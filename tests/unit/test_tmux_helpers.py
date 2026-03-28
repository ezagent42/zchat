"""Tests for zchat.cli.tmux helpers — run inside a real tmux session."""
import subprocess
import os
import pytest

# Skip entire module if not inside tmux
pytestmark = pytest.mark.skipif(
    not os.environ.get("TMUX") and not os.environ.get("ZCHAT_TMUX_SESSION"),
    reason="requires tmux",
)


@pytest.fixture(scope="module")
def tmux_env():
    """Create a throwaway tmux session for testing."""
    name = f"test-helpers-{os.getpid()}"
    subprocess.run(["tmux", "new-session", "-d", "-s", name, "-x", "80", "-y", "24"])
    yield name
    subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)


def test_get_session_returns_session(tmux_env):
    from zchat.cli.tmux import get_session
    session = get_session(tmux_env)
    assert session.session_name == tmux_env


def test_get_session_raises_on_missing():
    from zchat.cli.tmux import get_session
    with pytest.raises(KeyError):
        get_session("nonexistent-session-xyz")


def test_find_pane_returns_pane(tmux_env):
    from zchat.cli.tmux import get_session, find_pane
    session = get_session(tmux_env)
    pane = session.active_window.active_pane
    found = find_pane(session, pane.pane_id)
    assert found.pane_id == pane.pane_id


def test_find_pane_returns_none_for_missing(tmux_env):
    from zchat.cli.tmux import get_session, find_pane
    session = get_session(tmux_env)
    assert find_pane(session, "%99999") is None


def test_pane_alive(tmux_env):
    from zchat.cli.tmux import get_session, pane_alive
    session = get_session(tmux_env)
    pane = session.active_window.active_pane
    assert pane_alive(session, pane.pane_id) is True
    assert pane_alive(session, "%99999") is False
