"""Global configuration management (~/.zchat/config.toml)."""
from __future__ import annotations

import os
import tomllib
import tomli_w

from zchat.cli.project import ZCHAT_DIR

_GLOBAL_CONFIG = os.path.join(ZCHAT_DIR, "config.toml")

_DEFAULTS = {
    "update": {
        "channel": "main",
        "auto_upgrade": True,
    },
}


def load_global_config(path: str = _GLOBAL_CONFIG) -> dict:
    """Load global config, filling defaults for missing keys."""
    data: dict = {}
    if os.path.isfile(path):
        with open(path, "rb") as f:
            data = tomllib.load(f)
    for section, defaults in _DEFAULTS.items():
        data.setdefault(section, {})
        for key, value in defaults.items():
            data[section].setdefault(key, value)
    return data


def save_global_config(config: dict, path: str = _GLOBAL_CONFIG) -> None:
    """Write global config to TOML file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(config, f)


def get_config_value(config: dict, dotted_key: str):
    """Get a value from config by dotted key (e.g. 'update.channel')."""
    parts = dotted_key.split(".")
    node = config
    for part in parts:
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def set_config_value(config: dict, dotted_key: str, value: str | int | bool | list) -> None:
    """Set a value in config by dotted key. Auto-converts 'true'/'false' to bool when value is str."""
    parts = dotted_key.split(".")
    node = config
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    if isinstance(value, str):
        if value.lower() in ("true", "false"):
            node[parts[-1]] = value.lower() == "true"
        else:
            node[parts[-1]] = value
    else:
        node[parts[-1]] = value
