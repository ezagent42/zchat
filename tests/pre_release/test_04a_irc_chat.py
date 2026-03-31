# tests/pre_release/test_04a_irc_chat.py
"""Pre-release: IRC user-to-user communication verification."""

import pytest


@pytest.mark.order(1)
def test_alice_bob_channel_message(irc_probe, bob_probe, weechat_window, tmux_send):
    """Bob and alice exchange messages in #general."""
    # Bob sends to #general
    bob_probe.privmsg("#general", "Hello from bob")
    msg = irc_probe.wait_for_message("Hello from bob", timeout=10)
    assert msg is not None, "bob's message not seen by probe"
    assert msg["nick"] == "bob"

    # Alice sends to #general via WeeChat (use /msg to avoid buffer-focus issues)
    tmux_send(weechat_window, "/msg #general Hello from alice")
    msg = bob_probe.wait_for_message("Hello from alice", timeout=10)
    assert msg is not None, "alice's message not seen by bob"
    assert msg["nick"] == "alice"
