# zchat/cli/paths.py
"""Centralized path resolution for zchat.

All path accessors live here. Resolution priority for overridable paths:
    environment variable  >  config.toml [paths]  >  defaults.toml [paths]
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def zchat_home() -> Path:
    """Root zchat directory. Override with $ZCHAT_HOME."""
    return Path(os.environ.get("ZCHAT_HOME", "~/.zchat")).expanduser()


def _resolve_subdir(env_var: str, key: str) -> Path:
    """Resolve a sub-directory path using env var > config > defaults."""
    env_val = os.environ.get(env_var)
    if env_val:
        return Path(env_val).expanduser()

    # Try global config.toml [paths] section
    cfg_paths = _load_config_paths()
    if key in cfg_paths:
        val = cfg_paths[key]
        p = Path(val)
        return p if p.is_absolute() else zchat_home() / p

    # Fall back to defaults.toml [paths]
    default = _load_default_paths().get(key, key)
    return zchat_home() / default


def _load_config_paths() -> dict:
    """Load [paths] from global config.toml. Returns empty dict if missing."""
    config_path = zchat_home() / "config.toml"
    if not config_path.is_file():
        return {}
    import tomllib
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    return data.get("paths", {})


@lru_cache(maxsize=1)
def _load_default_paths() -> dict:
    """Load [paths] from defaults.toml."""
    from zchat.cli.defaults import load_defaults
    return load_defaults().get("paths", {})


# ---------------------------------------------------------------------------
# Top-level directories
# ---------------------------------------------------------------------------

def plugins_dir() -> Path:
    """Plugin WASM directory. Override with $ZCHAT_PLUGINS_DIR."""
    return _resolve_subdir("ZCHAT_PLUGINS_DIR", "plugins")


def templates_dir() -> Path:
    """User template directory. Override with $ZCHAT_TEMPLATES_DIR."""
    return _resolve_subdir("ZCHAT_TEMPLATES_DIR", "templates")


def projects_dir() -> Path:
    """Directory containing all projects."""
    default = _load_default_paths().get("projects", "projects")
    return zchat_home() / default


# ---------------------------------------------------------------------------
# Global files
# ---------------------------------------------------------------------------

def global_config_path() -> Path:
    """Global config.toml."""
    return zchat_home() / "config.toml"


def update_state() -> Path:
    """Update check state file."""
    return zchat_home() / "update.json"


def default_project_file() -> Path:
    """File storing the default project name."""
    return zchat_home() / "default"


# ---------------------------------------------------------------------------
# Per-project paths
# ---------------------------------------------------------------------------

def project_dir(name: str) -> Path:
    """Root directory for a project."""
    return projects_dir() / name


def project_config(name: str) -> Path:
    """Project config.toml."""
    return project_dir(name) / "config.toml"


def project_state(name: str) -> Path:
    """Project runtime state.json."""
    return project_dir(name) / "state.json"


def project_env_file(name: str) -> Path:
    """Per-project Claude environment file."""
    return project_dir(name) / "claude.local.env"


def ergo_data_dir(name: str) -> Path:
    """Per-project ergo IRC daemon data directory."""
    return project_dir(name) / "ergo"


def weechat_home(name: str) -> Path:
    """Per-project WeeChat config directory."""
    return project_dir(name) / ".weechat"


def zellij_layout_dir() -> Path:
    """Directory for Zellij layout files."""
    return zchat_home() / "main"


# ---------------------------------------------------------------------------
# Agent paths
# ---------------------------------------------------------------------------

def agent_workspace(project: str, agent: str) -> Path:
    """Agent workspace directory within a project."""
    return project_dir(project) / "agents" / agent


def agent_ready_marker(project: str, agent: str) -> Path:
    """Agent startup ready marker file."""
    return project_dir(project) / "agents" / f"{agent}.ready"


