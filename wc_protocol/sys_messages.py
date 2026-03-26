"""System message protocol for machine-to-machine control over IRC PRIVMSG."""

from __future__ import annotations
import json
import os
import time

SYS_PREFIX = "sys."
IRC_SYS_PREFIX = "__wc_sys:"


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


def encode_sys_for_irc(msg: dict) -> str:
    """Encode a sys message for IRC PRIVMSG transport."""
    return f"{IRC_SYS_PREFIX}{json.dumps(msg)}"


def decode_sys_from_irc(text: str) -> dict | None:
    """Decode a sys message from IRC PRIVMSG. Returns None if not a sys message."""
    if not text.startswith(IRC_SYS_PREFIX):
        return None
    try:
        return json.loads(text[len(IRC_SYS_PREFIX):])
    except json.JSONDecodeError:
        return None
