# Shared Protocol Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract duplicated protocol logic (topic building, pair keys, zenoh config, signal constants) into a shared `wc_protocol/` module, eliminating cross-component duplication while respecting the PyO3 subinterpreter constraint.

**Architecture:** Create a pure-Python `wc_protocol/` package at the project root. It contains zero PyO3 dependencies (no `import zenoh`) so it can be safely imported by both WeeChat subinterpreter code and standalone processes. Each component replaces inline logic with imports from this shared package. WeeChat plugins access it via `sys.path` manipulation (same pattern already used for `helpers.py`).

**Tech Stack:** Python 3.12+, pytest, no new dependencies

---

## Current vs. Target Architecture

### Current: Duplicated inline logic

```
weechat-zenoh/
├── weechat-zenoh.py     ← inline make_pair, topic paths, signal emission
├── zenoh_sidecar.py     ← inline make_pair, topic paths, zenoh config, ZENOH_DEFAULT_ENDPOINT
└── helpers.py           ← target_to_buffer_label, parse_input, ZENOH_DEFAULT_ENDPOINT

weechat-channel-server/
├── server.py            ← inline zenoh config, topic paths
└── message.py           ← make_private_pair, topic builders, chunk_message, dedup, mention

weechat-agent/
└── weechat-agent.py     ← inline scoped_name, pair extraction

tests/
└── conftest.py          ← MockZenoh classes, sys.path hack for message.py
```

### Target: Shared protocol package

```
wc_protocol/                    ← NEW shared package (pure Python, no PyO3)
├── __init__.py                 ← re-exports public API
├── topics.py                   ← topic builders, pair key, channel key parsing
├── config.py                   ← ZENOH_DEFAULT_ENDPOINT, build_zenoh_client_config()
├── signals.py                  ← signal name constants + emit helper type
└── naming.py                   ← scoped_name(), agent naming conventions

weechat-zenoh/
├── weechat-zenoh.py            ← imports from wc_protocol (topics, signals)
├── zenoh_sidecar.py            ← imports from wc_protocol (topics, config)
└── helpers.py                  ← DELETED (contents moved to wc_protocol)

weechat-channel-server/
├── server.py                   ← imports from wc_protocol (config, topics)
└── message.py                  ← keeps dedup, mention, chunk (server-specific); topic/pair REMOVED

weechat-agent/
└── weechat-agent.py            ← imports from wc_protocol (naming, signals)

tests/
├── conftest.py                 ← MockZenoh stays; sys.path adds wc_protocol
└── unit/test_protocol.py       ← NEW tests for wc_protocol
```

### What moves where

| Current location | Function/Constant | Target |
|---|---|---|
| `helpers.py:3` | `ZENOH_DEFAULT_ENDPOINT` | `wc_protocol/config.py` |
| `zenoh_sidecar.py:22` | `ZENOH_DEFAULT_ENDPOINT` (duplicate) | DELETED |
| `server.py:67` | `ZENOH_DEFAULT_ENDPOINT` (inline) | DELETED |
| `helpers.py:6-16` | `target_to_buffer_label()` | `wc_protocol/topics.py` |
| `helpers.py:19-27` | `parse_input()` | `wc_protocol/topics.py` |
| `message.py:46-48` | `make_private_pair()` | `wc_protocol/topics.py` |
| `message.py:51-63` | `private_topic()`, `channel_topic()`, `presence_topic()` | `wc_protocol/topics.py` |
| `zenoh_sidecar.py:44-50` | `build_config()` | `wc_protocol/config.py` |
| `server.py:67-74` | `setup_zenoh` config block | uses `wc_protocol/config.py` |
| `weechat-agent.py:29-33` | `scoped_name()` | `wc_protocol/naming.py` |
| (new) | Signal name constants | `wc_protocol/signals.py` |

### What stays in place

| File | Keeps | Reason |
|---|---|---|
| `message.py` | `MessageDedup`, `detect_mention`, `clean_mention`, `chunk_message` | Server-specific logic, not shared |
| `zenoh_sidecar.py` | All Zenoh session management | Process-specific, uses `import zenoh` |
| `weechat-zenoh.py` | Buffer management, sidecar IPC, queue polling | WeeChat-specific |
| `weechat-agent.py` | Workspace/tmux/lifecycle management | Agent-specific |

---

## Task 1: Create `wc_protocol/topics.py` with tests

**Files:**
- Create: `wc_protocol/__init__.py`
- Create: `wc_protocol/topics.py`
- Create: `tests/unit/test_protocol.py`

- [ ] **Step 1: Write failing tests for topic builders and pair key**

```python
# tests/unit/test_protocol.py
"""Tests for wc_protocol shared module."""


def test_make_private_pair_sorted():
    from wc_protocol.topics import make_private_pair
    assert make_private_pair("bob", "alice") == "alice_bob"
    assert make_private_pair("alice", "bob") == "alice_bob"


def test_channel_topic():
    from wc_protocol.topics import channel_topic
    assert channel_topic("general") == "wc/channels/general/messages"


def test_private_topic():
    from wc_protocol.topics import private_topic
    assert private_topic("alice_bob") == "wc/private/alice_bob/messages"


def test_presence_topic():
    from wc_protocol.topics import presence_topic
    assert presence_topic("alice") == "wc/presence/alice"


def test_channel_presence_topic():
    from wc_protocol.topics import channel_presence_topic
    assert channel_presence_topic("general", "alice") == "wc/channels/general/presence/alice"


def test_channel_presence_glob():
    from wc_protocol.topics import channel_presence_glob
    assert channel_presence_glob("general") == "wc/channels/general/presence/*"


def test_target_to_buffer_label_channel():
    from wc_protocol.topics import target_to_buffer_label
    assert target_to_buffer_label("channel:general", "alice") == "channel:#general"


def test_target_to_buffer_label_private():
    from wc_protocol.topics import target_to_buffer_label
    assert target_to_buffer_label("private:alice_bob", "alice") == "private:@bob"


def test_parse_input_msg():
    from wc_protocol.topics import parse_input
    assert parse_input("hello") == ("msg", "hello")


def test_parse_input_action():
    from wc_protocol.topics import parse_input
    assert parse_input("/me waves") == ("action", "waves")


def test_extract_other_nick():
    from wc_protocol.topics import extract_other_nick
    assert extract_other_nick("alice_bob", "alice") == "bob"
    assert extract_other_nick("alice_bob", "bob") == "alice"


def test_parse_target_key():
    from wc_protocol.topics import parse_target_key
    assert parse_target_key("channel:general") == ("channel", "general")
    assert parse_target_key("private:alice_bob") == ("private", "alice_bob")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/h2oslabs/Workspace/weechat-claude/.claude/worktrees/code-simplifier && python -m pytest tests/unit/test_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wc_protocol'`

- [ ] **Step 3: Implement `wc_protocol/topics.py`**

```python
# wc_protocol/__init__.py
"""Shared protocol definitions for WeeChat-Claude components.
Pure Python — no PyO3/zenoh imports. Safe for WeeChat subinterpreters."""

# wc_protocol/topics.py
"""Zenoh topic builders, target key parsing, and input parsing."""


def make_private_pair(nick_a: str, nick_b: str) -> str:
    """Create a sorted private pair key from two nicknames."""
    return "_".join(sorted([nick_a, nick_b]))


def channel_topic(channel_id: str) -> str:
    """Zenoh topic for channel messages."""
    return f"wc/channels/{channel_id}/messages"


def private_topic(pair: str) -> str:
    """Zenoh topic for private messages."""
    return f"wc/private/{pair}/messages"


def presence_topic(nick: str) -> str:
    """Zenoh topic for global presence."""
    return f"wc/presence/{nick}"


def channel_presence_topic(channel_id: str, nick: str) -> str:
    """Zenoh topic for per-channel presence token."""
    return f"wc/channels/{channel_id}/presence/{nick}"


def channel_presence_glob(channel_id: str) -> str:
    """Zenoh key expression for subscribing to all presence in a channel."""
    return f"wc/channels/{channel_id}/presence/*"


def target_to_buffer_label(target: str, my_nick: str) -> str:
    """Convert internal target key to WeeChat-style buffer label.
    'channel:general' → 'channel:#general'
    'private:alice_bob' → 'private:@alice' (the other nick)
    """
    if target.startswith("channel:"):
        return f"channel:#{target[8:]}"
    pair = target.split(":", 1)[1]
    other = extract_other_nick(pair, my_nick)
    return f"private:@{other}"


def extract_other_nick(pair: str, my_nick: str) -> str:
    """Extract the other party's nick from a sorted pair key."""
    nicks = pair.split("_")
    others = [n for n in nicks if n != my_nick]
    return others[0] if others else pair


def parse_target_key(target: str) -> tuple[str, str]:
    """Split 'channel:general' → ('channel', 'general')."""
    kind, _, value = target.partition(":")
    return (kind, value)


def parse_input(input_data: str) -> tuple[str, str]:
    """Parse user input into (msg_type, body).
    '/me waves' → ('action', 'waves')
    'hello' → ('msg', 'hello')
    """
    if input_data.startswith("/me ") or input_data == "/me":
        body = input_data[4:] if len(input_data) > 4 else ""
        return ("action", body)
    return ("msg", input_data)
```

- [ ] **Step 4: Add project root to test sys.path in conftest.py**

In `tests/conftest.py`, add after line 10 (before the existing `weechat-channel-server` path insert):
```python
# Add project root for wc_protocol
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
```

This must happen now (not later) so all subsequent tasks have `wc_protocol` importable in tests.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/h2oslabs/Workspace/weechat-claude/.claude/worktrees/code-simplifier && python -m pytest tests/unit/test_protocol.py -v`
Expected: All 12 tests PASS

- [ ] **Step 6: Commit**

```bash
git add wc_protocol/ tests/unit/test_protocol.py tests/conftest.py
git commit -m "feat: add wc_protocol shared package with topic builders and parsing"
```

---

## Task 2: Add `wc_protocol/config.py` and `wc_protocol/naming.py`

**Files:**
- Create: `wc_protocol/config.py`
- Create: `wc_protocol/naming.py`
- Modify: `tests/unit/test_protocol.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_protocol.py`:

```python
def test_zenoh_default_endpoint():
    from wc_protocol.config import ZENOH_DEFAULT_ENDPOINT
    assert ZENOH_DEFAULT_ENDPOINT == "tcp/127.0.0.1:7447"


def test_build_zenoh_client_config_default(monkeypatch):
    """Test config builder without real zenoh — just verify the dict output."""
    from wc_protocol.config import build_zenoh_config_dict
    result = build_zenoh_config_dict()
    assert result["mode"] == "client"
    assert result["connect/endpoints"] == ["tcp/127.0.0.1:7447"]


def test_build_zenoh_client_config_custom():
    from wc_protocol.config import build_zenoh_config_dict
    result = build_zenoh_config_dict(connect="tcp/10.0.0.1:7447,tcp/10.0.0.2:7447")
    assert result["connect/endpoints"] == ["tcp/10.0.0.1:7447", "tcp/10.0.0.2:7447"]


def test_scoped_name_adds_prefix():
    from wc_protocol.naming import scoped_name
    assert scoped_name("helper", "alice") == "alice:helper"


def test_scoped_name_no_double_prefix():
    from wc_protocol.naming import scoped_name
    assert scoped_name("alice:helper", "alice") == "alice:helper"


def test_scoped_name_different_prefix():
    from wc_protocol.naming import scoped_name
    assert scoped_name("bob:helper", "alice") == "bob:helper"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_protocol.py -v -k "config or scoped"`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement config.py**

```python
# wc_protocol/config.py
"""Zenoh configuration constants and builders.

NOTE: This module does NOT import zenoh. It produces plain dicts
that callers apply to zenoh.Config() themselves. This keeps the
module safe for WeeChat subinterpreters.
"""

ZENOH_DEFAULT_ENDPOINT = "tcp/127.0.0.1:7447"


def build_zenoh_config_dict(connect: str | None = None) -> dict:
    """Build a Zenoh client config as a plain dict.

    Args:
        connect: Comma-separated endpoint list, or None for default.

    Returns:
        Dict with keys 'mode' and 'connect/endpoints' ready to be
        applied via zenoh.Config.insert_json5().
    """
    endpoints = connect.split(",") if connect else [ZENOH_DEFAULT_ENDPOINT]
    return {
        "mode": "client",
        "connect/endpoints": endpoints,
    }
```

- [ ] **Step 4: Implement naming.py**

```python
# wc_protocol/naming.py
"""Agent naming conventions."""

AGENT_SEPARATOR = ":"


def scoped_name(name: str, username: str) -> str:
    """Add username prefix to agent name if not already scoped.
    'helper' + 'alice' → 'alice:helper'
    'alice:helper' + 'alice' → 'alice:helper' (no change)
    """
    if AGENT_SEPARATOR in name:
        return name
    return f"{username}{AGENT_SEPARATOR}{name}"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_protocol.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add wc_protocol/config.py wc_protocol/naming.py tests/unit/test_protocol.py
git commit -m "feat: add wc_protocol config and naming modules"
```

---

## Task 3: Add `wc_protocol/signals.py`

**Files:**
- Create: `wc_protocol/signals.py`
- Modify: `tests/unit/test_protocol.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_protocol.py`:

```python
def test_signal_constants():
    from wc_protocol.signals import (
        SIGNAL_MESSAGE_SENT, SIGNAL_MESSAGE_RECEIVED, SIGNAL_PRESENCE_CHANGED
    )
    assert SIGNAL_MESSAGE_SENT == "zenoh_message_sent"
    assert SIGNAL_MESSAGE_RECEIVED == "zenoh_message_received"
    assert SIGNAL_PRESENCE_CHANGED == "zenoh_presence_changed"
```

- [ ] **Step 2: Implement signals.py**

```python
# wc_protocol/signals.py
"""WeeChat signal name constants for inter-plugin communication.

These signal names form the contract between weechat-zenoh and weechat-agent.
Centralizing them here prevents silent breakage from typos or renames.
"""

SIGNAL_MESSAGE_SENT = "zenoh_message_sent"
SIGNAL_MESSAGE_RECEIVED = "zenoh_message_received"
SIGNAL_PRESENCE_CHANGED = "zenoh_presence_changed"
```

- [ ] **Step 3: Run tests, verify pass**

Run: `python -m pytest tests/unit/test_protocol.py -v`

- [ ] **Step 4: Commit**

```bash
git add wc_protocol/signals.py tests/unit/test_protocol.py
git commit -m "feat: add signal name constants to wc_protocol"
```

---

## Task 4: Migrate `zenoh_sidecar.py` to use `wc_protocol`

**Files:**
- Modify: `weechat-zenoh/zenoh_sidecar.py`

- [ ] **Step 1: Add `wc_protocol` to sidecar's sys.path and replace imports**

At the top of `zenoh_sidecar.py`, after the existing imports, add:

```python
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))
from wc_protocol.topics import (
    make_private_pair, channel_topic, private_topic,
    presence_topic, channel_presence_topic, channel_presence_glob,
)
from wc_protocol.config import build_zenoh_config_dict
```

- [ ] **Step 2: Replace `ZENOH_DEFAULT_ENDPOINT` and `build_config()`**

Delete `ZENOH_DEFAULT_ENDPOINT = "tcp/127.0.0.1:7447"` (line 22).

Replace `build_config()` function (lines 44-50) with:

```python
def build_config(connect: str | None = None):
    """Build Zenoh client config from wc_protocol dict."""
    cfg_dict = build_zenoh_config_dict(connect)
    config = zenoh.Config()
    config.insert_json5("mode", f'"{cfg_dict["mode"]}"')
    config.insert_json5("connect/endpoints", json.dumps(cfg_dict["connect/endpoints"]))
    return config
```

- [ ] **Step 3: Replace inline pair key generation**

In `handle_join_private` (line 180): replace `"_".join(sorted([my_nick, target_nick]))` with `make_private_pair(my_nick, target_nick)`.

In `handle_leave_private` (line 197): same replacement.

- [ ] **Step 4: Replace inline topic strings with builders**

In `handle_join_channel`:
- Line 99: `f"wc/channels/{channel_id}/messages"` → `channel_topic(channel_id)`
- Line 107: `f"wc/channels/{channel_id}/presence/{my_nick}"` → `channel_presence_topic(channel_id, my_nick)`
- Line 112: `f"wc/channels/{channel_id}/presence/*"` → `channel_presence_glob(channel_id)`
- Line 118: same glob replacement

In `handle_init`:
- Line 68: `f"wc/presence/{my_nick}"` → `presence_topic(my_nick)`

In `handle_join_private`:
- Line 186: `f"wc/private/{pair}/messages"` → `private_topic(pair)`

In `handle_set_nick`:
- Line 221: `f"wc/presence/{my_nick}"` → `presence_topic(my_nick)`
- Line 230: `f"wc/channels/{cid}/presence/{my_nick}"` → `channel_presence_topic(cid, my_nick)`

- [ ] **Step 5: Run existing sidecar tests**

Run: `python -m pytest tests/unit/test_sidecar.py -v`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add weechat-zenoh/zenoh_sidecar.py
git commit -m "refactor: migrate zenoh_sidecar to use wc_protocol"
```

---

## Task 5: Migrate `weechat-zenoh.py` to use `wc_protocol`

**Files:**
- Modify: `weechat-zenoh/weechat-zenoh.py`
- Delete: `weechat-zenoh/helpers.py`

- [ ] **Step 1: Replace `helpers.py` import with `wc_protocol`**

Replace line 15:
```python
from helpers import target_to_buffer_label, parse_input
```
with:
```python
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))
from wc_protocol.topics import target_to_buffer_label, parse_input, make_private_pair, extract_other_nick
from wc_protocol.signals import SIGNAL_MESSAGE_SENT, SIGNAL_MESSAGE_RECEIVED, SIGNAL_PRESENCE_CHANGED
```

(Note: `os` is already imported on line 12. The `_sys` alias avoids shadowing the existing `sys` usage pattern.)

Replace the `from helpers import ...` line (line 15) with:
```python
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))
from wc_protocol.topics import target_to_buffer_label, parse_input, make_private_pair, extract_other_nick
from wc_protocol.signals import SIGNAL_MESSAGE_SENT, SIGNAL_MESSAGE_RECEIVED, SIGNAL_PRESENCE_CHANGED
```

- [ ] **Step 2: Replace inline `make_private_pair` calls**

In `join_private` (line 283): `"_".join(sorted([my_nick, target_nick]))` → `make_private_pair(my_nick, target_nick)`

In `leave_private` (line 322): same replacement.

In `send_message` (line 345): same replacement.

- [ ] **Step 3: Replace inline pair extraction in `poll_queues_cb`**

Lines 410-411:
```python
nicks = pair.split("_")
other = [n for n in nicks if n != my_nick]
```
→
```python
other_nick = extract_other_nick(pair, my_nick)
```
And update line 413: `join_private(other[0])` → `join_private(other_nick)`

In `zenoh_cmd_cb` reconnect (lines 558-560): same pattern replacement.

- [ ] **Step 4: Replace signal name strings with constants**

Line 377: `"zenoh_message_sent"` → `SIGNAL_MESSAGE_SENT`
Line 448: `"zenoh_message_received"` → `SIGNAL_MESSAGE_RECEIVED`
Line 467: `"zenoh_presence_changed"` → `SIGNAL_PRESENCE_CHANGED`

- [ ] **Step 5: Delete `helpers.py`**

```bash
git rm weechat-zenoh/helpers.py
```

- [ ] **Step 6: Run sidecar tests (they exercise the plugin indirectly)**

Run: `python -m pytest tests/unit/test_sidecar.py tests/unit/test_protocol.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add weechat-zenoh/weechat-zenoh.py
git commit -m "refactor: migrate weechat-zenoh to use wc_protocol, delete helpers.py"
```

---

## Task 6: Migrate `weechat-channel-server/` to use `wc_protocol`

**Files:**
- Modify: `weechat-channel-server/server.py`
- Modify: `weechat-channel-server/message.py`

- [ ] **Step 1: Add `wc_protocol` to server.py imports**

At top of `server.py`, after existing imports, add:
```python
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))
from wc_protocol.config import build_zenoh_config_dict
from wc_protocol.topics import make_private_pair, channel_topic, private_topic, presence_topic
```

- [ ] **Step 2: Simplify `setup_zenoh` config block**

Replace lines 67-74 in `setup_zenoh()`:
```python
    ZENOH_DEFAULT_ENDPOINT = "tcp/127.0.0.1:7447"
    zenoh_config = zenoh.Config()
    zenoh_config.insert_json5("mode", '"client"')
    connect = os.environ.get("ZENOH_CONNECT")
    if connect:
        zenoh_config.insert_json5("connect/endpoints", json.dumps(connect.split(",")))
    else:
        zenoh_config.insert_json5("connect/endpoints", f'["{ZENOH_DEFAULT_ENDPOINT}"]')
```
with:
```python
    cfg = build_zenoh_config_dict(os.environ.get("ZENOH_CONNECT"))
    zenoh_config = zenoh.Config()
    zenoh_config.insert_json5("mode", f'"{cfg["mode"]}"')
    zenoh_config.insert_json5("connect/endpoints", json.dumps(cfg["connect/endpoints"]))
```

- [ ] **Step 3: Replace topic strings in `_handle_reply`**

Line 221: `f"wc/channels/{channel}/messages"` → `channel_topic(channel)`
Line 224: `f"wc/private/{pair}/messages"` → `private_topic(pair)`

- [ ] **Step 4: Replace presence topics in `setup_zenoh`**

Line 76: `f"wc/presence/{AGENT_NAME}"` → `presence_topic(AGENT_NAME)`
Line 116: `f"wc/channels/{channel}/presence/{AGENT_NAME}"` → `channel_presence_topic(channel, AGENT_NAME)`
Line 131-132: same replacement for autojoin block

Also add `channel_presence_topic` to the import from `wc_protocol.topics`.

- [ ] **Step 5: Replace topic in `_handle_join_channel`**

Line 229: `f"wc/channels/{channel}/presence/{AGENT_NAME}"` → `channel_presence_topic(channel, AGENT_NAME)`

- [ ] **Step 6: Update `server.py` import from `message` and remove moved functions from `message.py`**

In `server.py`, change the `from message import` line to:
```python
from message import MessageDedup, detect_mention, clean_mention, chunk_message
```
(Remove `make_private_pair` — now imported from `wc_protocol.topics`.)

Remove from `message.py`:
- `make_private_pair()` (lines 46-48)
- `private_topic()` (lines 51-53)
- `channel_topic()` (lines 56-58)
- `presence_topic()` (lines 61-63)

- [ ] **Step 7: Run server and message tests**

Run: `python -m pytest tests/unit/test_message.py tests/unit/test_server.py tests/unit/test_tools.py tests/unit/test_protocol.py -v`
Expected: All PASS (note: `test_tools.py` tests `server.py` reply logic, not the deleted `tools.py`)

- [ ] **Step 8: Commit**

```bash
git add weechat-channel-server/server.py weechat-channel-server/message.py
git commit -m "refactor: migrate channel-server to use wc_protocol"
```

---

## Task 7: Migrate `weechat-agent.py` to use `wc_protocol`

**Files:**
- Modify: `weechat-agent/weechat-agent.py`

- [ ] **Step 1: Add `wc_protocol` imports**

After existing imports (line 14), add:
```python
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))
from wc_protocol.naming import scoped_name as protocol_scoped_name
from wc_protocol.signals import SIGNAL_MESSAGE_RECEIVED, SIGNAL_PRESENCE_CHANGED
```

- [ ] **Step 2: Replace inline `scoped_name()`**

Replace the local `scoped_name()` function (lines 29-33) with a thin wrapper that binds `USERNAME`:

```python
def scoped_name(name):
    return protocol_scoped_name(name, USERNAME)
```

This preserves the 1-arg call sites (lines 49, 140, 272) unchanged while using the shared implementation.

- [ ] **Step 3: Replace signal name strings**

Line 62: `"zenoh_message_received"` → `SIGNAL_MESSAGE_RECEIVED`
Line 66: `"zenoh_presence_changed"` → `SIGNAL_PRESENCE_CHANGED`

- [ ] **Step 4: Run agent tests**

Run: `python -m pytest tests/unit/test_agent_lifecycle.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add weechat-agent/weechat-agent.py
git commit -m "refactor: migrate weechat-agent to use wc_protocol"
```

---

## Task 8: Update `conftest.py` and clean up dead code

**Files:**
- Modify: `tests/conftest.py`
- Delete: `weechat-channel-server/tools.py` (if exists)

- [ ] **Step 1: Delete dead `tools.py`**

Note: `test_tools.py` tests `server.py` reply logic — it survives this deletion.

```bash
git rm weechat-channel-server/tools.py 2>/dev/null || true
```

- [ ] **Step 2: Move inline `shutil` import to top-level in weechat-zenoh.py**

In `weechat-zenoh.py`, move `import shutil` from line 61 (inside `_start_sidecar()`) to the top-level imports section.

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add weechat-zenoh/weechat-zenoh.py
git rm weechat-channel-server/tools.py 2>/dev/null; true
git commit -m "chore: clean up dead code and fix inline imports"
```

---

## Task 9: Run integration tests and final verification

- [ ] **Step 1: Run full test suite including integration**

Run: `python -m pytest tests/ -v --tb=short`

- [ ] **Step 2: Verify no remaining inline duplications**

Run:
```bash
# Should find ZERO results — all pair generation now goes through wc_protocol
grep -rn '"_".join(sorted' weechat-zenoh/ weechat-channel-server/ weechat-agent/

# Should find ZERO results — all topic strings now use builders
grep -rn 'wc/channels/' weechat-zenoh/ weechat-channel-server/ weechat-agent/ --include='*.py' | grep -v '# ' | grep -v 'test_'

# Signal names should only appear in wc_protocol/signals.py
grep -rn 'zenoh_message_received\|zenoh_message_sent\|zenoh_presence_changed' \
  weechat-zenoh/ weechat-channel-server/ weechat-agent/ --include='*.py'
```

Expected: All greps return empty (or only comments/test files).

- [ ] **Step 3: Final commit if any fixups needed**

```bash
git add -A
git commit -m "refactor: complete shared protocol migration — verify zero duplication"
```
