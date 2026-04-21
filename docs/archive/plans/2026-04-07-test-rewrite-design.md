# Test Infrastructure Rewrite — tmux → Zellij

> Date: 2026-04-07
> Status: Approved

## Problem

3 test files import the deleted `zchat.cli.tmux` module, making all E2E (13 tests) and pre-release (41 tests) suites completely broken. Only unit tests (173) run in CI.

## Broken Files

| File | Broken Fixtures | Uses |
|------|----------------|------|
| `tests/shared/tmux_helpers.py` | `send_keys`, `capture_pane`, `wait_for_content` | libtmux API |
| `tests/e2e/conftest.py` | `tmux_send`, `weechat_window`, `tmux_session` | libtmux session/window/pane |
| `tests/pre_release/conftest.py` | `tmux_send`, `tmux_session` | libtmux session/window |

## Solution

Replace all libtmux-based fixtures with `zchat.cli.zellij` wrappers. The zellij module already provides all needed operations:

| Old (libtmux) | New (zellij.py) |
|---------------|-----------------|
| `session.new_window(name, shell)` | `zellij.new_tab(session, name, command)` |
| `window.active_pane.send_keys(text)` | `zellij.send_command(session, pane_id, text)` |
| `pane.capture_pane()` | `zellij.dump_screen(session, pane_id)` |
| `libtmux.Server().new_session()` | `zellij.ensure_session(name)` |
| `find_window(session, name)` | `zellij.tab_exists(session, name)` |
| `find_pane(session, target)` | `zellij.get_pane_id(session, tab_name)` |

## Scope

1. Replace `tests/shared/tmux_helpers.py` → `tests/shared/zellij_helpers.py`
2. Rewrite `tests/e2e/conftest.py` — remove libtmux, use zellij
3. Rewrite `tests/pre_release/conftest.py` — remove libtmux, use zellij
4. Update env vars: `ZCHAT_TMUX_SESSION` → session name from config
5. Verify all test files can be collected by pytest (import check)
6. Run E2E `test_zellij_lifecycle.py` to validate fixtures work
