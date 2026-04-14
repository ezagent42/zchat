# tests/pre_release/test_04_agent.py
"""Pre-release: agent lifecycle management."""
import os
import re

import pytest


def _irc_nick() -> str:
    """Return the sanitized IRC nick matching what zchat auth stores."""
    raw = os.environ.get("USER", "user")
    nick = re.sub(r"[^A-Za-z0-9\-_\\\[\]\{\}\^|]", "", raw)
    nick = nick.lstrip("0123456789-")
    return nick or "user"


@pytest.mark.order(1)
def test_agent_create(cli, irc_probe, ergo_server):
    """Create agent0, verify it joins IRC."""
    result = cli("agent", "create", "agent0")
    assert result.returncode == 0, f"agent create failed: {result.stderr}"
    username = _irc_nick()
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


def _capture_agent_pane(username):
    """Capture agent tmux pane content for debugging."""
    import subprocess
    agent_window = f"{username}-agent0"
    try:
        # Search ALL sessions for the agent window
        sessions = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, timeout=5)
        for sess in sessions.stdout.strip().split("\n"):
            # Try to capture — if window doesn't exist in this session, it fails silently
            cap = subprocess.run(
                ["tmux", "capture-pane", "-t", f"{sess}:{agent_window}", "-p", "-S", "-80"],
                capture_output=True, text=True, timeout=5)
            if cap.returncode == 0 and cap.stdout.strip():
                return cap.stdout
    except Exception:
        pass
    return None


@pytest.mark.order(4)
def test_agent_send(cli, irc_probe):
    """Send message via agent0 to #general."""
    username = _irc_nick()

    msg = None
    for attempt in range(3):
        result = cli("agent", "send", "agent0",
            'Use the reply MCP tool to send "prerelease-test-msg" to #general',
            check=False)
        if result.returncode != 0:
            print(f"[DEBUG] send attempt {attempt+1} failed: {result.stderr}")
            continue
        msg = irc_probe.wait_for_message("prerelease-test-msg", timeout=60)
        if msg is not None:
            break
        # Capture after each failed wait
        pane = _capture_agent_pane(username)
        if pane:
            print(f"[DEBUG] agent pane after attempt {attempt+1}:\n{pane}")

    assert msg is not None, "agent0 message not received in #general after 3 attempts"


@pytest.mark.order(5)
def test_agent_focus_hide(cli):
    """agent focus/hide switch zellij tabs without error."""
    result = cli("agent", "focus", "agent0", check=False)
    assert result.returncode == 0, f"agent focus failed: {result.stderr}"
    result = cli("agent", "hide", "agent0", check=False)
    assert result.returncode == 0, f"agent hide failed: {result.stderr}"


@pytest.mark.order(6)
def test_agent_create_second(cli, irc_probe):
    """Create agent1."""
    cli("agent", "create", "agent1")
    username = _irc_nick()
    assert irc_probe.wait_for_nick(
        f"{username}-agent1", timeout=30
    ), "agent1 not on IRC"


@pytest.mark.order(7)
def test_agent_restart(cli, irc_probe):
    """Restart agent1, verify it re-joins IRC."""
    cli("agent", "restart", "agent1")
    username = _irc_nick()
    assert irc_probe.wait_for_nick(
        f"{username}-agent1", timeout=30
    ), "agent1 not back on IRC after restart"


@pytest.mark.order(8)
def test_agent_stop(cli, irc_probe):
    """Stop agent1, verify it leaves IRC."""
    cli("agent", "stop", "agent1")
    username = _irc_nick()
    assert irc_probe.wait_for_nick_gone(
        f"{username}-agent1", timeout=10
    ), "agent1 still on IRC after stop"


@pytest.mark.order(9)
def test_agent_list_after_stop(cli):
    """agent list shows agent1 after stop."""
    result = cli("agent", "list")
    assert "agent1" in result.stdout
