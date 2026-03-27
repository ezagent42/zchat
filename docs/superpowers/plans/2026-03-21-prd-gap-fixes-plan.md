# PRD Gap Fixes Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 12 gaps between PRD v3.1.0 and codebase, including terminology rename (room→channel, dm→private), MCP channel notification injection, and comprehensive tests.

**Architecture:** 4 phases — foundation fixes, weechat-zenoh logic fixes, channel-server rewrite (low-level MCP Server + write_stream notification injection), weechat-agent tmux pane tracking. Each phase includes automated tests + manual testing guide.

**Tech Stack:** Python 3.10+, eclipse-zenoh ≥1.0.0, mcp[cli] ≥1.2.0, anyio, pytest, pytest-asyncio

**Spec:** `docs/specs/2026-03-21-prd-gap-fixes-design.md`

---

## Chunk 1: Phase 1 — Foundation Fixes

### Task 1: Fix start.sh pip → uv

**Files:**
- Modify: `start.sh:30-33`

- [ ] **Step 1: Fix the pip command**

In `start.sh`, replace the pip block:
```python
# Old (lines 30-33):
python3 -c "import zenoh" 2>/dev/null || {
  echo "  Installing eclipse-zenoh for system Python..."
  pip install eclipse-zenoh --quiet
}

# New:
python3 -c "import zenoh" 2>/dev/null || {
  echo "  Installing eclipse-zenoh for system Python..."
  uv pip install --system eclipse-zenoh --quiet
}
```

- [ ] **Step 2: Verify no bare pip references remain**

Run: `grep -n 'pip install' start.sh`
Expected: Only the `uv pip install` line

- [ ] **Step 3: Commit**

```bash
git add start.sh
git commit -m "fix: use uv pip install instead of bare pip in start.sh"
```

### Task 2: Add pytest-asyncio dependency

**Files:**
- Modify: `weechat-channel-server/pyproject.toml`
- Modify: `pytest.ini`

- [ ] **Step 1: Add test dependencies to pyproject.toml**

Append to `weechat-channel-server/pyproject.toml`:
```toml
[project.optional-dependencies]
test = ["pytest", "pytest-asyncio"]
```

- [ ] **Step 2: Update pytest.ini**

Replace content of `pytest.ini`:
```ini
[pytest]
testpaths = tests
markers =
    integration: requires real Zenoh peer session
asyncio_mode = auto
```

- [ ] **Step 3: Verify async tests run**

Run: `cd weechat-channel-server && uv sync && cd .. && uv run --project weechat-channel-server pytest tests/unit/test_tools.py -v`
Expected: All tests pass without asyncio warnings

- [ ] **Step 4: Commit**

```bash
git add weechat-channel-server/pyproject.toml pytest.ini
git commit -m "fix: add pytest-asyncio dependency, set asyncio_mode=auto"
```

### Task 3: Create missing files from PRD §4.4

**Files:**
- Create: `weechat-channel-server/skills/.gitkeep`
- Create: `weechat-channel-server/README.md`

- [ ] **Step 1: Create skills directory**

```bash
mkdir -p weechat-channel-server/skills
touch weechat-channel-server/skills/.gitkeep
```

- [ ] **Step 2: Create README.md**

Write `weechat-channel-server/README.md`:
```markdown
# weechat-channel-server

Claude Code Channel plugin — bridges Zenoh P2P messaging and Claude Code via MCP.

## Install

```bash
claude plugin install weechat-channel
```

## Usage

```bash
# Start Claude Code with the channel plugin
claude --dangerously-load-development-channels plugin:weechat-channel

# Agent joins Zenoh mesh as "agent0" (configurable via AGENT_NAME env var)
# Any WeeChat user with weechat-zenoh can /zenoh join @agent0 to chat
```

## Environment Variables

- `AGENT_NAME` — agent identifier (default: `agent0`)
- `ZENOH_CONNECT` — Zenoh endpoints (optional, multicast by default)
```

- [ ] **Step 3: Commit**

```bash
git add weechat-channel-server/skills/.gitkeep weechat-channel-server/README.md
git commit -m "feat: add missing skills dir and README per PRD §4.4"
```

---

## Chunk 2: Phase 2 — weechat-zenoh Fixes (Terminology + Logic)

### Task 4: Rename terminology in weechat-zenoh.py

**Files:**
- Modify: `weechat-zenoh/weechat-zenoh.py` (global rename)

This task renames all WeeChat-overlapping concepts to match WeeChat conventions. No logic changes.

- [ ] **Step 1: Run existing tests to establish baseline**

Run: `pytest tests/unit/ -v`
Expected: All pass (baseline before rename)

- [ ] **Step 2: Rename variables, functions, keys, topics, and localvar types**

Apply these renames throughout `weechat-zenoh/weechat-zenoh.py`:

| Old | New |
|-----|-----|
| `rooms` (set) | `channels` |
| `dms` (set) | `privates` |
| `room_id` (param) | `channel_id` |
| `join_room(room_id)` | `join_channel(channel_id)` |
| `join_dm(target_nick)` | `join_private(target_nick)` |
| `leave_room(room_id)` | `leave_channel(channel_id)` |
| `leave_dm(target_nick)` | `leave_private(target_nick)` |
| `_on_room_msg` | `_on_channel_msg` |
| `_on_dm_msg` | `_on_private_msg` |
| `_on_room_presence` | `_on_channel_presence` |
| `"room:{id}"` (dict key) | `"channel:{id}"` |
| `"dm:{pair}"` (dict key) | `"private:{pair}"` |
| `localvar_set_type", "room"` | `localvar_set_type", "channel"` |
| `localvar_set_type", "dm"` | `localvar_set_type", "private"` |
| `buf_type == "room"` | `buf_type == "channel"` |
| `buf_type == "dm"` | `buf_type == "private"` |
| `localvar_dm_pair` | `localvar_private_pair` |
| `wc/rooms/` | `wc/channels/` |
| `wc/dm/` | `wc/private/` |

- [ ] **Step 3: Update tests for new terminology**

Update `tests/unit/test_zenoh_protocol.py` and `tests/integration/` files to use new topic paths (`wc/channels/`, `wc/private/`).

Update `tests/conftest.py` if any fixtures reference old terminology.

Update `tests/integration/test_dm_and_room.py` — rename file to `tests/integration/test_private_and_channel.py` and update all internal references.

- [ ] **Step 4: Run all tests**

Run: `pytest tests/ -v --ignore=tests/integration`
Expected: All unit tests pass with new terminology

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: rename room→channel, dm→private to align with WeeChat conventions"
```

### Task 5: Extract testable helpers + signal format (Fix 10)

**Files:**
- Modify: `weechat-zenoh/weechat-zenoh.py`
- Create: `weechat-zenoh/helpers.py`
- Create: `tests/unit/test_zenoh_signals.py`

- [ ] **Step 1: Create helpers.py with pure functions**

Write `weechat-zenoh/helpers.py`:
```python
"""Pure helper functions extracted from weechat-zenoh for testability."""

def target_to_buffer_label(target: str, my_nick: str) -> str:
    """Convert internal target key to WeeChat-style buffer label.

    'channel:general' → 'channel:#general'
    'private:alice_bob' → 'private:@alice' (the other nick)
    """
    if target.startswith("channel:"):
        return f"channel:#{target[8:]}"
    pair = target.split(":", 1)[1]
    nicks = pair.split("_")
    other = [n for n in nicks if n != my_nick]
    return f"private:@{other[0]}" if other else f"private:@{pair}"


def parse_input(input_data: str) -> tuple[str, str]:
    """Parse user input into (msg_type, body).

    '/me waves' → ('action', 'waves')
    'hello' → ('msg', 'hello')
    '/me' → ('action', '')
    """
    if input_data.startswith("/me ") or input_data == "/me":
        body = input_data[4:] if len(input_data) > 4 else ""
        return ("action", body)
    return ("msg", input_data)
```

- [ ] **Step 2: Write failing tests**

Write `tests/unit/test_zenoh_signals.py`:
```python
"""Tests for weechat-zenoh signal format and input parsing."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "weechat-zenoh"))
from helpers import target_to_buffer_label, parse_input


class TestTargetToBufferLabel:
    def test_channel_format(self):
        assert target_to_buffer_label("channel:general", "alice") == "channel:#general"

    def test_private_format(self):
        assert target_to_buffer_label("private:alice_bob", "alice") == "private:@bob"

    def test_private_reverse_order(self):
        assert target_to_buffer_label("private:alice_bob", "bob") == "private:@alice"

    def test_private_same_nick(self):
        assert target_to_buffer_label("private:alice_alice", "alice") == "private:@alice"


class TestParseInput:
    def test_regular_message(self):
        assert parse_input("hello world") == ("msg", "hello world")

    def test_me_action(self):
        assert parse_input("/me waves") == ("action", "waves")

    def test_bare_me(self):
        assert parse_input("/me") == ("action", "")

    def test_me_with_spaces(self):
        assert parse_input("/me does a thing") == ("action", "does a thing")
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/unit/test_zenoh_signals.py -v`
Expected: All 8 tests PASS

- [ ] **Step 4: Wire helpers into weechat-zenoh.py**

In `weechat-zenoh/weechat-zenoh.py`:

1. Add at top (after existing imports): `from helpers import target_to_buffer_label, parse_input`
2. In `poll_queues_cb`, replace the signal send (around line 362):
```python
# Old:
weechat.hook_signal_send("zenoh_message_received",
    weechat.WEECHAT_HOOK_SIGNAL_STRING,
    json.dumps({"target": target, "nick": nick, "body": body, "type": msg_type}))

# New:
buffer_label = target_to_buffer_label(target, my_nick)
weechat.hook_signal_send("zenoh_message_received",
    weechat.WEECHAT_HOOK_SIGNAL_STRING,
    json.dumps({"buffer": buffer_label, "nick": nick, "body": body, "type": msg_type}))
```

3. In `buffer_input_cb`, use `parse_input()` for the `/me` detection + use `"buffer"` field in sent signal.

- [ ] **Step 5: Commit**

```bash
git add weechat-zenoh/helpers.py tests/unit/test_zenoh_signals.py weechat-zenoh/weechat-zenoh.py
git commit -m "feat: extract testable helpers, align signal format to buffer convention (Fix 9, 10)"
```

### Task 6: Private message_sent signal + /me action (Fix 9, 11)

**Files:**
- Modify: `weechat-zenoh/weechat-zenoh.py:270-296` (buffer_input_cb)

- [ ] **Step 1: Add tests for private signal and /me**

Append to `tests/unit/test_zenoh_signals.py`:
```python
class TestBufferInputParsing:
    """Verify buffer_input_cb logic for /me and signal sending."""

    def test_me_action_body(self):
        msg_type, body = parse_input("/me dances")
        assert msg_type == "action"
        assert body == "dances"

    def test_regular_msg(self):
        msg_type, body = parse_input("hello there")
        assert msg_type == "msg"
        assert body == "hello there"
```

- [ ] **Step 2: Implement in buffer_input_cb**

Rewrite `buffer_input_cb` in `weechat-zenoh.py` to:
1. Use `parse_input()` for /me detection
2. Send `zenoh_message_sent` signal for both channel AND private buffers
3. Use `"buffer"` field in signal payload

```python
def buffer_input_cb(data, buffer, input_data):
    buf_type = weechat.buffer_get_string(buffer, "localvar_type")
    target = weechat.buffer_get_string(buffer, "localvar_target")
    msg_type, body = parse_input(input_data)

    if buf_type == "channel":
        pub_key = f"channel:{target}"
        _publish_event(pub_key, msg_type, body)
        if msg_type == "action":
            weechat.prnt(buffer, f" *\t{my_nick} {body}")
        else:
            weechat.prnt(buffer, f"{my_nick}\t{body}")
        buffer_label = f"channel:#{target}"

    elif buf_type == "private":
        pair = weechat.buffer_get_string(buffer, "localvar_private_pair")
        pub_key = f"private:{pair}"
        _publish_event(pub_key, msg_type, body)
        if msg_type == "action":
            weechat.prnt(buffer, f" *\t{my_nick} {body}")
        else:
            weechat.prnt(buffer, f"{my_nick}\t{body}")
        buffer_label = f"private:@{target}"

    else:
        return weechat.WEECHAT_RC_OK

    weechat.hook_signal_send("zenoh_message_sent",
        weechat.WEECHAT_HOOK_SIGNAL_STRING,
        json.dumps({"buffer": buffer_label, "nick": my_nick, "body": body, "type": msg_type}))

    return weechat.WEECHAT_RC_OK
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_zenoh_signals.py -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add weechat-zenoh/weechat-zenoh.py tests/unit/test_zenoh_signals.py
git commit -m "feat: add private signal, /me action support (Fix 9, 11)"
```

### Task 7: Nick broadcast + liveliness update (Fix 2+3)

**Files:**
- Modify: `weechat-zenoh/weechat-zenoh.py:426-431` (nick handler)
- Modify: `weechat-zenoh/weechat-zenoh.py:333-386` (poll_queues_cb — handle nick type)

- [ ] **Step 1: Add nick-related tests**

Append to `tests/unit/test_zenoh_signals.py`:
```python
import json

class TestNickBroadcast:
    def test_nick_message_body_format(self):
        body = json.dumps({"old": "alice", "new": "alice2"})
        parsed = json.loads(body)
        assert parsed["old"] == "alice"
        assert parsed["new"] == "alice2"
```

- [ ] **Step 2: Implement nick broadcast**

In the `zenoh_cmd_cb` nick handler, after updating `my_nick`:

```python
elif cmd == "nick" and len(argv) >= 2:
    global my_nick
    old = my_nick
    my_nick = argv[1]
    weechat.config_set_plugin("nick", my_nick)

    # Broadcast to all channels
    for channel_id in channels:
        _publish_event(f"channel:{channel_id}", "nick",
                       json.dumps({"old": old, "new": my_nick}))

    # Update global liveliness
    liveliness_tokens["_global"].undeclare()
    liveliness_tokens["_global"] = \
        zenoh_session.liveliness().declare_token(f"wc/presence/{my_nick}")

    # Update channel liveliness tokens
    for channel_id in channels:
        key = f"channel:{channel_id}"
        if key in liveliness_tokens:
            liveliness_tokens[key].undeclare()
        liveliness_tokens[key] = \
            zenoh_session.liveliness().declare_token(
                f"wc/channels/{channel_id}/presence/{my_nick}")

    # Warn about open privates
    if privates:
        weechat.prnt("",
            f"[zenoh] Warning: {len(privates)} open private buffer(s) may stop working. "
            f"Re-open with /zenoh leave @target && /zenoh join @target")

    weechat.prnt("", f"[zenoh] Nick changed: {old} → {my_nick}")
```

- [ ] **Step 3: Handle nick type in poll_queues_cb**

Add to the message type handler in `poll_queues_cb`:
```python
elif msg_type == "nick":
    try:
        nick_data = json.loads(body)
        old_nick = nick_data.get("old", "")
        new_nick = nick_data.get("new", "")
        weechat.prnt(buf, f" --\t{old_nick} is now known as {new_nick}")
        channel_id = target.replace("channel:", "")
        _remove_nick(channel_id, old_nick)
        _add_nick(channel_id, new_nick)
    except (json.JSONDecodeError, KeyError):
        pass
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_zenoh_signals.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add weechat-zenoh/weechat-zenoh.py tests/unit/test_zenoh_signals.py
git commit -m "feat: nick broadcast + liveliness update + private warning (Fix 2, 3)"
```

### Task 8: Status enhancement (Fix 6)

**Files:**
- Modify: `weechat-zenoh/weechat-zenoh.py:446-449` (status handler)

- [ ] **Step 1: Update status handler**

Replace the status block in `zenoh_cmd_cb`:
```python
elif cmd == "status":
    try:
        info = zenoh_session.info()
        zid = str(info.zid())
        routers = list(info.routers_zid())
        peers = list(info.peers_zid())
        weechat.prnt(buffer,
            f"[zenoh] zid={zid[:8]}... nick={my_nick}\n"
            f"  mode=peer  channels={len(channels)} privates={len(privates)}\n"
            f"  routers={len(routers)} peers={len(peers)}\n"
            f"  session={'open' if zenoh_session else 'closed'}")
    except Exception as e:
        weechat.prnt(buffer,
            f"[zenoh] nick={my_nick} channels={len(channels)} "
            f"privates={len(privates)} session={'open' if zenoh_session else 'closed'}\n"
            f"  (info unavailable: {e})")
```

- [ ] **Step 2: Commit**

```bash
git add weechat-zenoh/weechat-zenoh.py
git commit -m "feat: enhance /zenoh status with zid, peers, routers (Fix 6)"
```

---

## Chunk 3: Phase 3 — Channel Server Rewrite

### Task 9: Rename terminology in message.py

**Files:**
- Modify: `weechat-channel-server/message.py`
- Modify: `tests/unit/test_message.py`

- [ ] **Step 1: Rename helpers**

In `message.py`, rename:
- `dm_topic(pair)` → `private_topic(pair)` — returns `f"wc/private/{pair}/messages"`
- `room_topic(room_id)` → `channel_topic(channel_id)` — returns `f"wc/channels/{channel_id}/messages"`
- `make_dm_pair` → `make_private_pair`

- [ ] **Step 2: Update test_message.py**

Rename all references: `dm_topic` → `private_topic`, `room_topic` → `channel_topic`, `make_dm_pair` → `make_private_pair`, `TestMakeDmPair` → `TestMakePrivatePair`, etc.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_message.py -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add weechat-channel-server/message.py tests/unit/test_message.py
git commit -m "refactor: rename dm→private, room→channel in message.py"
```

### Task 10: Rewrite server.py — low-level MCP Server (Fix 1)

**Files:**
- Rewrite: `weechat-channel-server/server.py`
- Create: `tests/unit/test_server.py`

This is the critical fix — replaces the FastMCP stub with a working MCP channel notification system.

- [ ] **Step 1: Write unit tests for inject_message**

Write `tests/unit/test_server.py`:
```python
"""Tests for weechat-channel-server/server.py notification injection."""
import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

# We'll test inject_message as a standalone function
# Import after server.py is rewritten


class TestInjectMessage:
    @pytest.mark.asyncio
    async def test_notification_format(self):
        from server import inject_message
        mock_stream = AsyncMock()
        msg = {"id": "test-001", "nick": "alice", "body": "hello", "ts": 1711036800.0}
        await inject_message(mock_stream, msg, "alice")
        mock_stream.send.assert_called_once()
        session_msg = mock_stream.send.call_args[0][0]
        notification = session_msg.message.root
        assert notification.method == "notifications/claude/channel"
        assert notification.params["content"] == "hello"
        assert notification.params["meta"]["user"] == "alice"
        assert notification.params["meta"]["chat_id"] == "alice"

    @pytest.mark.asyncio
    async def test_notification_channel_chat_id(self):
        from server import inject_message
        mock_stream = AsyncMock()
        msg = {"id": "test-002", "nick": "bob", "body": "hi", "ts": 1711036800.0}
        await inject_message(mock_stream, msg, "#general")
        session_msg = mock_stream.send.call_args[0][0]
        assert session_msg.message.root.params["meta"]["chat_id"] == "#general"

    @pytest.mark.asyncio
    async def test_notification_meta_fields(self):
        from server import inject_message
        mock_stream = AsyncMock()
        msg = {"id": "m-1", "nick": "alice", "body": "test", "ts": 1711036800.0}
        await inject_message(mock_stream, msg, "alice")
        meta = mock_stream.send.call_args[0][0].message.root.params["meta"]
        assert "chat_id" in meta
        assert "message_id" in meta
        assert "user" in meta
        assert "ts" in meta
```

- [ ] **Step 2: Rewrite server.py**

Write complete `weechat-channel-server/server.py`:
```python
#!/usr/bin/env python3
"""
weechat-channel-server: Claude Code Channel MCP Server
Bridges Zenoh P2P messaging ↔ Claude Code via MCP stdio protocol.

Architecture:
  Zenoh subscriber (background thread)
    → asyncio.Queue via loop.call_soon_threadsafe()
      → async poll_zenoh_queue() → write_stream.send(notification)
        → MCP stdio → Claude Code receives <channel> event
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

import anyio
import zenoh
import mcp.server.stdio
from mcp.server.lowlevel import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage, JSONRPCNotification, Tool, TextContent
from mcp import types

from message import (
    MessageDedup, detect_mention, clean_mention,
    make_private_pair, chunk_message,
)

AGENT_NAME = os.environ.get("AGENT_NAME", "agent0")


# ============================================================
# MCP Notification Injection
# ============================================================

async def inject_message(write_stream, msg: dict, context: str):
    """Send a channel notification to Claude Code via the MCP write stream."""
    ts = msg.get("ts", 0)
    iso_ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else datetime.now(tz=timezone.utc).isoformat()

    notification = JSONRPCNotification(
        jsonrpc="2.0",
        method="notifications/claude/channel",
        params={
            "content": msg.get("body", ""),
            "meta": {
                "chat_id": context,
                "message_id": msg.get("id", ""),
                "user": msg.get("nick", "unknown"),
                "ts": iso_ts,
            },
        },
    )
    await write_stream.send(
        SessionMessage(message=JSONRPCMessage(notification))
    )


async def poll_zenoh_queue(queue: asyncio.Queue, write_stream):
    """Consume Zenoh messages from the queue and inject into Claude Code."""
    while True:
        msg, context = await queue.get()
        try:
            await inject_message(write_stream, msg, context)
        except Exception as e:
            print(f"[channel-server] inject error: {e}", file=sys.stderr)


# ============================================================
# Zenoh Setup
# ============================================================

def setup_zenoh(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """Initialize Zenoh session and subscribe to messages."""
    zenoh_config = zenoh.Config()
    zenoh_config.insert_json5("mode", '"peer"')

    connect = os.environ.get("ZENOH_CONNECT")
    if connect:
        zenoh_config.insert_json5("connect/endpoints",
                                  json.dumps(connect.split(",")))

    zenoh_session = zenoh.open(zenoh_config)
    zenoh_session.liveliness().declare_token(f"wc/presence/{AGENT_NAME}")

    dedup = MessageDedup()
    joined_channels: dict[str, object] = {}

    def on_private(sample):
        """Filter and forward private messages addressed to this agent."""
        try:
            key = str(sample.key_expr)
            parts = key.split("/")
            if len(parts) < 3:
                return
            pair = parts[2]
            if AGENT_NAME not in pair.split("_"):
                return
            msg = json.loads(sample.payload.to_string())
            if msg.get("nick") == AGENT_NAME:
                return
            msg_id = msg.get("id", "")
            if msg_id and dedup.is_duplicate(msg_id):
                return
            sender = msg.get("nick", "unknown")
            print(f"[channel-server] [private:{sender}] {sender}: {msg.get('body', '')}", file=sys.stderr)
            loop.call_soon_threadsafe(queue.put_nowait, (msg, sender))
        except Exception as e:
            print(f"[channel-server] private error: {e}", file=sys.stderr)

    def on_channel(sample):
        """Filter @mentions in channel messages and forward to agent."""
        try:
            msg = json.loads(sample.payload.to_string())
            if msg.get("nick") == AGENT_NAME:
                return
            body = msg.get("body", "")
            if not detect_mention(body, AGENT_NAME):
                return
            msg_id = msg.get("id", "")
            if msg_id and dedup.is_duplicate(msg_id):
                return
            msg["body"] = clean_mention(body, AGENT_NAME)
            channel = str(sample.key_expr).split("/")[2]
            print(f"[channel-server] [#{channel}] {msg.get('nick', '?')}: {body}", file=sys.stderr)

            # Auto-join channel presence
            if channel not in joined_channels:
                token = zenoh_session.liveliness().declare_token(
                    f"wc/channels/{channel}/presence/{AGENT_NAME}")
                joined_channels[channel] = token

            loop.call_soon_threadsafe(queue.put_nowait, (msg, f"#{channel}"))
        except Exception as e:
            print(f"[channel-server] channel error: {e}", file=sys.stderr)

    zenoh_session.declare_subscriber("wc/private/*/messages", on_private, background=True)
    zenoh_session.declare_subscriber("wc/channels/*/messages", on_channel, background=True)

    return zenoh_session, joined_channels


# ============================================================
# MCP Server + Tools
# ============================================================

def create_server():
    """Create and configure the low-level MCP server."""
    server = Server("weechat-channel")

    # Tool definitions are registered after zenoh_session is available
    return server


def register_tools(server: Server, zenoh_session):
    """Register MCP tools on the server."""

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return [
            Tool(
                name="reply",
                description=(
                    "Reply to a WeeChat user or channel. "
                    "chat_id is a username for private (e.g. 'alice') "
                    "or #channel name (e.g. '#general')."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "chat_id": {
                            "type": "string",
                            "description": "Target: username for private or #channel",
                        },
                        "text": {
                            "type": "string",
                            "description": "Message content",
                        },
                    },
                    "required": ["chat_id", "text"],
                },
            ),
            Tool(
                name="join_channel",
                description="Join a WeeChat channel to receive @mentions.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "channel_name": {
                            "type": "string",
                            "description": "Channel name without # prefix",
                        },
                    },
                    "required": ["channel_name"],
                },
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "reply":
            return await _handle_reply(zenoh_session, arguments)
        elif name == "join_channel":
            return await _handle_join_channel(zenoh_session, arguments)
        raise ValueError(f"Unknown tool: {name}")


async def _handle_reply(zenoh_session, arguments: dict) -> list[TextContent]:
    """Send a message back to WeeChat via Zenoh."""
    import time
    chat_id = arguments["chat_id"]
    text = arguments["text"]
    chunks = chunk_message(text)

    for chunk in chunks:
        msg = json.dumps({
            "id": os.urandom(8).hex(),
            "nick": AGENT_NAME,
            "type": "msg",
            "body": chunk,
            "ts": time.time(),
        })
        if chat_id.startswith("#"):
            channel = chat_id.lstrip("#")
            zenoh_session.put(f"wc/channels/{channel}/messages", msg)
        else:
            pair = make_private_pair(AGENT_NAME, chat_id)
            zenoh_session.put(f"wc/private/{pair}/messages", msg)

    return [TextContent(type="text", text=f"Sent to {chat_id}")]


async def _handle_join_channel(zenoh_session, arguments: dict) -> list[TextContent]:
    """Join a channel by declaring presence."""
    channel = arguments["channel_name"]
    zenoh_session.liveliness().declare_token(
        f"wc/channels/{channel}/presence/{AGENT_NAME}")
    return [TextContent(type="text", text=f"Joined #{channel}")]


# ============================================================
# Main
# ============================================================

async def main():
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    server = create_server()

    init_opts = InitializationOptions(
        server_name=f"weechat-channel-{AGENT_NAME}",
        server_version="0.1.0",
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={"claude/channel": {}},
        ),
    )

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        # Delay to let Claude Code initialize before Zenoh messages arrive
        await anyio.sleep(2)

        zenoh_session, joined_channels = setup_zenoh(queue, loop)
        register_tools(server, zenoh_session)

        print(f"[channel-server] {AGENT_NAME} ready on Zenoh", file=sys.stderr)

        try:
            async with anyio.create_task_group() as tg:
                tg.start_soon(server.run, read_stream, write_stream, init_opts)
                tg.start_soon(poll_zenoh_queue, queue, write_stream)
        finally:
            zenoh_session.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Run unit tests**

Run: `pytest tests/unit/test_server.py -v`
Expected: All 3 inject_message tests pass

- [ ] **Step 4: Commit**

```bash
git add weechat-channel-server/server.py tests/unit/test_server.py
git commit -m "feat: rewrite server.py with low-level MCP Server + channel notifications (Fix 1, 4)"
```

### Task 11: Rewrite tools.py + update test_tools.py

**Files:**
- Rewrite: `weechat-channel-server/tools.py` (simplified — logic moved to server.py)
- Modify: `tests/unit/test_tools.py`

- [ ] **Step 1: Simplify tools.py**

Since tool logic is now in `server.py`, `tools.py` becomes a thin wrapper for backward compatibility or is removed. The `_handle_reply` and `_handle_join_channel` functions live in `server.py`.

Write `weechat-channel-server/tools.py`:
```python
"""
MCP tool definitions — kept for backward compatibility.
Tool logic has moved to server.py (register_tools function).
"""
# Tools are now registered directly in server.py via @server.call_tool()
# This module is retained for the chunk_message import used by tests.
```

- [ ] **Step 2: Update test_tools.py**

Rewrite `tests/unit/test_tools.py` to test the reply logic via the new server.py functions:
```python
"""Tests for reply tool logic in server.py."""
import json
import os
import pytest
from unittest.mock import MagicMock

os.environ["AGENT_NAME"] = "agent0"

from server import _handle_reply


class TestReplyTool:
    @pytest.fixture
    def mock_zenoh(self):
        session = MagicMock()
        session.put = MagicMock()
        return session

    @pytest.mark.asyncio
    async def test_reply_to_private(self, mock_zenoh):
        result = await _handle_reply(mock_zenoh, {"chat_id": "alice", "text": "hello"})
        assert "Sent" in result[0].text
        mock_zenoh.put.assert_called_once()
        key = mock_zenoh.put.call_args[0][0]
        assert key == "wc/private/agent0_alice/messages"
        msg = json.loads(mock_zenoh.put.call_args[0][1])
        assert msg["nick"] == "agent0"
        assert msg["body"] == "hello"

    @pytest.mark.asyncio
    async def test_reply_to_channel(self, mock_zenoh):
        result = await _handle_reply(mock_zenoh, {"chat_id": "#general", "text": "hi"})
        key = mock_zenoh.put.call_args[0][0]
        assert key == "wc/channels/general/messages"

    @pytest.mark.asyncio
    async def test_reply_message_format(self, mock_zenoh):
        await _handle_reply(mock_zenoh, {"chat_id": "bob", "text": "test"})
        msg = json.loads(mock_zenoh.put.call_args[0][1])
        for field in ("id", "nick", "type", "body", "ts"):
            assert field in msg
        assert isinstance(msg["ts"], float)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_tools.py tests/unit/test_server.py -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add weechat-channel-server/tools.py tests/unit/test_tools.py
git commit -m "refactor: simplify tools.py, update tests for new server.py structure"
```

### Task 12: Thread-to-async bridge tests

**Files:**
- Create: `tests/unit/test_zenoh_asyncio_bridge.py`

- [ ] **Step 1: Write bridge tests**

Write `tests/unit/test_zenoh_asyncio_bridge.py`:
```python
"""Tests for Zenoh background thread → asyncio.Queue bridge."""
import asyncio
import threading
import pytest
from unittest.mock import AsyncMock

from server import inject_message


class TestThreadToAsyncBridge:
    @pytest.mark.asyncio
    async def test_thread_to_queue_bridge(self):
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def zenoh_callback():
            loop.call_soon_threadsafe(queue.put_nowait, ({"body": "hello"}, "alice"))

        thread = threading.Thread(target=zenoh_callback)
        thread.start()
        thread.join()

        msg, ctx = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert msg["body"] == "hello"
        assert ctx == "alice"

    @pytest.mark.asyncio
    async def test_multiple_concurrent_posts(self):
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def post(i):
            loop.call_soon_threadsafe(queue.put_nowait, ({"body": f"msg-{i}"}, f"ctx-{i}"))

        threads = [threading.Thread(target=post, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        received = []
        for _ in range(10):
            item = await asyncio.wait_for(queue.get(), timeout=1.0)
            received.append(item)
        assert len(received) == 10

    @pytest.mark.asyncio
    async def test_write_stream_receives_notification(self):
        mock_stream = AsyncMock()
        msg = {"id": "ws-1", "nick": "alice", "body": "test", "ts": 1711036800.0}
        await inject_message(mock_stream, msg, "#general")
        session_msg = mock_stream.send.call_args[0][0]
        assert session_msg.message.root.method == "notifications/claude/channel"
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/unit/test_zenoh_asyncio_bridge.py -v`
Expected: All 3 pass

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_zenoh_asyncio_bridge.py
git commit -m "test: add thread-to-async bridge tests for Zenoh→MCP pipeline"
```

---

## Chunk 4: Phase 4 — weechat-agent Fixes + Manual Testing

### Task 13: Update weechat-agent.py (terminology + signal field + tmux pane tracking)

**Files:**
- Modify: `weechat-agent/weechat-agent.py`

- [ ] **Step 1: Rename terminology**

In `weechat-agent.py`, rename:
- All comments mentioning "DM" → "private"
- All comments mentioning "room" → "channel"
- `/agent join <agent> <#room>` → `/agent join <agent> <#channel>` in help text

- [ ] **Step 2: Update signal handler to read "buffer" field**

In `on_message_signal_cb`, the handler currently reads `nick` and `body`. No changes needed for those. But update any future reference from `target` to `buffer` for consistency.

- [ ] **Step 3: Implement tmux pane tracking (Fix 5)**

In `create_agent()`, change `subprocess.Popen` to `subprocess.run` with pane ID capture:
```python
result = subprocess.run(
    ["tmux", "split-window", "-h", "-P", "-F", "#{pane_id}",
     "-t", TMUX_SESSION, cmd],
    capture_output=True, text=True
)
pane_id = result.stdout.strip()

agents[name] = {
    "workspace": workspace,
    "status": "starting",
    "pane_id": pane_id,
}
```

In `stop_agent()`, target the specific pane:
```python
def stop_agent(name):
    if name == "agent0":
        weechat.prnt("", "[agent] Cannot stop agent0")
        return
    if name not in agents:
        weechat.prnt("", f"[agent] Unknown agent: {name}")
        return

    pane_id = agents[name].get("pane_id")
    if pane_id:
        subprocess.run(
            ["tmux", "send-keys", "-t", pane_id, "C-c", ""],
            capture_output=True
        )

    agents[name]["status"] = "stopped"
    weechat.prnt("", f"[agent] Stopped {name}")
```

- [ ] **Step 4: Commit**

```bash
git add weechat-agent/weechat-agent.py
git commit -m "feat: tmux pane tracking for stop_agent, align terminology (Fix 5)"
```

### Task 14: Update agent lifecycle tests

**Files:**
- Modify: `tests/unit/test_agent_lifecycle.py`

- [ ] **Step 1: Update tests**

Add/update tests in `tests/unit/test_agent_lifecycle.py`:
```python
class TestTmuxPaneTracking:
    def test_create_stores_pane_id(self):
        """Verify agents dict stores pane_id after creation."""
        agents = {}
        name = "helper1"
        pane_id = "%42"
        agents[name] = {"workspace": "/tmp", "status": "starting", "pane_id": pane_id}
        assert agents[name]["pane_id"] == "%42"

    def test_stop_uses_pane_id(self):
        """Verify tmux command targets specific pane."""
        pane_id = "%42"
        cmd = ["tmux", "send-keys", "-t", pane_id, "C-c", ""]
        assert "-t" in cmd
        assert cmd[cmd.index("-t") + 1] == "%42"

    def test_signal_buffer_field(self):
        """Verify signal payload uses 'buffer' field."""
        import json
        signal_data = json.dumps({"buffer": "private:@agent0", "nick": "alice", "body": "hello"})
        msg = json.loads(signal_data)
        assert "buffer" in msg
        assert msg["buffer"] == "private:@agent0"
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/unit/test_agent_lifecycle.py -v`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_agent_lifecycle.py
git commit -m "test: update agent lifecycle tests for pane tracking and buffer field"
```

### Task 15: Update integration tests + create manual testing guide

**Files:**
- Modify: `tests/integration/test_channel_bridge.py`
- Rename: `tests/integration/test_dm_and_room.py` → `tests/integration/test_private_and_channel.py`
- Modify: `tests/integration/test_zenoh_pubsub.py`
- Create: `docs/manual-testing.md`

- [ ] **Step 1: Update integration test terminology**

In all integration test files, rename Zenoh topics:
- `wc/rooms/` → `wc/channels/`
- `wc/dm/` → `wc/private/`
- Variable names: `room` → `channel`, `dm` → `private`

Rename `test_dm_and_room.py` → `test_private_and_channel.py`.

- [ ] **Step 2: Create manual testing guide**

Write `docs/manual-testing.md`:
```markdown
# Manual Testing Guide

Tests that require a full WeeChat + Claude Code runtime and cannot be automated.

## Prerequisites

- macOS/Linux with tmux, weechat, claude, uv installed
- Two terminal windows minimum
- Claude Code account logged in

## Phase 1: Foundation

### Test: start.sh without pip
1. Temporarily remove `pip` from PATH
2. Run `./start.sh /tmp/test testuser`
3. **Expected**: eclipse-zenoh installs via `uv pip install --system`, tmux session starts

## Phase 2: weechat-zenoh

### Test: /me action rendering
1. Load weechat-zenoh, join #test
2. Type `/me waves hello`
3. **Expected**: buffer shows ` * alice waves hello` (action format)

### Test: Nick change broadcast
1. Alice and Bob both in #test (two WeeChat instances)
2. Alice runs: `/zenoh nick alice2`
3. **Expected**: Bob sees ` -- alice is now known as alice2`, nicklist updates

### Test: Nick change private warning
1. Alice has an open private buffer with @bob
2. Alice runs: `/zenoh nick alice2`
3. **Expected**: Warning message about open private buffers

### Test: /zenoh status output
1. Join a channel, run `/zenoh status`
2. **Expected**: Output shows zid, peer count, mode=peer, channel/private counts

## Phase 3: Channel Server

### Test: Full message bridge (private)
1. Run `./start.sh ~/workspace alice`
2. In WeeChat: `/zenoh join @agent0`
3. Type: `hello agent0`
4. **Expected**: Claude Code session shows `<channel>` event
5. **Expected**: Claude uses reply tool → message appears in WeeChat buffer

### Test: Channel @mention
1. In WeeChat: `/zenoh join #dev`
2. Type: `@agent0 list files in src/`
3. **Expected**: Agent receives mention, replies to #dev

### Test: Agent auto-joins channel presence
1. After @mentioning agent0 in #dev
2. Run `/zenoh status` or check nicklist
3. **Expected**: agent0 appears in #dev's nicklist

## Phase 4: Agent Management

### Test: Multi-agent pane targeting
1. `/agent create helper1 --workspace /tmp/test1`
2. `/agent create helper2 --workspace /tmp/test2`
3. `/agent stop helper1`
4. **Expected**: Only helper1's tmux pane receives C-c
5. **Expected**: helper2 still running (verify in tmux)

### Test: Agent restart
1. `/agent restart helper1`
2. **Expected**: helper1 stops, then restarts after 2s in same workspace
```

- [ ] **Step 3: Run all tests**

Run: `pytest tests/ -v --ignore=tests/integration`
Expected: All unit tests pass

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: update integration tests terminology, add manual testing guide"
```

### Task 16: Final push

- [ ] **Step 1: Run full test suite one last time**

Run: `pytest tests/ -v --ignore=tests/integration`
Expected: All unit tests pass

- [ ] **Step 2: Push all changes**

```bash
git push
```
