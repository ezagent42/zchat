"""Thin libtmux helpers shared across CLI modules."""
from __future__ import annotations

import libtmux
from libtmux import Pane, Session


_server: libtmux.Server | None = None


def server() -> libtmux.Server:
    """Return (and cache) the libtmux Server singleton."""
    global _server
    if _server is None:
        _server = libtmux.Server()
    return _server


def get_session(name: str) -> Session:
    """Look up a tmux session by name. Raises KeyError if not found."""
    try:
        return server().sessions.get(session_name=name)
    except Exception:
        raise KeyError(f"tmux session not found: {name}")


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
