# zchat/cli/project.py
"""Project management: create, list, use, remove, resolve."""
import os
import shutil
import tomllib
import tomli_w

ZCHAT_DIR = os.environ.get("ZCHAT_HOME", os.path.expanduser("~/.zchat"))


def project_dir(name: str) -> str:
    return os.path.join(ZCHAT_DIR, "projects", name)


def _generate_session_name(project_name: str) -> str:
    """Generate a Zellij session name for a project."""
    return f"zchat-{project_name}"


def create_project_config(name: str, server: str = "local",
                          nick: str = "", channels: str = "#general",
                          env_file: str = "",
                          default_runner: str = "claude-channel",
                          mcp_server_cmd: list[str] | None = None,
                          # Legacy params kept for backward compat
                          port: int = 6667, tls: bool = False,
                          password: str = "",
                          default_type: str = "claude"):
    """Create project directory and write config.toml."""
    pdir = project_dir(name)
    os.makedirs(pdir, exist_ok=True)
    channels_list = [ch.strip() for ch in channels.split(",") if ch.strip()]
    session = _generate_session_name(name)
    if mcp_server_cmd is None:
        mcp_server_cmd = ["zchat-channel"]

    config = {
        "server": server,
        "default_runner": default_runner,
        "default_channels": channels_list,
        "username": nick,
        "env_file": env_file,
        "mcp_server_cmd": mcp_server_cmd,
        "zellij": {
            "session": session,
        },
    }

    with open(os.path.join(pdir, "config.toml"), "wb") as f:
        tomli_w.dump(config, f)


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
    """Load and validate project config.toml (new format only).

    Old-format configs (with [irc]/[tmux] sections) are rejected with a
    clear error message asking the user to recreate the project.
    """
    config_path = os.path.join(project_dir(name), "config.toml")
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)

    if "irc" in cfg or "tmux" in cfg:
        raise SystemExit(
            f"Error: Project '{name}' uses old config format.\n"
            f"Please delete and recreate:\n"
            f"  zchat project remove {name} && zchat project create {name}"
        )

    cfg.setdefault("server", "local")
    cfg.setdefault("default_runner", "claude-channel")
    cfg.setdefault("default_channels", ["#general"])
    cfg.setdefault("username", "")
    cfg.setdefault("env_file", "")
    cfg.setdefault("mcp_server_cmd", ["zchat-channel"])
    cfg.setdefault("zellij", {})
    cfg["zellij"].setdefault("session", _generate_session_name(name))
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
