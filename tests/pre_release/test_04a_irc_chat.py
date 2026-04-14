# tests/pre_release/test_04a_irc_chat.py
"""Pre-release: IRC user-to-user communication verification.

Verifies that two IRC clients can exchange messages in #general via the
ergo IRC server managed by zchat.  Uses fresh IrcProbe instances (not
the session-scoped ones) to avoid stale-connection issues after the
long-running agent tests.
"""

import os
import re
import time

import pytest

from tests.shared.irc_probe import IrcProbe


def _irc_nick() -> str:
    """Return the sanitized IRC nick matching what zchat auth stores."""
    raw = os.environ.get("USER", "user")
    nick = re.sub(r"[^A-Za-z0-9\-_\\\[\]\{\}\^|]", "", raw)
    nick = nick.lstrip("0123456789-")
    return nick or "user"


@pytest.mark.order(1)
def test_alice_bob_channel_message(ergo_server):
    """Alice and bob exchange messages in #general via fresh IRC probes."""
    host, port = ergo_server["host"], ergo_server["port"]
    # Use unique nicks to avoid collisions with session-scoped fixtures
    # (irc_probe="e2e-probe", bob_probe="bob") that are still connected.
    alice = IrcProbe(host, port, nick="chatalice")
    bob = IrcProbe(host, port, nick="chatbob")
    alice.connect()
    bob.connect()
    time.sleep(1)
    alice.join("#general")
    bob.join("#general")
    time.sleep(1)

    try:
        # Bob sends to #general, alice should see it
        bob.privmsg("#general", "Hello from bob")
        msg = alice.wait_for_message("Hello from bob", timeout=10)
        assert msg is not None, "bob's message not seen by alice"
        assert msg["nick"] == "chatbob"

        # Alice sends to #general, bob should see it
        alice.privmsg("#general", "Hello from alice")
        msg = bob.wait_for_message("Hello from alice", timeout=10)
        assert msg is not None, "alice's message not seen by bob"
        assert msg["nick"] == "chatalice"
    finally:
        alice.disconnect()
        bob.disconnect()
