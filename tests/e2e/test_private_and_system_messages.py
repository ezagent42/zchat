"""E2E coverage for private and system-message IRC paths."""

from __future__ import annotations

import json

import pytest


@pytest.mark.e2e
@pytest.mark.order(0)
def test_direct_private_message_between_users(irc_probe, bob_probe):
    """Bob can send a direct PRIVMSG to another user nick."""
    target_nick = irc_probe.nick  # default: e2e-probe
    message = "dm-check-from-bob"
    bob_probe.privmsg(target_nick, message)

    received = irc_probe.wait_for_message(message, timeout=10)
    assert received is not None, "direct private message not received"
    assert received["nick"] == "bob"
    # IrcProbe records PRIVMSG-to-user with channel=None.
    assert received["channel"] is None


@pytest.mark.e2e
@pytest.mark.order(0)
def test_system_message_prefix_roundtrip_on_irc(irc_probe, bob_probe):
    """`__zchat_sys:` payload is preserved over IRC transport."""
    payload = {
        "type": "sys.status_response",
        "ok": True,
        "sender": "bob",
    }
    wire_msg = "__zchat_sys:" + json.dumps(payload, separators=(",", ":"))
    bob_probe.privmsg("#general", wire_msg)

    received = irc_probe.wait_for_message(r"__zchat_sys:", timeout=10)
    assert received is not None, "system message with __zchat_sys prefix not observed"
    assert received["nick"] == "bob"
    assert received["channel"] == "#general"
    assert "__zchat_sys:" in received["text"]
    assert '"type":"sys.status_response"' in received["text"]
