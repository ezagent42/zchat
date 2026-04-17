# zchat/cli/project.py
"""Project management: create, list, use, remove, resolve."""
from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

import tomli_w

from zchat.cli import paths


def project_dir(name: str) -> str:
    """Return project directory path as string (legacy compat)."""
    return str(paths.project_dir(name))


def _generate_session_name(project_name: str) -> str:
    """Generate a Zellij session name for a project."""
    return f"zchat-{project_name}"


def _channel_server_defaults() -> dict:
    """Return default [channel_server] config section."""
    return {
        "bridge_port": 9999,
        "plugins_dir": "plugins",
        "db_path": "conversations.db",
        "timers": {
            "takeover_wait": 180,
            "idle_timeout": 300,
            "close_timeout": 3600,
        },
        "participants": {
            "operators": [],
            "bridge_prefixes": ["feishu-bridge", "web-bridge"],
            "max_operator_concurrent": 5,
        },
    }


def generate_default_config(name: str, server: str = "127.0.0.1",
                            port: int = 6667, nick: str = "",
                            channels: str | None = None,
                            env_file: str = "",
                            default_runner: str | None = None,
                            mcp_server_cmd: list[str] | None = None) -> str:
    """Generate default config as TOML text (no file I/O)."""
    from zchat.cli.defaults import default_channels, default_runner as _default_runner, default_mcp_server_cmd
    if channels is None:
        channels = ",".join(default_channels())
    channels_list = [ch.strip() for ch in channels.split(",") if ch.strip()]
    session = _generate_session_name(name)
    if default_runner is None:
        default_runner = _default_runner()
    if mcp_server_cmd is None:
        mcp_server_cmd = default_mcp_server_cmd()

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
        "channel_server": _channel_server_defaults(),
    }
    return tomli_w.dumps(config)


def create_project_config(name: str, server: str = "local",
                          nick: str = "", channels: str | None = None,
                          env_file: str = "",
                          default_runner: str | None = None,
                          mcp_server_cmd: list[str] | None = None,
                          # Legacy params kept for backward compat
                          port: int = 6667, tls: bool = False,
                          password: str = "",
                          default_type: str = "claude"):
    """Create project directory and write config.toml + empty routing.toml."""
    from zchat.cli.routing import init_routing
    pdir = paths.project_dir(name)
    pdir.mkdir(parents=True, exist_ok=True)
    text = generate_default_config(
        name, server=server, nick=nick, channels=channels,
        env_file=env_file, default_runner=default_runner,
        mcp_server_cmd=mcp_server_cmd,
    )
    (pdir / "config.toml").write_text(text)
    init_routing(pdir)


def list_projects() -> list[str]:
    pdir = paths.projects_dir()
    if not pdir.is_dir():
        return []
    return sorted(d.name for d in pdir.iterdir() if d.is_dir())


def get_default_project() -> str | None:
    default_file = paths.default_project_file()
    if default_file.is_file():
        return default_file.read_text().strip() or None
    return None


def set_default_project(name: str):
    paths.zchat_home().mkdir(parents=True, exist_ok=True)
    paths.default_project_file().write_text(name)


def resolve_project(explicit: str | None = None) -> str | None:
    """Resolve project: explicit > .zchat file > default."""
    if explicit:
        return explicit
    path = Path.cwd()
    while path != path.parent:
        marker = path / ".zchat"
        if marker.is_file():
            return marker.read_text().strip() or None
        path = path.parent
    return get_default_project()


def load_project_config(name: str) -> dict:
    """Load and validate project config.toml (new format only).

    Old-format configs (with [irc]/[tmux] sections) are rejected with a
    clear error message asking the user to recreate the project.
    """
    config_path = paths.project_config(name)
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)

    if "irc" in cfg or "tmux" in cfg:
        raise SystemExit(
            f"Error: Project '{name}' uses old config format.\n"
            f"Please delete and recreate:\n"
            f"  zchat project remove {name} && zchat project create {name}"
        )

    from zchat.cli.defaults import default_channels, default_runner, default_mcp_server_cmd
    cfg.setdefault("server", "local")
    cfg.setdefault("default_runner", default_runner())
    cfg.setdefault("default_channels", default_channels())
    cfg.setdefault("username", "")
    cfg.setdefault("env_file", "")
    cfg.setdefault("mcp_server_cmd", default_mcp_server_cmd())
    cfg.setdefault("zellij", {})
    cfg["zellij"].setdefault("session", _generate_session_name(name))
    cfg.setdefault("channel_server", _channel_server_defaults())
    return cfg


def remove_project(name: str):
    """Remove project directory."""
    pdir = paths.project_dir(name)
    if pdir.is_dir():
        shutil.rmtree(pdir)


def state_file_path(name: str) -> str:
    """Return path to project state.json."""
    return str(paths.project_state(name))


def set_config_value(name: str, key: str, value: str):
    """Set a dotted key in project config.toml. e.g., 'agents.default_type' = 'codex'."""
    config_path = paths.project_config(name)
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


# ---------------------------------------------------------------------------
# Channel name helper (纯工具函数，保留向后兼容)
# ---------------------------------------------------------------------------

def normalize_channel_name(name: str) -> str:
    """Ensure channel name starts with '#'."""
    if not name.startswith("#"):
        return f"#{name}"
    return name
