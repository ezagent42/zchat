# zchat/cli/irc_manager.py
"""IRC daemon (ergo) and WeeChat pane management."""
import json
import os
import subprocess
import time


class IrcManager:
    """Manage ergo IRC daemon and WeeChat tmux pane."""

    def __init__(self, config: dict, state_file: str, tmux_session: str = "zchat"):
        self.config = config
        self._state_file = state_file
        self.tmux_session = tmux_session
        self._state: dict = {}
        self._load_state()

    @property
    def irc_config(self) -> dict:
        return self.config.get("irc", {})

    def daemon_start(self, port_override: int | None = None):
        """Start local ergo IRC server. Uses port_override or project config port."""
        server = self.irc_config.get("server", "127.0.0.1")
        if server not in ("127.0.0.1", "localhost", "::1"):
            print(f"IRC server is remote ({server}), no local daemon needed.")
            return

        port = port_override or self.irc_config.get("port", 6667)

        # Check if already listening on our port
        if self._port_in_use(port):
            pid = self._state.get("irc", {}).get("daemon_pid")
            print(f"ergo already running on port {port} (pid {pid or 'unknown'}).")
            return

        # Use per-project ergo data dir to avoid conflicts
        state_dir = os.path.dirname(self._state_file)
        ergo_data_dir = os.path.join(state_dir, "ergo")
        os.makedirs(ergo_data_dir, exist_ok=True)

        # Copy languages from system ergo install if needed
        system_ergo = os.path.expanduser("~/.local/share/ergo")
        if os.path.isdir(os.path.join(system_ergo, "languages")) and \
           not os.path.isdir(os.path.join(ergo_data_dir, "languages")):
            import shutil
            shutil.copytree(os.path.join(system_ergo, "languages"),
                            os.path.join(ergo_data_dir, "languages"))

        # Generate ergo config with project's port
        ergo_conf = os.path.join(ergo_data_dir, "ergo.yaml")
        result = subprocess.run(["ergo", "defaultconfig"], capture_output=True, text=True)
        if result.returncode != 0:
            print("Error: 'ergo defaultconfig' failed. Is ergo installed?")
            return
        config_text = result.stdout
        # Patch port
        config_text = config_text.replace('"127.0.0.1:6667":', f'"127.0.0.1:{port}":')
        # Remove IPv6 listener
        lines = config_text.split('\n')
        lines = [l for l in lines if '[::1]:6667' not in l]
        config_text = '\n'.join(lines)
        # Remove TLS listener (requires certs)
        import re
        config_text = re.sub(r'":6697":\s*\n.*?min-tls-version:.*?\n', '', config_text, flags=re.DOTALL)
        with open(ergo_conf, 'w') as f:
            f.write(config_text)

        # Remove stale lock
        lock_file = os.path.join(ergo_data_dir, "ircd.lock")
        if os.path.exists(lock_file):
            os.remove(lock_file)

        # Start ergo
        log_file = os.path.join(ergo_data_dir, "ergo.log")
        with open(log_file, 'w') as lf:
            proc = subprocess.Popen(
                ["ergo", "run", "--conf", ergo_conf],
                cwd=ergo_data_dir,
                stdout=lf, stderr=lf,
            )
        time.sleep(2)

        if self._port_in_use(port):
            self._state.setdefault("irc", {})["daemon_pid"] = proc.pid
            self._save_state()
            print(f"ergo running (pid {proc.pid}, port {port}).")
        else:
            print(f"Error: ergo failed to start on port {port}.")
            print(f"  Log: {log_file}")
            try:
                with open(log_file) as f:
                    for line in f.readlines()[-5:]:
                        print(f"  {line.rstrip()}")
            except Exception:
                pass

    def daemon_stop(self):
        """Stop local ergo IRC server (by PID or port)."""
        port = self.irc_config.get("port", 6667)
        pid = self._state.get("irc", {}).get("daemon_pid")
        if pid:
            subprocess.run(["kill", str(pid)], capture_output=True)
        # Also kill by port in case PID is stale
        result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
        if result.stdout.strip():
            subprocess.run(["kill"] + result.stdout.strip().split(), capture_output=True)
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
        tls_flag = "" if tls else " -notls"

        # Source proxy env if available
        script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        env_file = os.path.join(script_dir, "claude.local.env")
        source_env = f"[ -f '{env_file}' ] && set -a && source '{env_file}' && set +a; " if os.path.isfile(env_file) else ""

        # Use irc.server.wc-local.autojoin instead of /join — /connect is async so /join may run before connected
        autojoin = ",".join(channels)
        # Load zchat plugin if available
        plugin_dir = os.path.join(script_dir, "weechat-zchat-plugin")
        plugin_path = os.path.join(plugin_dir, "zchat.py")
        load_plugin = f"; /script load {plugin_path}" if os.path.isfile(plugin_path) else ""

        cmd = f"{source_env}weechat -r '/server add wc-local {server}/{port}{tls_flag} -nicks={nick}; /set irc.server.wc-local.autojoin \"{autojoin}\"; /connect wc-local{load_plugin}'"

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

    def _port_in_use(self, port: int) -> bool:
        return subprocess.run(["lsof", "-i", f":{port}"],
                              capture_output=True).returncode == 0

    def _is_ergo_running(self) -> bool:
        port = self.irc_config.get("port", 6667)
        return self._port_in_use(port)

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
