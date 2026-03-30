# zchat/cli/project.py
"""Project management: create, list, use, remove, resolve."""
import os
import shutil
import tomllib
import tomli_w
import uuid

ZCHAT_DIR = os.environ.get("ZCHAT_HOME", os.path.expanduser("~/.zchat"))


def project_dir(name: str) -> str:
    return os.path.join(ZCHAT_DIR, "projects", name)


def _generate_tmux_session_name(project_name: str) -> str:
    """Generate a unique tmux session name for a project."""
    short_id = uuid.uuid4().hex[:8]
    return f"zchat-{short_id}-{project_name}"


def create_project_config(name: str, server: str, port: int, tls: bool,
                          password: str, nick: str, channels: str,
                          env_file: str = "", default_type: str = "claude",
                          auth_provider: str = "none", auth_issuer: str = "",
                          auth_client_id: str = ""):
    """Create project directory and write config.toml."""
    pdir = project_dir(name)
    os.makedirs(pdir, exist_ok=True)
    channels_list = [ch.strip() for ch in channels.split(",") if ch.strip()]
    channels_toml = ", ".join(f'"{ch}"' for ch in channels_list)
    tmux_session = _generate_tmux_session_name(name)
    config_content = f'''[irc]
server = "{server}"
port = {port}
tls = {"true" if tls else "false"}
password = "{password}"

[agents]
default_type = "{default_type}"
default_channels = [{channels_toml}]
username = "{nick}"
env_file = "{env_file}"

[tmux]
session = "{tmux_session}"

[auth]
provider = "{auth_provider}"
issuer = "{auth_issuer}"
client_id = "{auth_client_id}"
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
    agents.setdefault("default_type", "claude")
    auth = cfg.setdefault("auth", {})
    auth.setdefault("provider", "none")
    auth.setdefault("issuer", "")
    auth.setdefault("client_id", "")
    return cfg


def remove_project(name: str):
    """Remove project directory."""
    pdir = project_dir(name)
    if os.path.isdir(pdir):
        shutil.rmtree(pdir)


def state_file_path(name: str) -> str:
    """Return path to project state.json."""
    return os.path.join(project_dir(name), "state.json")


def set_config_value(name: str, key: str, value: str):
    """Set a dotted key in project config.toml. e.g., 'agents.default_type' = 'codex'."""
    config_path = os.path.join(project_dir(name), "config.toml")
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)

    # Navigate dotted key
    parts = key.split(".")
    target = cfg
    for part in parts[:-1]:
        target = target.setdefault(part, {})

    # Type coercion: try bool, int, then keep as string
    coerced: str | int | bool = value
    if value.lower() in ("true", "false"):
        coerced = value.lower() == "true"
    else:
        try:
            coerced = int(value)
        except ValueError:
            pass
    target[parts[-1]] = coerced

    with open(config_path, "wb") as f:
        tomli_w.dump(cfg, f)
