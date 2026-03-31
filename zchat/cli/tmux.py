"""Thin libtmux helpers shared across CLI modules."""
from __future__ import annotations

import libtmux
from libtmux import Pane, Session, Window


_server: libtmux.Server | None = None


def server() -> libtmux.Server:
    """Return (and cache) the libtmux Server singleton."""
    global _server
    if _server is None:
        _server = libtmux.Server()
    return _server


def get_or_create_session(name: str) -> Session:
    """Get an existing tmux session by name, or create a new detached one."""
    s = server()
    session = s.sessions.get(session_name=name, default=None)
    if session is not None:
        return session
    return s.new_session(session_name=name, detach=True)


def get_session(name: str) -> Session:
    """Look up a tmux session by name. Raises KeyError if not found."""
    session = server().sessions.get(session_name=name, default=None)
    if session is None:
        raise KeyError(f"tmux session not found: {name}")
    return session


def find_pane(session: Session, pane_id: str) -> Pane | None:
    """Find a pane by ID within a session. Returns None if gone."""
    for window in session.windows:
        for pane in window.panes:
            if pane.pane_id == pane_id:
                return pane
    return None


def pane_alive(session: Session, pane_id: str) -> bool:
    """Check if a pane still exists in the session."""
    return find_pane(session, pane_id) is not None


def find_window(session: Session, window_name: str) -> Window | None:
    """Find a window by name within a session. Returns None if not found."""
    for window in session.windows:
        if window.window_name == window_name:
            return window
    return None


def window_alive(session: Session, window_name: str) -> bool:
    """Check if a window still exists in the session."""
    return find_window(session, window_name) is not None
