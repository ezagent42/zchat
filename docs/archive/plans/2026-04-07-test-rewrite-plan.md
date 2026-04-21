# Test Infrastructure Rewrite — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace all libtmux-based test fixtures with `zchat.cli.zellij` wrappers so E2E and pre-release suites can run again.

**Architecture:** Drop-in replacement of 3 files that imported the deleted `zchat.cli.tmux` module. The `zchat.cli.zellij` module already provides equivalent operations. Test files that consume the fixtures need fixture name updates (`tmux_send` → `zellij_send`, `weechat_window` → `weechat_tab`).

**Tech Stack:** Python, pytest, zchat.cli.zellij, Zellij CLI

---

## Status: COMPLETED

All tasks below have been implemented and verified.

### Task 1: Create `tests/shared/zellij_helpers.py`

**Files:**
- Create: `tests/shared/zellij_helpers.py`

Replaces `tests/shared/tmux_helpers.py` with zellij equivalents:
- `send_keys()` → resolves tab name to pane_id, uses `zellij.send_command()`
- `capture_pane()` → uses `zellij.dump_screen()`
- `wait_for_content()` → polls `dump_screen()` with regex matching

### Task 2: Rewrite `tests/e2e/conftest.py`

**Files:**
- Modify: `tests/e2e/conftest.py`

Changes:
- `tmux_session` → `zellij_session` (uses `zellij.ensure_session()` + `kill_session()`)
- `tmux_send` → `zellij_send` (uses `zellij.get_pane_id()` + `send_command()`)
- `weechat_window` → `weechat_tab` (uses `zellij.new_tab()` instead of `session.new_window()`)
- `e2e_context` config: `[tmux] session = ...` → `[zellij] session = ...`
- `ergo_server`: `IrcManager(..., tmux_session=...)` → `IrcManager(..., zellij_session=...)`
- Removed `ZCHAT_TMUX_SESSION` env var (no longer used)
- Removed `import libtmux` and `from zchat.cli.tmux import ...`

### Task 3: Rewrite `tests/pre_release/conftest.py`

**Files:**
- Modify: `tests/pre_release/conftest.py`

Changes:
- `tmux_session` → `zellij_session`
- `tmux_send` → `zellij_send`
- `weechat_window` → `weechat_tab`
- `cli` fixture: removed `ZCHAT_TMUX_SESSION` env var
- `project` fixture: `cli("set", "tmux.session", ...)` → `cli("set", "zellij.session", ...)`
- Removed `import libtmux` and `from zchat.cli.tmux import ...`

### Task 4: Update test files referencing old fixture names

**Files:**
- Modify: `tests/e2e/test_e2e.py`
- Modify: `tests/pre_release/test_04a_irc_chat.py`

Changes in `test_e2e.py`:
- `weechat_window` → `weechat_tab` (3 occurrences)
- `tmux_send` → `zellij_send` (2 occurrences)

Changes in `test_04a_irc_chat.py`:
- `weechat_window` → `weechat_tab`
- `tmux_send` → `zellij_send`

### Task 5: Verify pytest collection

All three suites collect without ImportError:
- Unit: 173 tests collected
- E2E: 13 tests collected
- Pre-release: 41 tests collected

### Task 6: Run E2E tests

`test_zellij_lifecycle.py` — 4/4 passed (21.71s)
Unit tests — 173/173 passed (1.82s)
