"""E2E tests for agent DM (IRC PRIVMSG) functionality.

Covers test-plan-004 (confirmed): Agent 间 DM 私聊功能.
Implements TC-001, TC-002, TC-003, TC-006, TC-011.

Deferred (require unimplemented features or complex multi-round interaction):
  TC-004 (agent discovery — needs list_agents MCP tool)
  TC-005 (offline DM — needs _handle_reply error handling fix)
  TC-007 (human vs agent DM — needs WeeChat + agent coordination)
  TC-008 (sys message — needs send_sys_message MCP tool)
  TC-009 (multi-round DM context)
  TC-010 (cross-agent task delegation)

These tests run after the core lifecycle suite (order 100+) and manage
their own agent. IrcProbe / bob_probe serve as DM counterparts — IRC
PRIVMSG does not distinguish agents from regular clients, so the same
reply tool and on_privmsg code paths are exercised.
"""

import time

import pytest


# -- Setup / teardown -------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.order(100)
def test_create_agent_for_dm(zchat_cli, irc_probe):
    """Phase 100: Create agent0 for the DM test suite."""
    result = zchat_cli("agent", "create", "agent0")
    if result.returncode != 0:
        raise RuntimeError(
            f"agent create failed (rc={result.returncode}): "
            f"stdout={result.stdout}, stderr={result.stderr}"
        )
    assert irc_probe.wait_for_nick("alice-agent0", timeout=30), \
        "alice-agent0 not on IRC after create for DM tests"


# -- TC-001: agent sends DM to a nick --------------------------------------

@pytest.mark.e2e
@pytest.mark.order(101)
def test_send_dm_agent_to_nick(zchat_cli, irc_probe):
    """Phase 101: agent0 sends DM to e2e-probe via reply tool -> probe receives PRIVMSG.

    Maps to TC-001 (adapted: agent -> probe instead of agent -> agent).
    Verifies that the reply tool's chat_id parameter works for nick targets.
    """
    marker = f"DM-TEST-{int(time.time())}"
    zchat_cli(
        "agent", "send", "agent0",
        f'Use the reply MCP tool to send exactly "{marker}" to e2e-probe. '
        f'The chat_id parameter should be "e2e-probe", not a channel.',
    )

    msg = irc_probe.wait_for_message(marker, timeout=30)
    assert msg is not None, \
        "agent0 DM not received by e2e-probe within 30s"
    assert msg["nick"] == "alice-agent0", \
        f"DM sender should be alice-agent0, got {msg['nick']}"
    assert msg["channel"] is None, \
        f"DM should be private (channel=None), got channel={msg['channel']}"


# -- TC-002: agent receives DM and remains functional ----------------------

@pytest.mark.e2e
@pytest.mark.order(102)
def test_receive_dm_from_user(zchat_cli, irc_probe, bob_probe):
    """Phase 102: bob sends DM to agent0 -> agent processes it and can still send messages.

    Maps to TC-002. Verifies on_privmsg handler doesn't crash the agent
    and the agent remains functional after receiving an incoming DM.
    """
    bob_probe.privmsg("alice-agent0", "DM from bob: hello agent")
    time.sleep(5)

    # Agent should still be alive on IRC
    assert irc_probe.wait_for_nick("alice-agent0", timeout=10), \
        "alice-agent0 left IRC after receiving DM from bob"

    # Agent should still be able to send messages (functional check)
    marker = f"POST-DM-{int(time.time())}"
    zchat_cli(
        "agent", "send", "agent0",
        f'Use the reply MCP tool to send exactly "{marker}" to #general',
    )
    msg = irc_probe.wait_for_message(marker, timeout=30)
    assert msg is not None, \
        "agent0 could not send to #general after receiving a DM from bob"


# -- TC-003: cross-user DM -------------------------------------------------

@pytest.mark.e2e
@pytest.mark.order(103)
def test_send_dm_cross_user(zchat_cli, bob_probe):
    """Phase 103: agent0 (alice) sends DM to bob -> bob receives PRIVMSG.

    Maps to TC-003. IRC PRIVMSG doesn't enforce user-ownership boundaries,
    so alice-agent0 can DM any nick including those belonging to other users.
    """
    marker = f"CROSS-DM-{int(time.time())}"
    zchat_cli(
        "agent", "send", "agent0",
        f'Use the reply MCP tool to send exactly "{marker}" to bob. '
        f'The chat_id parameter should be "bob".',
    )

    msg = bob_probe.wait_for_message(marker, timeout=30)
    assert msg is not None, \
        "bob did not receive cross-user DM from alice-agent0 within 30s"
    assert msg["nick"] == "alice-agent0", \
        f"Cross-user DM sender should be alice-agent0, got {msg['nick']}"
    assert msg["channel"] is None, \
        f"Cross-user DM should be private (channel=None), got {msg['channel']}"


# -- TC-006: long message DM (auto-chunked) --------------------------------

@pytest.mark.e2e
@pytest.mark.order(104)
def test_send_dm_long_message(zchat_cli, irc_probe):
    """Phase 104: agent0 sends >512-byte DM -> chunk_message splits, probe receives chunks.

    Maps to TC-006. The channel-server's chunk_message() splits text that
    exceeds IRC's 512-byte per-message limit (~390 bytes usable after header).
    We verify at least the first chunk arrives with the expected marker.
    """
    marker = f"LONGDM-{int(time.time())}"
    # 600 chars of padding to ensure the total exceeds 512 bytes
    long_body = "A" * 600
    zchat_cli(
        "agent", "send", "agent0",
        f'Use the reply MCP tool to send the following exact text to e2e-probe '
        f'(chat_id="e2e-probe"): "{marker} {long_body}"',
    )

    msg = irc_probe.wait_for_message(marker, timeout=30)
    assert msg is not None, \
        "e2e-probe did not receive any chunk of the long DM from agent0"
    assert msg["nick"] == "alice-agent0"
    assert msg["channel"] is None, "Long DM should be private (channel=None)"


# -- TC-011: DM @mention does not notify third party -----------------------

@pytest.mark.e2e
@pytest.mark.order(105)
def test_dm_mention_no_notification(zchat_cli, irc_probe, bob_probe):
    """Phase 105: DM containing @bob text does NOT notify bob.

    Maps to TC-011. detect_mention() is only called in on_pubmsg (channel
    messages), never in on_privmsg. A DM from agent0 to e2e-probe that
    mentions @bob should not produce any message to bob.
    """
    with bob_probe._lock:
        bob_baseline = len(bob_probe.messages)

    marker = f"MENTION-DM-{int(time.time())}"
    zchat_cli(
        "agent", "send", "agent0",
        f'Use the reply MCP tool to send exactly '
        f'"{marker} hey @bob do you have write access?" to e2e-probe. '
        f'The chat_id must be "e2e-probe", NOT "#general".',
    )

    # Verify probe received the DM (proves the message was actually sent)
    msg = irc_probe.wait_for_message(marker, timeout=30)
    assert msg is not None, \
        "e2e-probe did not receive the DM containing @bob mention"
    assert msg["channel"] is None, "Should be a DM, not a channel message"

    # Verify bob did NOT receive the DM content
    time.sleep(3)
    with bob_probe._lock:
        new_bob_msgs = [
            m for m in bob_probe.messages[bob_baseline:]
            if marker in m["text"]
        ]
    assert len(new_bob_msgs) == 0, (
        f"bob received {len(new_bob_msgs)} message(s) containing the DM "
        f"@mention marker — expected 0"
    )


# -- Cleanup ----------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.order(109)
def test_shutdown_dm_agents(zchat_cli, irc_probe):
    """Phase 109: Cleanup — shut down agents created for DM tests."""
    zchat_cli("shutdown")
    assert irc_probe.wait_for_nick_gone("alice-agent0", timeout=10), \
        "alice-agent0 still on IRC after DM test shutdown"
