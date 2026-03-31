# tests/shared/tmux_helpers.py
"""Tmux helper functions shared across test suites."""
import re
import time

from zchat.cli.tmux import get_session, find_window, find_pane


def send_keys(session_name: str, target: str, text: str, enter: bool = True) -> None:
    """Send keys to a tmux window (by name) or pane (by ID)."""
    session = get_session(session_name)
    window = find_window(session, target)
    if window and window.active_pane:
        window.active_pane.send_keys(text, enter=enter)
        return
    pane = find_pane(session, target)
    if pane:
        pane.send_keys(text, enter=enter)


def capture_pane(session_name: str, target: str) -> str:
    """Capture the visible content of a tmux window or pane."""
    session = get_session(session_name)
    window = find_window(session, target)
    if window and window.active_pane:
        return "\n".join(window.active_pane.capture_pane())
    pane = find_pane(session, target)
    if pane:
        return "\n".join(pane.capture_pane())
    return ""


def wait_for_content(session_name: str, target: str, pattern: str,
                     timeout: float = 10.0) -> bool:
    """Wait until pane content matches a regex pattern."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        content = capture_pane(session_name, target)
        if re.search(pattern, content):
            return True
        time.sleep(0.5)
    return False
