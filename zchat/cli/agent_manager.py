"""Agent lifecycle management: create workspace, spawn zellij tab, track state."""

import glob as _glob
import json
import os
import shlex
import shutil
import subprocess as _sp
import tempfile
import threading
import time

from zchat.cli import zellij
from zchat.cli.irc_manager import check_irc_connectivity
from zchat.cli.runner import resolve_runner, render_env, _parse_env_file, _resolve_template_dir, _load_template_toml
from zchat_protocol.naming import scoped_name, AGENT_SEPARATOR


DEFAULT_STATE_FILE = os.path.expanduser("~/.local/state/zchat/agents.json")


def _find_channel_pkg_dir() -> str | None:
    """Locate zchat-channel-server package dir in its uv tool venv."""
    result = _sp.run(["uv", "tool", "dir"], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    tool_dir = result.stdout.strip()
    patterns = _glob.glob(
        os.path.join(tool_dir, "zchat-channel-server", "lib", "python*",
                     "site-packages", "zchat_channel_server")
    )
    return patterns[0] if patterns else None


class AgentManager:
    def __init__(self, irc_server: str, irc_port: int, irc_tls: bool,
                 irc_password: str,
                 username: str, default_channels: list[str],
                 env_file: str = "",
                 default_type: str = "claude",
                 zellij_session: str = "zchat",
                 state_file: str = DEFAULT_STATE_FILE,
                 project_dir: str = ""):
        self.irc_server = irc_server
        self.irc_port = irc_port
        self.irc_tls = irc_tls
        self.irc_password = irc_password
        self.username = username
        self.default_channels = default_channels
        self.env_file = env_file
        self.default_type = default_type
        self._session_name = zellij_session
        self._state_file = state_file
        self.project_dir = project_dir
        self._agents: dict[str, dict] = {}
        self._load_state()

    @property
    def session_name(self) -> str:
        return self._session_name

    def scoped(self, name: str) -> str:
        return scoped_name(name, self.username)

    def create(self, name: str, workspace: str | None = None,
               channels: list[str] | None = None,
               agent_type: str | None = None) -> dict:
        """Create and launch a new agent. Returns agent info dict."""
        # Pre-check IRC server connectivity
        check_irc_connectivity(self.irc_server, self.irc_port, tls=self.irc_tls)

        name = self.scoped(name)
        if name in self._agents and self._agents[name].get("status") in ("running", "starting"):
            raise ValueError(f"{name} already exists and is running or starting")

        agent_type = agent_type or self.default_type
        channels = channels or list(self.default_channels)
        agent_workspace = workspace or self._create_workspace(name)

        tab_name = self._spawn_tab(name, agent_workspace, agent_type, channels)

        self._agents[name] = {
            "type": agent_type,
            "workspace": agent_workspace,
            "tab_name": tab_name,
            "status": "starting",
            "created_at": time.time(),
            "channels": channels,
        }
        self._save_state()

        # Wait for ready marker (SessionStart hook)
        try:
            if self._wait_for_ready(name, timeout=60):
                self._agents[name]["status"] = "running"
            else:
                self._agents[name]["status"] = "error"
        except (KeyboardInterrupt, Exception):
            self._force_stop(name)
            self._cleanup_workspace(name)
            self._agents[name]["status"] = "offline"
            self._save_state()
            raise
        self._save_state()
        return self._agents[name]

    def stop(self, name: str, force: bool = False):
        """Stop an agent."""
        name = self.scoped(name)
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        if agent["status"] == "offline":
            raise ValueError(f"{name} is already offline")
        self._force_stop(name)
        agent["status"] = "offline"
        self._cleanup_workspace(name)
        self._save_state()

    def restart(self, name: str):
        """Stop then re-create with same config."""
        scoped = self.scoped(name)
        agent = self._agents.get(scoped)
        if not agent:
            raise ValueError(f"Unknown agent: {scoped}")
        channels = list(agent.get("channels", self.default_channels))
        agent_type = agent.get("type", self.default_type)
        self.stop(name)
        self.create(name, channels=channels, agent_type=agent_type)

    def list_agents(self) -> dict[str, dict]:
        """Return all agents with refreshed status."""
        for name, info in self._agents.items():
            if info.get("status") != "offline":
                info["status"] = self._check_alive(name)
        self._save_state()
        return dict(self._agents)

    def get_status(self, name: str) -> dict:
        name = self.scoped(name)
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        if agent["status"] != "offline":
            agent["status"] = self._check_alive(name)
        return agent

    def _create_workspace(self, name: str) -> str:
        if self.project_dir:
            workspace = os.path.join(self.project_dir, "agents", name)
        else:
            safe = name.replace(AGENT_SEPARATOR, "_")
            workspace = os.path.join(tempfile.gettempdir(), f"zchat-{safe}")
        os.makedirs(workspace, exist_ok=True)
        return workspace

    def _build_env_context(self, name: str, workspace: str, channels: list[str]) -> dict:
        """Build the context dict for template placeholder rendering."""
        channels_str = ",".join(ch.lstrip("#") for ch in channels)
        context = {
            "agent_name": name,
            "irc_server": self.irc_server,
            "irc_port": str(self.irc_port),
            "irc_channels": channels_str,
            "irc_tls": str(self.irc_tls).lower(),
            "irc_password": self.irc_password,
            "workspace": workspace,
            "zchat_project_dir": self.project_dir,
            "irc_auth_token": "",
            "auth_token_file": "",
        }
        if self.project_dir:
            from zchat.cli.auth import get_credentials, _global_auth_dir
            creds = get_credentials()
            if creds:
                _, token = creds
                context["irc_auth_token"] = token
                context["auth_token_file"] = os.path.join(_global_auth_dir(), "auth.json")
        channel_pkg = _find_channel_pkg_dir()
        if channel_pkg:
            context["channel_pkg_dir"] = channel_pkg
        else:
            context["channel_pkg_dir"] = ""
        return context

    def _spawn_tab(self, name: str, workspace: str, agent_type: str,
                   channels: list[str]) -> str:
        context = self._build_env_context(name, workspace, channels)
        env = render_env(agent_type, context)

        # Overlay project-level env_file (lower priority than template env)
        if self.env_file and os.path.isfile(self.env_file):
            project_env = _parse_env_file(self.env_file)
            merged = dict(project_env)
            merged.update(env)
            env = merged

        # Resolve start script from template directory
        tpl_dir = _resolve_template_dir(agent_type)
        if tpl_dir:
            start_script = os.path.join(tpl_dir, "start.sh")
            if not os.path.isfile(start_script):
                raise FileNotFoundError(f"start.sh not found in template '{agent_type}'")
        else:
            raise FileNotFoundError(f"Template '{agent_type}' not found")

        # Write env to workspace
        env_file_path = os.path.join(workspace, ".zchat-env")
        with open(env_file_path, "w") as f:
            for k, v in env.items():
                f.write(f"export {k}={shlex.quote(v)}\n")

        cmd = f"cd '{workspace}' && source .zchat-env && bash '{start_script}'"

        # Create dedicated tab for this agent
        zellij.new_tab(self._session_name, name, command=cmd)
        # Start background confirmation watcher
        self._auto_confirm_startup(name)
        return name

    def _force_stop(self, name: str):
        agent = self._agents.get(name)
        if not agent:
            return
        wname = agent.get("tab_name") or agent.get("window_name")
        if not wname:
            return
        if not zellij.tab_exists(self._session_name, wname):
            return

        agent_type = agent.get("type", self.default_type)
        try:
            tpl_dir = _resolve_template_dir(agent_type)
            if tpl_dir:
                tpl = _load_template_toml(tpl_dir)
                pre_stop = tpl.get("hooks", {}).get("pre_stop", "")
            else:
                pre_stop = ""
        except Exception:
            pre_stop = ""

        if pre_stop:
            pane_id = zellij.get_pane_id(self._session_name, wname)
            if pane_id:
                zellij.send_command(self._session_name, pane_id, pre_stop)
            # Poll for up to 10 seconds
            for _ in range(20):
                time.sleep(0.5)
                if not zellij.tab_exists(self._session_name, wname):
                    return
        # Close tab as fallback
        try:
            zellij.close_tab(self._session_name, wname)
        except Exception:
            pass

    def _cleanup_workspace(self, name: str):
        """Delete ready marker on stop. Preserve workspace for restart."""
        if self.project_dir:
            ready_file = os.path.join(self.project_dir, "agents", f"{name}.ready")
            if os.path.isfile(ready_file):
                os.remove(ready_file)
        else:
            # Legacy: clean up /tmp workspaces
            agent = self._agents.get(name)
            if agent:
                ws = agent.get("workspace", "")
                if ws.startswith(tempfile.gettempdir()):
                    shutil.rmtree(ws, ignore_errors=True)

    def _wait_for_ready(self, name: str, timeout: int = 60) -> bool:
        """Poll for .agents/<name>.ready file. Returns True if found within timeout."""
        if not self.project_dir:
            return True
        ready_path = os.path.join(self.project_dir, "agents", f"{name}.ready")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if os.path.isfile(ready_path):
                return True
            time.sleep(0.5)
        return False

    def _auto_confirm_startup(self, tab_name: str, timeout: int = 60):
        """Background thread: poll pane screen for confirmation prompts, send Enter.

        Uses dump-screen polling instead of subscribe to avoid leaving
        orphan zellij processes that block the parent from exiting.
        """
        def _watch():
            pane_id = None
            # Wait briefly for tab to be ready
            for _ in range(10):
                pane_id = zellij.get_pane_id(self._session_name, tab_name)
                if pane_id:
                    break
                time.sleep(0.5)
            if not pane_id:
                return

            deadline = time.time() + timeout
            # Patterns that appear in Claude Code startup prompts
            confirm_patterns = [
                "i trust this folder",
                "local development",
                "enter to confirm",
                "development channels",
                "experimental",
            ]
            confirmed: set[str] = set()
            while time.time() < deadline:
                screen = zellij.dump_screen(self._session_name, pane_id).lower()
                if not screen:
                    time.sleep(1)
                    continue
                for pattern in confirm_patterns:
                    if pattern in screen and pattern not in confirmed:
                        zellij.send_keys(self._session_name, pane_id, "Enter")
                        confirmed.add(pattern)
                        time.sleep(1)
                        break
                # Stop polling once Claude Code is ready (INSERT mode visible)
                if "insert" in screen:
                    break
                time.sleep(1)

        thread = threading.Thread(target=_watch, daemon=True)
        thread.start()

    def _check_alive(self, name: str) -> str:
        agent = self._agents.get(name)
        if not agent:
            return "offline"
        # Support both new (tab_name) and legacy (window_name) state
        tab_name = agent.get("tab_name") or agent.get("window_name")
        if tab_name:
            return "running" if zellij.tab_exists(self._session_name, tab_name) else "offline"
        return "offline"

    def send(self, name: str, text: str):
        """Send text to agent's zellij tab."""
        name = self.scoped(name)
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        if self._check_alive(name) != "running":
            raise ValueError(f"{name} is not running")
        if self.project_dir:
            ready_path = os.path.join(self.project_dir, "agents", f"{name}.ready")
            if not os.path.isfile(ready_path):
                raise ValueError(f"{name} is not ready (still starting up)")
        tab_name = agent.get("tab_name") or agent.get("window_name")
        pane_id = zellij.get_pane_id(self._session_name, tab_name)
        if not pane_id:
            raise ValueError(f"tab not found for {name}")
        zellij.send_command(self._session_name, pane_id, text)

    def _load_state(self):
        if os.path.isfile(self._state_file):
            try:
                with open(self._state_file) as f:
                    data = json.load(f)
                self._agents = data.get("agents", {})
            except (json.JSONDecodeError, OSError):
                self._agents = {}

    def _save_state(self):
        os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
        existing = {}
        if os.path.isfile(self._state_file):
            try:
                with open(self._state_file) as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        existing["agents"] = self._agents
        with open(self._state_file, "w") as f:
            json.dump(existing, f, indent=2)
