# tests/pre_release/test_04b_remote_irc.py
"""Pre-release: remote IRC (TLS+SASL) connection and nick verification.

Validates that TLS+SASL authentication preserves the requested nickname
(the scoped name), rather than overriding it with the OIDC username.
This is the key regression test for the credentials-vs-nickname bug.
"""

import pytest


REMOTE_HOST = "zchat.inside.h2os.cloud"
REMOTE_PORT = 6697


def _skip_if_no_remote(remote_irc_probe):
    if remote_irc_probe is None:
        pytest.skip(f"Remote ergo ({REMOTE_HOST}:{REMOTE_PORT}) not reachable or no OIDC credentials")


@pytest.mark.order(1)
def test_remote_irc_connect(remote_irc_probe):
    """Remote ergo is reachable and SASL authentication succeeds."""
    _skip_if_no_remote(remote_irc_probe)
    assert remote_irc_probe._conn is not None
    assert remote_irc_probe._conn.connected


@pytest.mark.order(2)
def test_remote_nick_preserved_after_sasl(remote_irc_probe):
    """SASL authentication preserves the scoped nick, not the OIDC username.

    The probe connects as {username}-probe with SASL login={username}-probe.
    After SASL, ergo should keep this nick — not override it to {username}.
    This validates the same flow agents use ({username}-agent0).
    """
    _skip_if_no_remote(remote_irc_probe)
    actual_nick = remote_irc_probe._conn.real_nickname
    expected_nick = remote_irc_probe.nick  # {username}-probe
    assert actual_nick == expected_nick, (
        f"Nick was changed after SASL auth: expected='{expected_nick}' "
        f"actual='{actual_nick}'. This indicates ergo is overriding the nick "
        f"with the SASL account name."
    )
