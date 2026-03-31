# tests/e2e/test_e2e.py
"""E2E tests — each phase is a separate test, ordered by pytest-order."""

import os
import pytest


@pytest.mark.e2e
@pytest.mark.order(1)
def test_weechat_connects(irc_probe, weechat_window):
    """Phase 1: zchat irc start → WeeChat connects to IRC."""
    assert irc_probe.wait_for_nick("alice", timeout=30), "alice not on IRC"


@pytest.mark.e2e
@pytest.mark.order(2)
def test_agent_joins_irc(zchat_cli, irc_probe, e2e_context):
    """Phase 2: zchat agent create agent0 → agent joins IRC."""
    result = zchat_cli("agent", "create", "agent0")
    if result.returncode != 0:
        raise RuntimeError(f"agent create failed: {result.stderr or result.stdout}")
    # Capture agent workspace + mcp.json for debugging
    import json, glob
    ws_match = [line for line in (result.stdout or "").splitlines() if "workspace:" in line]
    if ws_match:
        ws_path = ws_match[0].split("workspace:")[-1].strip()
        mcp_path = os.path.join(ws_path, ".mcp.json")
        if os.path.isfile(mcp_path):
            with open(mcp_path) as f:
                print(f"[DEBUG] .mcp.json: {json.dumps(json.load(f), indent=2)}")
    if not irc_probe.wait_for_nick("alice-agent0", timeout=30):
        window_name = result.stdout.split("window:")[1].split("\n")[0].strip() if "window:" in result.stdout else ""
        raise AssertionError(f"agent0 not on IRC.\nCLI: {result.stdout}\nWindow: {window_name}")


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
def test_mention_triggers_reply(irc_probe, weechat_window, tmux_send):
    """Phase 4: @mention in WeeChat → agent auto-responds."""
    tmux_send(weechat_window, "@alice-agent0 what is 2+2?")
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
def test_alice_bob_conversation(irc_probe, bob_probe, weechat_window, tmux_send):
    """Phase 7: Two users exchange messages in #general."""
    # Bob sends to #general
    bob_probe.privmsg("#general", "Hello from bob")
    msg = irc_probe.wait_for_message("Hello from bob", timeout=10)
    assert msg is not None, "bob's message not seen by probe"
    assert msg["nick"] == "bob"

    # Alice sends to #general via WeeChat
    tmux_send(weechat_window, "Hello from alice")
    msg = bob_probe.wait_for_message("Hello from alice", timeout=10)
    assert msg is not None, "alice's message not seen by bob"
    assert msg["nick"] == "alice"


@pytest.mark.e2e
@pytest.mark.order(8)
def test_agent_stop(zchat_cli, irc_probe):
    """Phase 8: zchat agent stop → agent leaves IRC."""
    zchat_cli("agent", "stop", "agent1")
    assert irc_probe.wait_for_nick_gone("alice-agent1", timeout=10), "agent1 still on IRC"


@pytest.mark.e2e
@pytest.mark.order(9)
def test_shutdown(zchat_cli, irc_probe):
    """Phase 9: zchat shutdown → all agents gone."""
    zchat_cli("shutdown")
    assert irc_probe.wait_for_nick_gone("alice-agent0", timeout=10), "agent0 still on IRC"
