"""Agent naming conventions."""

AGENT_SEPARATOR = "-"


def scoped_name(name: str, username: str) -> str:
    """Add username prefix to agent name if not already scoped.
    'helper' + 'alice' → 'alice-helper'
    'alice-helper' + 'alice' → 'alice-helper' (no change)
    """
    if AGENT_SEPARATOR in name:
        return name
    return f"{username}{AGENT_SEPARATOR}{name}"
