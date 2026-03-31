# Fix Agent Send & Add IRC Communication Tests

**Date:** 2026-03-31
**Issue:** [ezagent42/zchat#30](https://github.com/ezagent42/zchat/issues/30)

## Problem

Two related gaps in zchat's reliability and test coverage:

1. **`zchat agent send` delivers messages before agent is ready** (Issue #30) — The `send()` method in `AgentManager` does not check the `.ready` marker before sending text via tmux `send-keys`. If the agent's Claude Code session hasn't finished its `SessionStart` hook (MCP connection, etc.), the text arrives before the agent can process it. Additionally, `send()` silently fails when the tmux window/pane is not found.

2. **No IRC user-to-user communication test** — All existing E2E and pre-release tests verify agent-to-channel or agent-to-agent flows via a single user ("alice"). There is no test that validates two independent users can exchange messages through IRC.

## Design

### Part 1: Fix `agent send` Readiness & Error Handling

**File:** `zchat/cli/agent_manager.py`

Current `send()` (L299-310):

```python
def send(self, name: str, text: str):
    from zchat.cli.tmux import find_window
    name = self.scoped(name)
    agent = self._agents.get(name)
    if not agent:
        raise ValueError(f"Unknown agent: {name}")
    if self._check_alive(name) != "running":
        raise ValueError(f"{name} is not running")
    window = find_window(self.tmux_session, agent["window_name"])
    if window and window.active_pane:
        window.active_pane.send_keys(text, enter=True)
```

Changes:
1. After the alive check, call `self._wait_for_ready(name, timeout=60)`. If it returns `False`, raise `ValueError(f"{name} not ready within 60s")`.
2. After `find_window()`, if `window` is `None` or `window.active_pane` is `None`, raise `ValueError(f"tmux window not found for {name}")` instead of silently skipping.

**New unit tests** in `tests/unit/test_agent_manager.py`:
- `test_send_waits_for_ready` — Create manager with `project_dir`, pre-touch `.ready` marker, mock `find_window` to return a mock window/pane. Verify `send()` completes without error.
- `test_send_raises_when_not_ready` — Create manager with `project_dir`, do NOT create `.ready` marker, set a short timeout. Verify `send()` raises `ValueError` with "not ready".
- `test_send_raises_on_missing_window` — Create manager, touch `.ready`, mock `find_window` to return `None`. Verify `send()` raises `ValueError` with "window not found".

### Part 2: Alice-Bob IRC Communication Test

**Approach:** Add a second `IrcProbe` instance ("bob") that joins `#general`. Verify bidirectional public message delivery between bob and alice (via WeeChat).

#### IrcProbe Enhancement

**File:** `tests/shared/irc_probe.py`

Add a `send(channel, text)` method to `IrcProbe`:

```python
def send(self, channel: str, text: str):
    """Send a PRIVMSG to a channel. Dispatched via reactor."""
    self._reactor.scheduler.execute_after(
        0, lambda: self._conn.privmsg(channel, text)
    )
```

This uses the same reactor-dispatch pattern as `join()` for thread safety.

#### E2E Test

**File:** `tests/e2e/conftest.py` — New session-scoped fixture:

```python
@pytest.fixture(scope="session")
def bob_probe(ergo_server):
    """Second IRC client (bob) for user-to-user tests."""
    probe = IrcProbe(ergo_server["host"], ergo_server["port"], nick="bob")
    probe.connect()
    time.sleep(1)
    probe.join("#general")
    time.sleep(1)
    yield probe
    probe.disconnect()
```

**File:** `tests/e2e/test_e2e.py` — New Phase 9 (between current Phase 8 `test_shutdown` and end, but reordered to run BEFORE shutdown — placed at order(7) and existing phases 7-8 bumped to 8-9):

Actually, the alice-bob test should run while the IRC server is still up and WeeChat is connected. Place it at **order(7)**, bump `test_agent_stop` to order(8), `test_shutdown` to order(9).

```python
@pytest.mark.e2e
@pytest.mark.order(7)
def test_alice_bob_conversation(irc_probe, bob_probe, weechat_window, tmux_send):
    """Phase 7: Two users exchange messages in #general."""
    # Bob sends to #general
    bob_probe.send("#general", "Hello from bob")
    msg = irc_probe.wait_for_message("Hello from bob", timeout=10)
    assert msg is not None, "bob's message not seen by probe"
    assert msg["nick"] == "bob"

    # Alice sends to #general via WeeChat
    tmux_send(weechat_window, "Hello from alice")
    msg = bob_probe.wait_for_message("Hello from alice", timeout=10)
    assert msg is not None, "alice's message not seen by bob"
    assert msg["nick"] == "alice"
```

#### Pre-Release Test

**File:** `tests/pre_release/conftest.py` — New session-scoped `bob_probe` fixture (same pattern).

**File:** `tests/pre_release/test_04a_irc_chat.py` — New module between test_04 and test_05:

```python
@pytest.mark.order(1)
def test_alice_bob_channel_message(cli, irc_probe, bob_probe, weechat_window, tmux_send):
    """Bob and alice exchange messages in #general."""
    bob_probe.send("#general", "Hello from bob")
    msg = irc_probe.wait_for_message("Hello from bob", timeout=10)
    assert msg is not None, "bob's message not seen by probe"

    tmux_send(weechat_window, "Hello from alice")
    msg = bob_probe.wait_for_message("Hello from alice", timeout=10)
    assert msg is not None, "alice's message not seen by bob"
```

Pre-release `conftest.py` needs `weechat_window` and `tmux_send` fixtures (currently only in E2E). Add them following the same pattern as E2E but using the pre-release `cli`/`tmux_session` fixtures.

### Timeout Changes

- `agent_manager.send()` ready wait: **60 seconds** (matches existing `_wait_for_ready` default)
- `test_agent_send` in pre-release `test_04_agent.py`: increase `wait_for_message` timeout from **30s to 60s**
- `test_agent_send_to_channel` in E2E `test_e2e.py`: increase `wait_for_message` timeout from **30s to 60s**
- Walkthrough `walkthrough-steps.sh`: increase `wait_pane_content` timeout from **30 to 60**

### Files Changed

| File | Change |
|------|--------|
| `zchat/cli/agent_manager.py` | `send()`: add ready wait + error on missing window |
| `tests/shared/irc_probe.py` | Add `send(channel, text)` method |
| `tests/unit/test_agent_manager.py` | 3 new unit tests for send |
| `tests/e2e/conftest.py` | Add `bob_probe` fixture |
| `tests/e2e/test_e2e.py` | Add Phase 7 alice-bob test, reorder phases 7→8, 8→9, bump timeouts |
| `tests/pre_release/conftest.py` | Add `bob_probe`, `weechat_window`, `tmux_send` fixtures |
| `tests/pre_release/test_04a_irc_chat.py` | New module: alice-bob test |
| `tests/pre_release/test_04_agent.py` | Bump `wait_for_message` timeout to 60s |
| `tests/pre_release/walkthrough-steps.sh` | Bump wait timeout from 30 to 60 |

### What Is NOT Changed

- Walkthrough script does not add bob conversation (keeps it simple)
- No changes to `app.py` (Typer catches ValueError automatically)
- No changes to existing test phases 1-6 logic
- No PRIVMSG / DM testing (future iteration)
