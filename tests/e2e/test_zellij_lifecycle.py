"""E2E tests for Zellij tab lifecycle.

Requires: zellij installed and available in PATH.
Run with: uv run pytest tests/e2e/test_zellij_lifecycle.py -v -m e2e
"""
from __future__ import annotations

import time

import pytest

from zchat.cli import zellij

SESSION = "zchat-test-e2e"


@pytest.fixture(autouse=True)
def zj_session():
    """Create a throwaway Zellij session for testing, clean up after."""
    # Clean any stale session first
    try:
        zellij.kill_session(SESSION)
        time.sleep(1)
    except Exception:
        pass
    # Delete EXITED session if it exists
    import subprocess
    subprocess.run(["zellij", "delete-session", SESSION], capture_output=True)
    time.sleep(0.5)

    zellij.ensure_session(SESSION)
    time.sleep(2)  # Give Zellij time to fully initialize
    yield SESSION
    try:
        zellij.kill_session(SESSION)
    except Exception:
        pass


@pytest.mark.e2e
def test_tab_create_exists_close():
    """Tab lifecycle: create, verify exists, close, verify gone."""
    zellij.new_tab(SESSION, "test-tab", command="sleep 300")
    time.sleep(1)
    assert zellij.tab_exists(SESSION, "test-tab"), "Tab should exist after creation"

    zellij.close_tab(SESSION, "test-tab")
    time.sleep(1)
    assert not zellij.tab_exists(SESSION, "test-tab"), "Tab should be gone after close"


@pytest.mark.e2e
def test_send_and_read():
    """Send command to pane and read output via dump-screen."""
    zellij.new_tab(SESSION, "echo-tab")
    time.sleep(1)
    pane_id = zellij.get_pane_id(SESSION, "echo-tab")
    assert pane_id is not None, "Should find pane ID for new tab"

    zellij.send_command(SESSION, pane_id, "echo HELLO_ZELLIJ_E2E")
    time.sleep(2)
    screen = zellij.dump_screen(SESSION, pane_id)
    assert "HELLO_ZELLIJ_E2E" in screen, f"Expected output in screen dump, got: {screen[:200]}"

    zellij.close_tab(SESSION, "echo-tab")


@pytest.mark.e2e
def test_list_tabs_returns_data():
    """list_tabs should return tab information."""
    zellij.new_tab(SESSION, "info-tab", command="sleep 300")
    time.sleep(1)
    tabs = zellij.list_tabs(SESSION)
    assert len(tabs) > 0, "Should have at least one tab"
    zellij.close_tab(SESSION, "info-tab")


@pytest.mark.e2e
def test_session_exists():
    """session_exists should return True for our test session."""
    assert zellij.session_exists(SESSION)
    assert not zellij.session_exists("zchat-nonexistent-session-xyz")
