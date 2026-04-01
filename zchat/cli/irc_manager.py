# zchat/cli/irc_manager.py
"""IRC daemon (ergo) and WeeChat pane management."""
import json
import os
import subprocess
import time

import libtmux

from zchat.cli.tmux import get_or_create_session, find_pane, pane_alive, find_window, window_alive


class IrcManager:
    """Manage ergo IRC daemon and WeeChat tmux pane."""

    def __init__(self, config: dict, state_file: str, tmux_session: str = "zchat"):
        self.config = config
        self._state_file = state_file
        self._tmux_session_name = tmux_session
        self._tmux_session: libtmux.Session | None = None
        self._state: dict = {}
        self._project_dir = os.path.dirname(state_file) if state_file else ""
        self._load_state()

    @property
    def tmux_session(self) -> libtmux.Session:
        if self._tmux_session is None:
            self._tmux_session = get_or_create_session(self._tmux_session_name)
        return self._tmux_session

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

        # Inject auth-script config if OIDC is enabled
        from zchat.cli.auth import get_credentials
        if get_credentials():
            self._inject_auth_script(ergo_data_dir, ergo_conf)

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

    def _inject_auth_script(self, ergo_data_dir: str, ergo_conf: str):
        """Inject auth-script and require-sasl settings into ergo config."""
        import shutil
        import sys as _sys
        script_src = os.path.join(os.path.dirname(__file__), "ergo_auth_script.py")
        script_dst = os.path.join(ergo_data_dir, "ergo_auth_script.py")
        shutil.copy2(script_src, script_dst)
        os.chmod(script_dst, 0o755)

        from zchat.cli.auth import discover_oidc_endpoints, load_cached_token, _global_auth_dir
        auth_data = load_cached_token(_global_auth_dir()) or {}
        issuer = auth_data.get("token_endpoint", "").rsplit("/", 1)[0] if auth_data.get("token_endpoint") else ""
        try:
            endpoints = discover_oidc_endpoints(issuer) if issuer else {}
            config_file = os.path.join(ergo_data_dir, "auth_script_config.json")
            import json as _json
            with open(config_file, "w") as f:
                _json.dump({"userinfo_url": endpoints["userinfo_endpoint"]}, f)
        except Exception as e:
            print(f"Warning: Could not discover OIDC endpoints: {e}")

        python_path = _sys.executable

        with open(ergo_conf) as f:
            config_text = f.read()

        import re
        config_text = re.sub(
            r'(auth-script:\s*\n\s*enabled:\s*)false',
            r'\1true',
            config_text,
        )
        config_text = re.sub(
            r'(command:\s*)"[^"]*authenticate-irc-user"',
            f'\\1"{python_path} {script_dst}"',
            config_text,
        )
        config_text = re.sub(
            r'(require-sasl:\s*\n\s*enabled:\s*)false',
            r'\1true',
            config_text,
        )

        with open(ergo_conf, 'w') as f:
            f.write(config_text)

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
        """Start WeeChat in its own tmux window, auto-connect to IRC."""
        existing = self._state.get("irc", {}).get("weechat_window")
        if existing and self._window_alive(existing):
            print(f"WeeChat already running (window {existing}).")
            return

        # Load tmuxp session if YAML exists and session doesn't
        project_dir = os.path.dirname(self._state_file)
        tmuxp_path = os.path.join(project_dir, "tmuxp.yaml")
        if os.path.isfile(tmuxp_path):
            # Update YAML with WeeChat window before loading
            self._update_tmuxp_weechat(tmuxp_path)
            import subprocess as sp
            sp.run(["tmuxp", "load", "-d", tmuxp_path], capture_output=True)
            # Refresh session reference after tmuxp creates it
            self._tmux_session = None

        server = self.irc_config.get("server", "127.0.0.1")
        port = self.irc_config.get("port", 6667)
        tls = self.irc_config.get("tls", False)
        from zchat.cli.auth import get_username
        nick = nick_override or get_username()
        channels = self.config.get("agents", {}).get("default_channels", ["#general"])
        tls_flag = "" if tls else " -notls"

        # Per-project WeeChat config dir to avoid cross-project conflicts
        weechat_home = os.path.join(project_dir, ".weechat")
        os.makedirs(weechat_home, exist_ok=True)

        # WeeChat IRC server name: {project}-ergo
        project_name = os.path.basename(project_dir)
        srv_name = f"{project_name}-ergo"

        # SASL config — nick is the SASL login, token is the credential
        sasl_cmds = ""
        from zchat.cli.auth import get_credentials
        creds = get_credentials()
        if creds:
            _, token = creds
            sasl_cmds = (
                f"; /set irc.server.{srv_name}.sasl_mechanism PLAIN"
                f"; /set irc.server.{srv_name}.sasl_username {nick}"
                f"; /set irc.server.{srv_name}.sasl_password {token}"
            )

        # Source env file if configured
        env_file = self.config.get("agents", {}).get("env_file", "")
        source_env = f"[ -f '{env_file}' ] && set -a && source '{env_file}' && set +a; " if env_file else ""

        autojoin = ",".join(channels)
        plugin_path = self._find_weechat_plugin()
        load_plugin = f"; /script load {plugin_path}" if plugin_path else ""

        cmd = (
            f"{source_env}weechat -d {weechat_home} -r '"
            f"/server add {srv_name} {server}/{port}{tls_flag} -nicks={nick}"
            f"; /set irc.server.{srv_name}.autojoin \"{autojoin}\""
            f"{sasl_cmds}"
            f"; /connect {srv_name}{load_plugin}'"
        )

        # Check if weechat window already exists (from tmuxp load)
        weechat_window = find_window(self.tmux_session, "weechat")
        if weechat_window:
            pane = weechat_window.active_pane
            if pane:
                pane.send_keys(cmd, enter=True)
        else:
            weechat_window = self.tmux_session.new_window(
                window_name="weechat", window_shell=cmd, attach=False,
            )

        self._state.setdefault("irc", {})["weechat_window"] = "weechat"
        self._save_state()
        print(f"WeeChat started (window weechat, nick {nick}).")

    def _update_tmuxp_weechat(self, tmuxp_path: str):
        """Update tmuxp.yaml to include WeeChat window."""
        import yaml
        with open(tmuxp_path) as f:
            cfg = yaml.safe_load(f)
        cfg["windows"] = [
            {"window_name": "weechat", "panes": ["blank"], "focus": True},
        ]
        with open(tmuxp_path, "w") as f:
            yaml.dump(cfg, f, default_flow_style=False)

    def stop_weechat(self):
        """Stop WeeChat by sending /quit."""
        wname = self._state.get("irc", {}).get("weechat_window")
        if not wname:
            # Legacy: try pane_id
            wname = self._state.get("irc", {}).get("weechat_pane_id")
        if wname and self._window_alive(wname):
            window = find_window(self.tmux_session, wname)
            if window and window.active_pane:
                window.active_pane.send_keys("/quit", enter=True)
            self._state.get("irc", {}).pop("weechat_window", None)
            self._state.get("irc", {}).pop("weechat_pane_id", None)
            self._save_state()
            print("WeeChat stopped.")
        else:
            print("WeeChat not running.")

    def status(self) -> dict:
        """Return IRC status info."""
        from zchat.cli.auth import get_username
        ergo_running = self._is_ergo_running()
        wname = self._state.get("irc", {}).get("weechat_window")
        weechat_running = wname and self._window_alive(wname)
        return {
            "daemon": {
                "running": ergo_running,
                "pid": self._state.get("irc", {}).get("daemon_pid"),
                "server": self.irc_config.get("server"),
                "port": self.irc_config.get("port"),
            },
            "weechat": {
                "running": weechat_running,
                "window": wname if weechat_running else None,
                "nick": get_username(),
            },
        }

    def _find_weechat_plugin(self) -> str | None:
        """Find zchat.py WeeChat plugin. Checks config, project dir, then common locations."""
        plugin_path = self.config.get("weechat", {}).get("plugin_path", "")
        if plugin_path and os.path.isfile(plugin_path):
            return plugin_path
        candidates = [
            os.path.join(self._project_dir, ".weechat", "python", "autoload", "zchat.py"),
            os.path.expanduser("~/.config/weechat/python/autoload/zchat.py"),  # XDG (WeeChat 4.x)
            os.path.expanduser("~/.weechat/python/autoload/zchat.py"),         # Legacy
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
        return None

    def _port_in_use(self, port: int) -> bool:
        return subprocess.run(["lsof", "-i", f":{port}"],
                              capture_output=True).returncode == 0

    def _is_ergo_running(self) -> bool:
        port = self.irc_config.get("port", 6667)
        return self._port_in_use(port)

    def _pane_alive(self, pane_id: str) -> bool:
        return pane_alive(self.tmux_session, pane_id)

    def _window_alive(self, window_name: str) -> bool:
        return window_alive(self.tmux_session, window_name)

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
