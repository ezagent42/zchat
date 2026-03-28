# zchat/cli/project.py
"""Project management: create, list, use, remove, resolve."""
import os
import shutil
import tomllib

ZCHAT_DIR = os.environ.get("ZCHAT_HOME", os.path.expanduser("~/.zchat"))


def project_dir(name: str) -> str:
    return os.path.join(ZCHAT_DIR, "projects", name)


def create_project_config(name: str, server: str, port: int, tls: bool,
                          password: str, nick: str, channels: str,
                          env_file: str = "", claude_args: list[str] | None = None):
    """Create project directory and write config.toml."""
    pdir = project_dir(name)
    os.makedirs(pdir, exist_ok=True)
    channels_list = [ch.strip() for ch in channels.split(",") if ch.strip()]
    channels_toml = ", ".join(f'"{ch}"' for ch in channels_list)
    if claude_args is None:
        claude_args = [
            "--permission-mode", "bypassPermissions",
            "--dangerously-load-development-channels", "server:zchat-channel",
        ]
    args_toml = ", ".join(f'"{a}"' for a in claude_args)
    config_content = f'''[irc]
server = "{server}"
port = {port}
tls = {"true" if tls else "false"}
password = "{password}"

[agents]
default_channels = [{channels_toml}]
username = "{nick}"
env_file = "{env_file}"
claude_args = [{args_toml}]
'''
    with open(os.path.join(pdir, "config.toml"), "w") as f:
        f.write(config_content)


def list_projects() -> list[str]:
    projects_dir = os.path.join(ZCHAT_DIR, "projects")
    if not os.path.isdir(projects_dir):
        return []
    return sorted(d for d in os.listdir(projects_dir)
                  if os.path.isdir(os.path.join(projects_dir, d)))


def get_default_project() -> str | None:
    default_file = os.path.join(ZCHAT_DIR, "default")
    if os.path.isfile(default_file):
        return open(default_file).read().strip() or None
    return None


def set_default_project(name: str):
    os.makedirs(ZCHAT_DIR, exist_ok=True)
    with open(os.path.join(ZCHAT_DIR, "default"), "w") as f:
        f.write(name)


def resolve_project(explicit: str | None = None) -> str | None:
    """Resolve project: explicit > .zchat file > default."""
    if explicit:
        return explicit
    path = os.getcwd()
    while path != "/":
        marker = os.path.join(path, ".zchat")
        if os.path.isfile(marker):
            return open(marker).read().strip() or None
        path = os.path.dirname(path)
    return get_default_project()


def load_project_config(name: str) -> dict:
    """Load and validate project config.toml."""
    config_path = os.path.join(project_dir(name), "config.toml")
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)
    irc = cfg.setdefault("irc", {})
    irc.setdefault("server", "127.0.0.1")
    irc.setdefault("port", 6667)
    irc.setdefault("tls", False)
    irc.setdefault("password", "")
    agents = cfg.setdefault("agents", {})
    agents.setdefault("default_channels", ["#general"])
    if not agents.get("username"):
        agents["username"] = os.environ.get("USER", "user")
    agents.setdefault("env_file", "")
    agents.setdefault("claude_args", [
        "--permission-mode", "bypassPermissions",
        "--dangerously-load-development-channels", "server:zchat-channel",
    ])
    agents.setdefault("mcp_server_cmd", ["zchat-channel"])
    return cfg


def remove_project(name: str):
    """Remove project directory."""
    pdir = project_dir(name)
    if os.path.isdir(pdir):
        shutil.rmtree(pdir)


def state_file_path(name: str) -> str:
    """Return path to project state.json."""
    return os.path.join(project_dir(name), "state.json")
