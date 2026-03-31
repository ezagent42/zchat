# tests/pre_release/test_04_agent.py
"""Pre-release: agent lifecycle management."""
import os

import pytest


@pytest.mark.order(1)
def test_agent_create(cli, irc_probe, ergo_server):
    """Create agent0, verify it joins IRC."""
    result = cli("agent", "create", "agent0")
    assert result.returncode == 0, f"agent create failed: {result.stderr}"
    username = os.environ.get("USER", "user")
    assert irc_probe.wait_for_nick(
        f"{username}-agent0", timeout=30
    ), "agent0 not on IRC"


@pytest.mark.order(2)
def test_agent_list(cli):
    """agent list shows agent0 as running."""
    result = cli("agent", "list")
    assert "agent0" in result.stdout
    assert "running" in result.stdout.lower()


@pytest.mark.order(3)
def test_agent_status(cli):
    """agent status shows detailed info for agent0."""
    result = cli("agent", "status", "agent0")
    assert "agent0" in result.stdout
    assert "status" in result.stdout.lower() or "running" in result.stdout.lower()


@pytest.mark.order(4)
def test_agent_send(cli, irc_probe):
    """Send message via agent0 to #general.

    First MCP tool call after agent startup may be slow (Claude Code init).
    Retry up to 2 times if the message isn't received.
    """
    msg = None
    for attempt in range(3):
        result = cli("agent", "send", "agent0",
            'Use the reply MCP tool to send "prerelease-test-msg" to #general',
            check=False)
        print(f"[DEBUG] send attempt {attempt+1}: rc={result.returncode} "
              f"stdout={result.stdout!r} stderr={result.stderr!r}")
        if result.returncode != 0:
            continue
        msg = irc_probe.wait_for_message("prerelease-test-msg", timeout=60)
        if msg is not None:
            break
    assert msg is not None, "agent0 message not received in #general after 3 attempts"


@pytest.mark.order(5)
def test_agent_create_second(cli, irc_probe):
    """Create agent1."""
    cli("agent", "create", "agent1")
    username = os.environ.get("USER", "user")
    assert irc_probe.wait_for_nick(
        f"{username}-agent1", timeout=30
    ), "agent1 not on IRC"


@pytest.mark.order(6)
def test_agent_restart(cli, irc_probe):
    """Restart agent1, verify it re-joins IRC."""
    cli("agent", "restart", "agent1")
    username = os.environ.get("USER", "user")
    assert irc_probe.wait_for_nick(
        f"{username}-agent1", timeout=30
    ), "agent1 not back on IRC after restart"


@pytest.mark.order(7)
def test_agent_stop(cli, irc_probe):
    """Stop agent1, verify it leaves IRC."""
    cli("agent", "stop", "agent1")
    username = os.environ.get("USER", "user")
    assert irc_probe.wait_for_nick_gone(
        f"{username}-agent1", timeout=10
    ), "agent1 still on IRC after stop"


@pytest.mark.order(8)
def test_agent_list_after_stop(cli):
    """agent list shows agent1 after stop."""
    result = cli("agent", "list")
    assert "agent1" in result.stdout
