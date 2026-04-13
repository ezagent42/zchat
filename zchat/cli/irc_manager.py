# zchat/cli/irc_manager.py
"""IRC daemon (ergo) and WeeChat pane management."""
import json
import os
import socket
import ssl
import subprocess
import time

from zchat.cli import zellij


def check_irc_connectivity(server: str, port: int, tls: bool = False, timeout: float = 5) -> None:
    """Raise ConnectionError if IRC server is unreachable."""
    try:
        sock = socket.create_connection((server, port), timeout=timeout)
        if tls:
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=server)
        sock.close()
    except OSError as e:
        raise ConnectionError(f"Cannot reach IRC server {server}:{port} — {e}")


class IrcManager:
    """Manage ergo IRC daemon and WeeChat Zellij tab."""

    def __init__(self, config: dict, state_file: str, zellij_session: str = "zchat"):
        self.config = config
        self._state_file = state_file
        self._session_name = zellij_session
        self._state: dict = {}
        self._project_dir = os.path.dirname(state_file) if state_file else ""
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
        # Remove TLS listener and cert/key config (requires certs we don't have)
        import re
        config_text = re.sub(r'.*":6697".*\n', '', config_text)
        config_text = re.sub(r'\s+tls:\s*\n\s+cert:.*\n\s+key:.*\n', '\n', config_text)
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
        """Stop local ergo IRC server (by stored PID only).

        Only kills the ergo process that was started by this project (stored in
        state.json).  Never kills by port alone — that could hit an unrelated
        ergo instance such as the ergo-inside launchd service.
        """
        pid = self._state.get("irc", {}).get("daemon_pid")
        if pid:
            subprocess.run(["kill", str(pid)], capture_output=True)
        if "irc" in self._state:
            self._state["irc"].pop("daemon_pid", None)
            self._save_state()
        print("ergo stopped.")

    def start_weechat(self, nick_override: str | None = None):
        """Start WeeChat in its own Zellij tab, auto-connect to IRC."""
        existing = self._state.get("irc", {}).get("weechat_tab")
        if existing and zellij.tab_exists(self._session_name, existing):
            print(f"WeeChat already running (tab {existing}).")
            return

        # Pre-check IRC server connectivity
        server = self.irc_config.get("server", "127.0.0.1")
        port = self.irc_config.get("port", 6667)
        tls = self.irc_config.get("tls", False)
        check_irc_connectivity(server, port, tls=tls)

        cmd = self.build_weechat_cmd(nick_override=nick_override)
        zellij.new_tab(self._session_name, "weechat", command=cmd)
        pane_id = zellij.get_pane_id(self._session_name, "weechat")

        self._state.setdefault("irc", {})["weechat_tab"] = "weechat"
        if pane_id:
            self._state["irc"]["weechat_pane_id"] = pane_id
        self._save_state()
        from zchat.cli.auth import get_username
        nick = nick_override or get_username()
        print(f"WeeChat started (tab weechat, nick {nick}).")

    def build_weechat_cmd(self, nick_override: str | None = None) -> str:
        """Build the WeeChat startup command string (without launching it)."""
        server = self.irc_config.get("server", self.irc_config.get("host", "127.0.0.1"))
        port = self.irc_config.get("port", 6667)
        tls = self.irc_config.get("tls", False)

        from zchat.cli.auth import get_username
        nick = nick_override or get_username()
        channels = self.config.get("default_channels") or self.config.get("agents", {}).get("default_channels", [])
        tls_flag = "" if tls else " -notls"

        project_dir = os.path.dirname(self._state_file)
        weechat_home = os.path.join(project_dir, ".weechat")
        os.makedirs(weechat_home, exist_ok=True)

        project_name = os.path.basename(project_dir)
        srv_name = f"{project_name}-ergo"

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

        env_file = self.config.get("env_file") or self.config.get("agents", {}).get("env_file", "")
        source_env = f"[ -f '{env_file}' ] && set -a && source '{env_file}' && set +a; " if env_file else ""

        autojoin = ",".join(channels)
        plugin_path = self._find_weechat_plugin()
        load_plugin = f"; /script load {plugin_path}" if plugin_path else ""

        return (
            f"{source_env}weechat -d {weechat_home} -r '"
            f"/server add {srv_name} {server}/{port}{tls_flag} -nicks={nick}"
            f"; /set irc.server.{srv_name}.autojoin \"{autojoin}\""
            f"; /set irc.server.{srv_name}.autoconnect on"
            f"; /set irc.server.{srv_name}.autoreconnect on"
            f"; /set irc.server.{srv_name}.autoreconnect_delay 10"
            f"{sasl_cmds}"
            f"; /connect {srv_name}{load_plugin}'"
        )

    def stop_weechat(self):
        """Stop WeeChat by sending /quit."""
        wname = self._state.get("irc", {}).get("weechat_tab")
        if not wname:
            # Legacy: try pane_id
            wname = self._state.get("irc", {}).get("weechat_pane_id")
        if wname and zellij.tab_exists(self._session_name, wname):
            pane_id = zellij.get_pane_id(self._session_name, wname)
            if pane_id:
                zellij.send_command(self._session_name, pane_id, "/quit")
            self._state.get("irc", {}).pop("weechat_tab", None)
            self._state.get("irc", {}).pop("weechat_pane_id", None)
            self._save_state()
            print("WeeChat stopped.")
        else:
            print("WeeChat not running.")

    def status(self) -> dict:
        """Return IRC status info."""
        from zchat.cli.auth import get_username
        ergo_running = self._is_ergo_running()
        wname = self._state.get("irc", {}).get("weechat_tab")
        weechat_running = wname and zellij.tab_exists(self._session_name, wname)
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
