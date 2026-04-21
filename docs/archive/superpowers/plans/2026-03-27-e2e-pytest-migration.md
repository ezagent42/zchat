# E2E Pytest Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate automated e2e tests from bash scripts to pytest with IrcProbe class and fixture-based lifecycle management.

**Architecture:** IrcProbe (irc library) for verification, pytest session-scoped fixtures for ergo/tmux/project/WeeChat lifecycle, single test function with sequential phases. Manual testing stays as bash setup script + docs.

**Tech Stack:** Python 3.11+, pytest, pytest-timeout, `irc` library, tmux, ergo

**Spec:** `docs/superpowers/specs/2026-03-27-e2e-pytest-migration.md`

### Review Corrections (apply during implementation)

1. **conftest.py `weechat_pane` fixture**: spec says `state["weechat_pane"]` — must be `state["irc"]["weechat_pane_id"]` (matches irc_manager.py)
2. **Delete `ergo-test.yaml`**: spec says "Keep" but conftest generates config dynamically — delete it in Task 6
3. **Delete `e2e-test.tape`**: references deleted `e2e-test.sh` and stale zenohd — delete in Task 6
4. **Manual test docs**: use `wc-agent` CLI commands (not `./wc-agent.sh` wrapper)
5. **`pytest.ini`**: add `e2e` marker registration alongside existing `integration` marker (Task 2)

---

## File Structure

### New files
```
tests/e2e/irc_probe.py        # IrcProbe class
tests/e2e/conftest.py          # Rewrite: pytest fixtures
tests/e2e/test_e2e.py          # Single test function with phases
tests/e2e/e2e-setup.sh         # Manual test env setup (from e2e-test-manual.sh)
docs/e2e-manual-test.md        # Manual test guide (recreated)
```

### Delete
```
tests/e2e/e2e-test.sh          # Replaced by pytest
tests/e2e/e2e-test-manual.sh   # Renamed to e2e-setup.sh
tests/e2e/e2e-cleanup.sh       # Replaced by fixture teardown
tests/e2e/helpers.sh            # Migrated to Python
tests/e2e/test-config.toml     # Replaced by dynamic config in conftest
tests/e2e/ergo-test.yaml       # Conftest generates config dynamically
tests/e2e/e2e-test.tape         # References deleted scripts + stale deps
```

### Modify
```
weechat-channel-server/pyproject.toml  # Add pytest-timeout to test deps
```

---

## Chunk 1: IrcProbe + Conftest

### Task 1: Create IrcProbe class

**Files:**
- Create: `tests/e2e/irc_probe.py`

Copy the IrcProbe class from the spec (lines 50-158). Key features:
- `connect()` — connect + start reactor thread
- `join(channel)` — join channel
- `nick_exists(nick)` — WHOIS on persistent connection
- `wait_for_nick(nick, timeout)` — poll nick_exists
- `wait_for_nick_gone(nick, timeout)` — poll until gone
- `wait_for_message(pattern, timeout)` — grep captured messages
- `threading.Lock` for thread-safe message list

- [ ] **Step 1: Create irc_probe.py** — copy from spec verbatim
- [ ] **Step 2: Commit**

```bash
git add tests/e2e/irc_probe.py
git commit -m "feat: add IrcProbe class for e2e test verification"
```

---

### Task 2: Create conftest.py with fixtures

**Files:**
- Create: `tests/e2e/conftest.py` (overwrite existing if any)

Copy fixtures from spec (lines 163-329). Key fixtures:
- `e2e_port` — unique port
- `ergo_server` — start/stop ergo with socket readiness check
- `tmux_session` — headless tmux session
- `e2e_context` — central context dict (home, project, tmux_session, port)
- `wc_agent` — callable fixture for CLI commands
- `tmux_send` — callable fixture for tmux send-keys
- `irc_probe` — IrcProbe instance
- `weechat_pane` — start WeeChat, yield pane_id from state.json
- `pytest_configure` — register `e2e` marker

- [ ] **Step 1: Create conftest.py** — copy from spec, ensure imports correct
- [ ] **Step 2: Add pytest-timeout to deps**

```toml
# weechat-channel-server/pyproject.toml [project.optional-dependencies]
test = ["pytest", "pytest-asyncio", "pytest-timeout"]
```

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/conftest.py weechat-channel-server/pyproject.toml
git commit -m "feat: add e2e pytest fixtures (ergo, tmux, project, probe, weechat)"
```

---

### Task 3: Create test_e2e.py

**Files:**
- Create: `tests/e2e/test_e2e.py`

Copy from spec (lines 336-381). Single function `test_full_e2e_lifecycle` with 7 phases:
1. WeeChat connected (nick check)
2. Agent0 create + IRC join
3. Agent send to #general
4. @mention auto-response
5. Agent1 create + send
6. Agent1 stop
7. Shutdown

- [ ] **Step 1: Create test_e2e.py** — copy from spec
- [ ] **Step 2: Run test** (expect it to work if ergo + tmux available)

```bash
cd weechat-channel-server && uv run --with pytest --with pytest-timeout python -m pytest ../tests/e2e/test_e2e.py -v -m e2e --timeout=300
```

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_e2e.py
git commit -m "feat: add e2e pytest test — full lifecycle in single function"
```

---

## Chunk 2: Manual Test + Cleanup

### Task 4: Rename e2e-test-manual.sh → e2e-setup.sh

**Files:**
- Rename: `tests/e2e/e2e-test-manual.sh` → `tests/e2e/e2e-setup.sh`

The content stays the same — it sets up env vars, creates project config, starts ergo. Just rename for clarity.

- [ ] **Step 1: Rename**

```bash
git mv tests/e2e/e2e-test-manual.sh tests/e2e/e2e-setup.sh
```

- [ ] **Step 2: Commit**

```bash
git commit -m "refactor: rename e2e-test-manual.sh → e2e-setup.sh"
```

---

### Task 5: Recreate docs/e2e-manual-test.md

**Files:**
- Create: `docs/e2e-manual-test.md`

Simple step-by-step guide referencing `source tests/e2e/e2e-setup.sh` and `./wc-agent.sh` commands. Same content as the previous version.

- [ ] **Step 1: Create manual test guide**
- [ ] **Step 2: Commit**

```bash
git add docs/e2e-manual-test.md
git commit -m "docs: recreate e2e manual test guide"
```

---

### Task 6: Delete old bash test files

**Files:**
- Delete: `tests/e2e/e2e-test.sh`, `tests/e2e/e2e-cleanup.sh`, `tests/e2e/helpers.sh`, `tests/e2e/test-config.toml`

- [ ] **Step 1: Delete files**

```bash
rm -f tests/e2e/e2e-test.sh tests/e2e/e2e-cleanup.sh tests/e2e/helpers.sh tests/e2e/test-config.toml tests/e2e/ergo-test.yaml tests/e2e/e2e-test.tape
```

- [ ] **Step 2: Update CLAUDE.md** — change e2e test command from `bash tests/e2e/e2e-test.sh` to `pytest tests/e2e/ -v -m e2e`
- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: delete old bash e2e test scripts, update CLAUDE.md"
```

---

## Chunk 3: Verify + Fix

### Task 7: Run e2e test and fix issues

- [ ] **Step 1: Run automated e2e test**

```bash
cd weechat-channel-server && uv run --with pytest --with pytest-timeout python -m pytest ../tests/e2e/test_e2e.py -v -m e2e --timeout=300
```

- [ ] **Step 2: Fix any failures**
- [ ] **Step 3: Run unit tests to ensure no regressions**

```bash
cd weechat-channel-server && uv run --with pytest python -m pytest ../tests/unit/ -v
```

- [ ] **Step 4: Commit fixes**

```bash
git commit -m "fix: e2e pytest test fixes"
```
