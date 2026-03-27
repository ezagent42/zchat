# tests/e2e/test_e2e.py
"""E2E tests — each phase is a separate test, ordered by pytest-order."""

import pytest


@pytest.mark.e2e
@pytest.mark.order(1)
def test_weechat_connects(irc_probe, weechat_pane):
    """Phase 1: zchat irc start → WeeChat connects to IRC."""
    assert irc_probe.wait_for_nick("alice", timeout=30), "alice not on IRC"


@pytest.mark.e2e
@pytest.mark.order(2)
def test_agent_joins_irc(zchat_cli, irc_probe):
    """Phase 2: zchat agent create agent0 → agent joins IRC."""
    zchat_cli("agent", "create", "agent0")
    assert irc_probe.wait_for_nick("alice-agent0", timeout=30), "agent0 not on IRC"


@pytest.mark.e2e
@pytest.mark.order(3)
def test_agent_send_to_channel(zchat_cli, irc_probe):
    """Phase 3: zchat agent send → agent replies to #general."""
    zchat_cli("agent", "send", "agent0",
             'Use the reply MCP tool to send "Hello from agent0!" to #general')
    msg = irc_probe.wait_for_message("Hello from agent0", timeout=30)
    assert msg is not None, "agent0 message not received in #general"
    assert msg["nick"] == "alice-agent0"


@pytest.mark.e2e
@pytest.mark.order(4)
def test_mention_triggers_reply(irc_probe, weechat_pane, tmux_send):
    """Phase 4: @mention in WeeChat → agent auto-responds."""
    tmux_send(weechat_pane, "@alice-agent0 what is 2+2?")
    reply = irc_probe.wait_for_message("alice-agent0", timeout=30)
    assert reply is not None, "agent0 did not respond to @mention"


@pytest.mark.e2e
@pytest.mark.order(5)
def test_second_agent(zchat_cli, irc_probe):
    """Phase 5: Create agent1, send message to #general."""
    zchat_cli("agent", "create", "agent1")
    assert irc_probe.wait_for_nick("alice-agent1", timeout=30), "agent1 not on IRC"
    zchat_cli("agent", "send", "agent1",
             'Use the reply MCP tool to send "hello from agent1" to #general')
    msg = irc_probe.wait_for_message("agent1", timeout=30)
    assert msg is not None, "agent1 message not received"


@pytest.mark.e2e
@pytest.mark.order(6)
def test_agent_to_agent(zchat_cli, irc_probe):
    """Phase 6: agent0 sends message mentioning agent1 in #general."""
    zchat_cli("agent", "send", "agent0",
             'Use the reply MCP tool to send "hey @alice-agent1 are you there?" to #general')
    msg = irc_probe.wait_for_message("alice-agent1", timeout=30)
    assert msg is not None, "agent0 message mentioning agent1 not seen in #general"


@pytest.mark.e2e
@pytest.mark.order(7)
def test_agent_stop(zchat_cli, irc_probe):
    """Phase 7: zchat agent stop → agent leaves IRC."""
    zchat_cli("agent", "stop", "agent1")
    assert irc_probe.wait_for_nick_gone("alice-agent1", timeout=10), "agent1 still on IRC"


@pytest.mark.e2e
@pytest.mark.order(8)
def test_shutdown(zchat_cli, irc_probe):
    """Phase 8: zchat shutdown → all agents gone."""
    zchat_cli("shutdown")
    assert irc_probe.wait_for_nick_gone("alice-agent0", timeout=10), "agent0 still on IRC"
