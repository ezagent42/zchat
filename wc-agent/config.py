# wc-agent/config.py
"""Read weechat-claude.toml configuration."""

import os
import tomllib


def load_config(path: str) -> dict:
    """Load and validate weechat-claude.toml."""
    with open(path, "rb") as f:
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

    return cfg
