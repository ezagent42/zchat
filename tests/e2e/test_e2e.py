# tests/e2e/test_e2e.py

import pytest
import time


@pytest.mark.e2e
def test_full_e2e_lifecycle(wc_agent, irc_probe, weechat_pane, tmux_send):
    """Full e2e test — sequential phases matching real user workflow."""

    # Phase 1: WeeChat connected
    assert irc_probe.wait_for_nick("alice", timeout=15), \
        f"alice not on IRC after irc start. Probe nick_exists test: {irc_probe.nick_exists('alice')}"

    # Phase 2: Create agent0 — joins IRC
    wc_agent("agent", "create", "agent0")
    assert irc_probe.wait_for_nick("alice-agent0", timeout=15), "agent0 not on IRC"

    # Phase 3: agent send — agent replies to channel
    wc_agent("agent", "send", "agent0",
             'Use the reply MCP tool to send "Hello from agent0!" to #general')
    msg = irc_probe.wait_for_message("Hello from agent0", timeout=15)
    assert msg is not None, "agent0 message not received in #general"
    assert msg["nick"] == "alice-agent0"

    # Phase 4: @mention in WeeChat — agent auto-responds
    tmux_send(weechat_pane, "@alice-agent0 what is 2+2?")
    reply = irc_probe.wait_for_message("alice-agent0", timeout=15)
    assert reply is not None, "agent0 did not respond to @mention"

    # Phase 5: Second agent — create, send, verify
    wc_agent("agent", "create", "agent1")
    assert irc_probe.wait_for_nick("alice-agent1", timeout=15), "agent1 not on IRC"
    wc_agent("agent", "send", "agent1",
             'Use the reply MCP tool to send "hello from agent1" to #general')
    msg1 = irc_probe.wait_for_message("agent1", timeout=15)
    assert msg1 is not None, "agent1 message not received"

    # Phase 6: Stop agent1 — leaves IRC
    wc_agent("agent", "stop", "agent1")
    assert irc_probe.wait_for_nick_gone("alice-agent1", timeout=10), "agent1 still on IRC after stop"

    # Phase 7: Shutdown — all agents + WeeChat gone
    wc_agent("shutdown")
    assert irc_probe.wait_for_nick_gone("alice-agent0", timeout=10), "agent0 still on IRC after shutdown"
