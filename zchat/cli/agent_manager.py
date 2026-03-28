"""Agent lifecycle management: create workspace, spawn tmux, track state."""

import json
import os
import shutil
import subprocess
import tempfile
import time

import libtmux

from zchat.cli.tmux import get_session, find_pane, pane_alive
from zchat_protocol.naming import scoped_name, AGENT_SEPARATOR


DEFAULT_STATE_FILE = os.path.expanduser("~/.local/state/zchat/agents.json")


class AgentManager:
    def __init__(self, irc_server: str, irc_port: int, irc_tls: bool,
                 username: str, default_channels: list[str],
                 env_file: str = "",
                 claude_args: list[str] | None = None,
                 tmux_session: str = "zchat",
                 state_file: str = DEFAULT_STATE_FILE):
        self.irc_server = irc_server
        self.irc_port = irc_port
        self.irc_tls = irc_tls
        self.username = username
        self.default_channels = default_channels
        self.env_file = env_file
        self.claude_args = claude_args or [
            "--permission-mode", "bypassPermissions",
            "--dangerously-load-development-channels", "server:zchat-channel",
        ]
        self._tmux_session_name = tmux_session
        self._tmux_session: libtmux.Session | None = None
        self._state_file = state_file
        self._agents: dict[str, dict] = {}
        self._load_state()

    @property
    def tmux_session(self) -> libtmux.Session:
        if self._tmux_session is None:
            self._tmux_session = get_session(self._tmux_session_name)
        return self._tmux_session

    def scoped(self, name: str) -> str:
        return scoped_name(name, self.username)

    def create(self, name: str, workspace: str | None = None, channels: list[str] | None = None) -> dict:
        """Create and launch a new agent. Returns agent info dict."""
        name = self.scoped(name)
        if name in self._agents and self._agents[name].get("status") == "running":
            raise ValueError(f"{name} already exists and is running")

        channels = channels or list(self.default_channels)
        agent_workspace = self._create_workspace(name, channels) if not workspace else workspace
        if workspace:
            self._write_workspace_config(name, workspace, channels)

        pane_id = self._spawn_tmux(name, agent_workspace)

        self._agents[name] = {
            "workspace": agent_workspace,
            "pane_id": pane_id,
            "status": "starting",
            "created_at": time.time(),
            "channels": channels,
        }
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
        name = self.scoped(name)
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        channels = list(agent.get("channels", self.default_channels))
        self.stop(name)
        base_name = name.split(AGENT_SEPARATOR, 1)[-1] if AGENT_SEPARATOR in name else name
        self.create(base_name, channels=channels)

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

    def _create_workspace(self, name: str, channels: list[str]) -> str:
        safe = name.replace(AGENT_SEPARATOR, "_")
        workspace = os.path.join(tempfile.gettempdir(), f"zchat-{safe}")
        os.makedirs(workspace, exist_ok=True)
        self._write_workspace_config(name, workspace, channels)
        return workspace

    def _write_workspace_config(self, name: str, workspace: str, channels: list[str]):
        """Write .claude/settings.local.json and .mcp.json for the agent workspace."""
        # Claude settings — auto-allow MCP tools
        claude_dir = os.path.join(workspace, ".claude")
        os.makedirs(claude_dir, exist_ok=True)
        settings = {
            "permissions": {
                "allow": [
                    "mcp__zchat-channel__reply",
                    "mcp__zchat-channel__join_channel",
                ]
            }
        }
        with open(os.path.join(claude_dir, "settings.local.json"), "w") as f:
            json.dump(settings, f, indent=2)

        # MCP server config — tells Claude how to reach the channel server
        channels_str = ",".join(ch.lstrip("#") for ch in channels)
        config = {
            "mcpServers": {
                "zchat-channel": {
                    "type": "stdio",
                    "command": "zchat-channel",
                    "env": {
                        "AGENT_NAME": name,
                        "IRC_SERVER": self.irc_server,
                        "IRC_PORT": str(self.irc_port),
                        "IRC_CHANNELS": channels_str,
                        "IRC_TLS": str(self.irc_tls).lower(),
                    },
                }
            }
        }
        with open(os.path.join(workspace, ".mcp.json"), "w") as f:
            json.dump(config, f, indent=2)

    def _spawn_tmux(self, name: str, workspace: str) -> str:
        source_env = ""
        if self.env_file:
            source_env = f"[ -f '{self.env_file}' ] && set -a && source '{self.env_file}' && set +a; "
        args_str = " ".join(self.claude_args)
        cmd = (
            f"{source_env}"
            f"cd '{workspace}' && "
            f"AGENT_NAME='{name}' "
            f"claude {args_str}"
        )
        window = self.tmux_session.active_window
        pane = window.split(attach=False, direction=libtmux.constants.PaneDirection.Below, shell=cmd)
        pane_id = pane.pane_id
        pane.cmd("select-pane", "-T", f"agent: {name}")
        # Auto-confirm development channels prompt after 3s
        subprocess.Popen(
            ["bash", "-c", f"sleep 3 && tmux send-keys -t {pane_id} Enter"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return pane_id

    def _force_stop(self, name: str):
        agent = self._agents.get(name)
        if agent and agent.get("pane_id"):
            pane = find_pane(self.tmux_session, agent["pane_id"])
            if pane:
                pane.send_keys("/exit", enter=True)

    def _cleanup_workspace(self, name: str):
        agent = self._agents.get(name)
        if agent:
            ws = agent.get("workspace", "")
            if ws.startswith(tempfile.gettempdir()):
                shutil.rmtree(ws, ignore_errors=True)

    def _check_alive(self, name: str) -> str:
        agent = self._agents.get(name)
        if not agent or not agent.get("pane_id"):
            return "offline"
        if pane_alive(self.tmux_session, agent["pane_id"]):
            return "running"
        return "offline"

    def send(self, name: str, text: str):
        """Send text to agent's tmux pane."""
        name = self.scoped(name)
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        if self._check_alive(name) != "running":
            raise ValueError(f"{name} is not running")
        pane = find_pane(self.tmux_session, agent["pane_id"])
        if pane:
            pane.send_keys(text, enter=True)

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
