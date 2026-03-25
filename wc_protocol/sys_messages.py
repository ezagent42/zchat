# wc_protocol/sys_messages.py
"""System message protocol for machine-to-machine control over Zenoh."""

from __future__ import annotations
import os
import time

SYS_PREFIX = "sys."


def _random_hex(n: int) -> str:
    return os.urandom(n // 2 + 1).hex()[:n]


def is_sys_message(msg: dict) -> bool:
    """Check if a message is a system control message."""
    return msg.get("type", "").startswith(SYS_PREFIX)


def make_sys_message(nick: str, type: str, body: dict, ref_id: str | None = None) -> dict:
    """Create a system message. Caller provides nick."""
    return {
        "id": _random_hex(8),
        "nick": nick,
        "type": type,
        "body": body,
        "ref_id": ref_id,
        "ts": time.time(),
    }
