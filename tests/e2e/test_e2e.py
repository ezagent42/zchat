# tests/e2e/test_e2e.py
"""E2E tests — each phase is a separate test, ordered by pytest-order."""

import pytest


@pytest.mark.e2e
@pytest.mark.order(1)
def test_weechat_connects(irc_probe, weechat_pane):
    """Phase 1: wc-agent irc start → WeeChat connects to IRC."""
    assert irc_probe.wait_for_nick("alice", timeout=15), "alice not on IRC"


@pytest.mark.e2e
@pytest.mark.order(2)
def test_agent_joins_irc(wc_agent, irc_probe):
    """Phase 2: wc-agent agent create agent0 → agent joins IRC."""
    wc_agent("agent", "create", "agent0")
    assert irc_probe.wait_for_nick("alice-agent0", timeout=15), "agent0 not on IRC"


@pytest.mark.e2e
@pytest.mark.order(3)
def test_agent_send_to_channel(wc_agent, irc_probe):
    """Phase 3: wc-agent agent send → agent replies to #general."""
    wc_agent("agent", "send", "agent0",
             'Use the reply MCP tool to send "Hello from agent0!" to #general')
    msg = irc_probe.wait_for_message("Hello from agent0", timeout=15)
    assert msg is not None, "agent0 message not received in #general"
    assert msg["nick"] == "alice-agent0"


@pytest.mark.e2e
@pytest.mark.order(4)
def test_mention_triggers_reply(irc_probe, weechat_pane, tmux_send):
    """Phase 4: @mention in WeeChat → agent auto-responds."""
    tmux_send(weechat_pane, "@alice-agent0 what is 2+2?")
    reply = irc_probe.wait_for_message("alice-agent0", timeout=15)
    assert reply is not None, "agent0 did not respond to @mention"


@pytest.mark.e2e
@pytest.mark.order(5)
def test_second_agent(wc_agent, irc_probe):
    """Phase 5: Create agent1, send message to #general."""
    wc_agent("agent", "create", "agent1")
    assert irc_probe.wait_for_nick("alice-agent1", timeout=15), "agent1 not on IRC"
    wc_agent("agent", "send", "agent1",
             'Use the reply MCP tool to send "hello from agent1" to #general')
    msg = irc_probe.wait_for_message("agent1", timeout=15)
    assert msg is not None, "agent1 message not received"


@pytest.mark.e2e
@pytest.mark.order(6)
def test_agent_stop(wc_agent, irc_probe):
    """Phase 6: wc-agent agent stop → agent leaves IRC."""
    wc_agent("agent", "stop", "agent1")
    assert irc_probe.wait_for_nick_gone("alice-agent1", timeout=10), "agent1 still on IRC"


@pytest.mark.e2e
@pytest.mark.order(7)
def test_shutdown(wc_agent, irc_probe):
    """Phase 7: wc-agent shutdown → all agents gone."""
    wc_agent("shutdown")
    assert irc_probe.wait_for_nick_gone("alice-agent0", timeout=10), "agent0 still on IRC"
