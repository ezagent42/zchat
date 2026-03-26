"""Agent lifecycle management: create workspace, spawn tmux, track state."""

import json
import os
import shutil
import subprocess
import tempfile
import time

import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from wc_protocol.naming import scoped_name, AGENT_SEPARATOR


DEFAULT_STATE_FILE = os.path.expanduser("~/.local/state/wc-agent/agents.json")


class AgentManager:
    def __init__(self, irc_server: str, irc_port: int, irc_tls: bool,
                 channel_server_dir: str, username: str,
                 default_channels: list[str],
                 tmux_session: str = "weechat-claude",
                 state_file: str = DEFAULT_STATE_FILE):
        self.irc_server = irc_server
        self.irc_port = irc_port
        self.irc_tls = irc_tls
        self.channel_server_dir = channel_server_dir
        self.username = username
        self.default_channels = default_channels
        self.tmux_session = tmux_session
        self._state_file = state_file
        self._agents: dict[str, dict] = {}
        self._load_state()

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
            self._write_mcp_json(name, workspace, channels)

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
        # Remove the scoped name so create re-scopes
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
        workspace = os.path.join(tempfile.gettempdir(), f"wc-agent-{safe}")
        os.makedirs(workspace, exist_ok=True)
        self._write_mcp_json(name, workspace, channels)
        return workspace

    def _write_mcp_json(self, name: str, workspace: str, channels: list[str]):
        channels_str = ",".join(ch.lstrip("#") for ch in channels)
        config = {
            "mcpServers": {
                "weechat-channel": {
                    "type": "stdio",
                    "command": "uv",
                    "args": [
                        "run", "--project", self.channel_server_dir,
                        "python3", os.path.join(self.channel_server_dir, "server.py"),
                    ],
                    "env": {
                        "AGENT_NAME": name,
                        "IRC_SERVER": self.irc_server,
                        "IRC_PORT": str(self.irc_port),
                        "IRC_CHANNELS": channels_str,
                        "IRC_TLS": str(self.irc_tls).lower(),
                        "WC_TMUX_SESSION": self.tmux_session,
                        "WC_PROJECT_DIR": os.path.dirname(self._state_file),
                        "no_proxy": f"localhost,127.0.0.1,{self.irc_server}",
                        "NO_PROXY": f"localhost,127.0.0.1,{self.irc_server}",
                    },
                }
            }
        }
        with open(os.path.join(workspace, ".mcp.json"), "w") as f:
            json.dump(config, f, indent=2)

    def _spawn_tmux(self, name: str, workspace: str) -> str:
        # Source proxy/env settings if available (claude needs proxy to reach API)
        env_file = os.path.join(self.channel_server_dir, "..", "claude.local.env")
        source_env = f"[ -f '{env_file}' ] && set -a && source '{env_file}' && set +a; "
        cmd = (
            f"{source_env}"
            f"cd '{workspace}' && "
            f"AGENT_NAME='{name}' "
            f"claude "
            f"--permission-mode bypassPermissions "
            f"--dangerously-load-development-channels server:weechat-channel"
        )
        result = subprocess.run(
            ["tmux", "split-window", "-v", "-P", "-F", "#{pane_id}",
             "-t", self.tmux_session, cmd],
            capture_output=True, text=True,
        )
        pane_id = result.stdout.strip()
        # Set pane title for iTerm2 tab display
        subprocess.run(["tmux", "select-pane", "-t", pane_id, "-T", f"agent: {name}"],
                       capture_output=True)
        # Auto-confirm development channels prompt after 3s
        subprocess.Popen(
            ["bash", "-c", f"sleep 3 && tmux send-keys -t {pane_id} Enter"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return pane_id

    def _force_stop(self, name: str):
        agent = self._agents.get(name)
        if agent and agent.get("pane_id"):
            subprocess.run(
                ["tmux", "send-keys", "-t", agent["pane_id"], "/exit", "Enter"],
                capture_output=True,
            )

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
        try:
            result = subprocess.run(
                ["tmux", "list-panes", "-t", self.tmux_session, "-F", "#{pane_id}"],
                capture_output=True, text=True,
            )
            if agent["pane_id"] in result.stdout:
                return "running"
        except Exception:
            pass
        return "offline"

    def send(self, name: str, text: str):
        """Send text to agent's tmux pane."""
        name = self.scoped(name)
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        pane = agent.get("pane_id")
        if not pane or not self._check_alive(name) == "running":
            raise ValueError(f"{name} is not running")
        subprocess.run(["tmux", "send-keys", "-t", pane, text, "Enter"],
                       capture_output=True)

    @classmethod
    def from_env(cls) -> "AgentManager":
        """Create AgentManager from environment variables (for use in channel-server)."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return cls(
            irc_server=os.environ.get("IRC_SERVER", "127.0.0.1"),
            irc_port=int(os.environ.get("IRC_PORT", "6667")),
            irc_tls=os.environ.get("IRC_TLS", "false").lower() == "true",
            channel_server_dir=os.path.join(script_dir, "..", "weechat-channel-server"),
            username=os.environ.get("AGENT_NAME", "agent0").split("-")[0],
            default_channels=[f"#{ch}" for ch in os.environ.get("IRC_CHANNELS", "general").split(",")],
            tmux_session=os.environ.get("WC_TMUX_SESSION", "weechat-claude"),
            state_file=os.path.join(os.environ.get("WC_PROJECT_DIR", os.path.expanduser("~/.wc-agent/projects/default")), "state.json"),
        )

    def _load_state(self):
        if os.path.isfile(self._state_file):
            try:
                with open(self._state_file) as f:
                    data = json.load(f)
                self._agents = data.get("agents", {})  # Only agents, not irc state
            except (json.JSONDecodeError, OSError):
                self._agents = {}

    def _save_state(self):
        os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
        # Read existing state to preserve "irc" key written by IrcManager
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
