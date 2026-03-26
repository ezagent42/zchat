# wc-agent/irc_manager.py
"""IRC daemon (ergo) and WeeChat pane management."""
import json
import os
import subprocess
import time


class IrcManager:
    """Manage ergo IRC daemon and WeeChat tmux pane."""

    def __init__(self, config: dict, state_file: str, tmux_session: str = "weechat-claude"):
        self.config = config
        self._state_file = state_file
        self.tmux_session = tmux_session
        self._state: dict = {}
        self._load_state()

    @property
    def irc_config(self) -> dict:
        return self.config.get("irc", {})

    def daemon_start(self):
        """Start local ergo IRC server."""
        server = self.irc_config.get("server", "127.0.0.1")
        if server not in ("127.0.0.1", "localhost", "::1"):
            print(f"IRC server is remote ({server}), no local daemon needed.")
            return

        if self._is_ergo_running():
            pid = self._state.get("irc", {}).get("daemon_pid")
            print(f"ergo already running (pid {pid or 'unknown'}).")
            return

        ergo_data_dir = os.environ.get("ERGO_DATA_DIR",
                                        os.path.expanduser("~/.local/share/ergo"))
        os.makedirs(ergo_data_dir, exist_ok=True)

        # Find ergo.yaml — check project dir first, then script dir
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ergo_conf = os.path.join(script_dir, "ergo.yaml")
        if not os.path.isfile(ergo_conf):
            print("Error: ergo.yaml not found.")
            return

        proc = subprocess.Popen(
            ["ergo", "run", "--conf", ergo_conf],
            cwd=ergo_data_dir,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1)
        if proc.poll() is None:
            self._state.setdefault("irc", {})["daemon_pid"] = proc.pid
            self._save_state()
            port = self.irc_config.get("port", 6667)
            print(f"ergo running (pid {proc.pid}, port {port}).")
        else:
            print("Error: ergo failed to start.")

    def daemon_stop(self):
        """Stop local ergo IRC server."""
        subprocess.run(["pkill", "-x", "ergo"], capture_output=True)
        if "irc" in self._state:
            self._state["irc"].pop("daemon_pid", None)
            self._save_state()
        print("ergo stopped.")

    def start_weechat(self, nick_override: str | None = None):
        """Start WeeChat in tmux, auto-connect to IRC."""
        existing = self._state.get("irc", {}).get("weechat_pane_id")
        if existing and self._pane_alive(existing):
            print(f"WeeChat already running (pane {existing}).")
            return

        server = self.irc_config.get("server", "127.0.0.1")
        port = self.irc_config.get("port", 6667)
        tls = self.irc_config.get("tls", False)
        nick = nick_override or self.config.get("agents", {}).get("username") or os.environ.get("USER", "user")
        channels = self.config.get("agents", {}).get("default_channels", ["#general"])
        channels_str = "; ".join(f"/join {ch}" for ch in channels)
        tls_flag = "" if tls else " -notls"

        # Source proxy env if available
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_file = os.path.join(script_dir, "claude.local.env")
        source_env = f"[ -f '{env_file}' ] && set -a && source '{env_file}' && set +a; " if os.path.isfile(env_file) else ""

        cmd = f"{source_env}weechat -r '/server add wc-local {server}/{port}{tls_flag} -nicks={nick}; /connect wc-local; {channels_str}'"

        result = subprocess.run(
            ["tmux", "split-window", "-v", "-P", "-F", "#{pane_id}",
             "-t", self.tmux_session, cmd],
            capture_output=True, text=True,
        )
        pane_id = result.stdout.strip()
        # Set pane title for iTerm2 tab display
        subprocess.run(["tmux", "select-pane", "-t", pane_id, "-T", f"weechat ({nick})"],
                       capture_output=True)
        self._state.setdefault("irc", {})["weechat_pane_id"] = pane_id
        self._save_state()
        print(f"WeeChat started (pane {pane_id}, nick {nick}).")

    def stop_weechat(self):
        """Stop WeeChat by sending /quit."""
        pane = self._state.get("irc", {}).get("weechat_pane_id")
        if pane and self._pane_alive(pane):
            subprocess.run(["tmux", "send-keys", "-t", pane, "/quit", "Enter"],
                           capture_output=True)
            self._state.get("irc", {}).pop("weechat_pane_id", None)
            self._save_state()
            print("WeeChat stopped.")
        else:
            print("WeeChat not running.")

    def status(self) -> dict:
        """Return IRC status info."""
        ergo_running = self._is_ergo_running()
        pane = self._state.get("irc", {}).get("weechat_pane_id")
        weechat_running = pane and self._pane_alive(pane)
        return {
            "daemon": {
                "running": ergo_running,
                "pid": self._state.get("irc", {}).get("daemon_pid"),
                "server": self.irc_config.get("server"),
                "port": self.irc_config.get("port"),
            },
            "weechat": {
                "running": weechat_running,
                "pane_id": pane if weechat_running else None,
                "nick": self.config.get("agents", {}).get("username"),
            },
        }

    def _is_ergo_running(self) -> bool:
        return subprocess.run(["pgrep", "-x", "ergo"],
                              capture_output=True).returncode == 0

    def _pane_alive(self, pane_id: str) -> bool:
        result = subprocess.run(["tmux", "list-panes", "-F", "#{pane_id}"],
                                capture_output=True, text=True)
        return pane_id in result.stdout

    def _load_state(self):
        if os.path.isfile(self._state_file):
            try:
                with open(self._state_file) as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._state = {}

    def _save_state(self):
        os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
        with open(self._state_file, "w") as f:
            json.dump(self._state, f, indent=2)
