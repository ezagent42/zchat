"""Thin Zellij CLI helpers shared across CLI modules."""
from __future__ import annotations

import json
import subprocess
import time


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


def ensure_session(name: str, layout: str | None = None, config: str | None = None) -> str:
    """Create or verify session exists. Returns session name.

    Handles EXITED sessions by deleting and recreating them.
    """
    if session_exists(name):
        # Check if session is EXITED — if so, delete and recreate
        if _session_exited(name):
            _run_global(["delete-session", name])
        else:
            return name
    args: list[str] = []
    if config:
        args += ["--config", config]
    if layout:
        args += ["--new-session-with-layout", layout, "--session", name]
        # Build full command — Popen doesn't block like subprocess.run
        full_cmd = ["zellij"] + args
        subprocess.Popen(full_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Wait briefly for session to initialize
        time.sleep(2)
    else:
        args += ["attach", "--create-background", name]
        _run_global(args)
    return name


def _session_exited(name: str) -> bool:
    """Check if a session is in EXITED state."""
    import re as _re
    r = subprocess.run(["zellij", "list-sessions"], capture_output=True, text=True)
    ansi_escape = _re.compile(r"\x1b\[[0-9;]*m")
    for line in r.stdout.splitlines():
        clean = ansi_escape.sub("", line).strip()
        if clean.startswith(name) and "EXITED" in clean:
            return True
    return False


def session_exists(name: str) -> bool:
    """Check if a Zellij session exists."""
    import re as _re
    r = subprocess.run(["zellij", "list-sessions"], capture_output=True, text=True)
    if r.returncode != 0:
        return False
    # Strip ANSI escape codes from output before matching
    ansi_escape = _re.compile(r"\x1b\[[0-9;]*m")
    for line in r.stdout.splitlines():
        clean = ansi_escape.sub("", line).strip()
        if clean.startswith(name):
            return True
    return False


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
    """Close tab by finding its tab_id then closing."""
    panes = list_panes(session)
    tab_id = None
    for p in panes:
        if p.get("tab_name") == tab_name:
            tab_id = p.get("tab_id")
            break
    if tab_id is not None:
        _run(["close-tab", "--tab-id", str(tab_id)], session=session)
    else:
        # Fallback: navigate then close
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
    """list-panes --all --json.

    Zellij 版本间 schema 不统一：可能是 list[dict] 也可能是 {"panes": [...]}。
    非预期 schema 一律返回 [] 以保证下游迭代安全。
    """
    r = _run(["list-panes", "--all", "--json"], session=session)
    if r.returncode != 0:
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict)]
    if isinstance(data, dict):
        inner = data.get("panes") or data.get("items") or []
        if isinstance(inner, list):
            return [p for p in inner if isinstance(p, dict)]
    return []


def send_command(session: str, pane_id: str, text: str) -> None:
    """Send text to pane using write-chars + send-keys Enter."""
    _run(["write-chars", "--pane-id", pane_id, "--", text], session=session)
    _run(["send-keys", "--pane-id", pane_id, "Enter"], session=session)


def send_keys(session: str, pane_id: str, keys: str) -> None:
    """Send special keys (Enter, Ctrl-C, etc.)."""
    _run(["send-keys", "--pane-id", pane_id, keys], session=session)


def dump_screen(session: str, pane_id: str, full: bool = False) -> str:
    """Dump pane screen content. Returns text."""
    args = ["dump-screen", "--pane-id", pane_id]
    if full:
        args.append("--full")
    r = _run(args, session=session)
    return r.stdout if r.returncode == 0 else ""


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
