"""Thin Zellij CLI helpers shared across CLI modules."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile


def _run(args: list[str], session: str | None = None, **kwargs) -> subprocess.CompletedProcess:
    """Run a zellij action command."""
    cmd = ["zellij"]
    if session:
        cmd += ["--session", session]
    cmd += ["action"] + args
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def _run_global(args: list[str], session: str | None = None, **kwargs) -> subprocess.CompletedProcess:
    """Run a top-level zellij command (not action)."""
    cmd = ["zellij"]
    if session:
        cmd += ["--session", session]
    cmd += args
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def ensure_session(name: str, layout_path: str | None = None) -> str:
    """Create or verify session exists. Returns session name."""
    if session_exists(name):
        return name
    if layout_path:
        _run_global(["--new-session-with-layout", layout_path, "--session", name])
    else:
        _run_global(["attach", "--create-background", name])
    return name


def session_exists(name: str) -> bool:
    """Check if a Zellij session exists."""
    r = subprocess.run(["zellij", "list-sessions"], capture_output=True, text=True)
    if r.returncode != 0:
        return False
    return any(line.strip().startswith(name) for line in r.stdout.splitlines())


def new_tab(session: str, name: str, command: str | None = None, cwd: str | None = None) -> str:
    """Create a new tab. Returns tab name."""
    args = ["new-tab", "--name", name]
    if cwd:
        args += ["--cwd", cwd]
    if command:
        args += ["--", "bash", "-c", command]
    _run(args, session=session)
    return name


def close_tab(session: str, tab_name: str) -> None:
    """Close tab by navigating to it then closing."""
    _run(["go-to-tab-name", tab_name], session=session)
    _run(["close-tab"], session=session)


def list_tabs(session: str) -> list[dict]:
    """list-tabs --json, return tab/pane info."""
    r = _run(["list-tabs", "--json"], session=session)
    if r.returncode != 0:
        return []
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return []


def list_panes(session: str | None = None) -> list[dict]:
    """list-panes --all --json."""
    r = _run(["list-panes", "--all", "--json"], session=session)
    if r.returncode != 0:
        return []
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return []


def send_command(session: str, pane_id: str, text: str) -> None:
    """Send text to pane using paste + send-keys Enter."""
    _run(["paste", "--pane-id", pane_id, text], session=session)
    _run(["send-keys", "--pane-id", pane_id, "Enter"], session=session)


def send_keys(session: str, pane_id: str, keys: str) -> None:
    """Send special keys (Enter, Ctrl-C, etc.)."""
    _run(["send-keys", "--pane-id", pane_id, keys], session=session)


def dump_screen(session: str, pane_id: str, full: bool = False) -> str:
    """Dump pane screen to /dev/shm (or tempfile on macOS), return content."""
    # macOS doesn't have /dev/shm
    dump_dir = "/dev/shm" if os.path.isdir("/dev/shm") else tempfile.gettempdir()
    dump_file = os.path.join(dump_dir, f"zj-{session}-{pane_id.replace('/', '_')}.txt")
    args = ["dump-screen", "--pane-id", pane_id, dump_file]
    if full:
        args.insert(1, "--full")  # --full before --pane-id
    _run(args, session=session)
    try:
        with open(dump_file) as f:
            content = f.read()
        os.unlink(dump_file)
        return content
    except FileNotFoundError:
        return ""


def subscribe_pane(session: str, pane_id: str) -> subprocess.Popen:
    """Start subscribe process, return Popen for streaming reads."""
    return subprocess.Popen(
        ["zellij", "--session", session, "subscribe",
         "--pane-id", pane_id, "--format", "json"],
        stdout=subprocess.PIPE, text=True,
    )


def tab_exists(session: str, tab_name: str) -> bool:
    """Check if tab exists via list-panes."""
    panes = list_panes(session)
    return any(p.get("tab_name") == tab_name for p in panes)


def get_pane_id(session: str, tab_name: str) -> str | None:
    """Get terminal pane ID for a tab. Returns 'terminal_N' format."""
    panes = list_panes(session)
    for p in panes:
        if p.get("tab_name") == tab_name and not p.get("is_plugin"):
            return f"terminal_{p['id']}"
    return None


def go_to_tab(session: str, tab_name: str) -> None:
    """Switch to a tab by name."""
    _run(["go-to-tab-name", tab_name], session=session)


def switch_session(name: str) -> None:
    """Switch to another session (must be called from within Zellij)."""
    _run(["switch-session", name])


def kill_session(name: str) -> None:
    """Kill a Zellij session."""
    _run_global(["kill-session", name])
