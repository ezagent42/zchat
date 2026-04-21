# Design: PRD Gap Fixes for WeeChat-Claude

**Date**: 2026-03-21
**Status**: Approved
**Scope**: Fix all identified gaps between PRD v3.1.0 and current codebase

> **Terminology**: This document follows WeeChat naming conventions:
> channel (not "room"), private (not "DM"), buffer (generic container).
> Signal payload field: `"buffer"` with values like `"channel:#general"` or `"private:@alice"`.

---

## Context

Gap analysis identified 12 issues across 4 severity levels. This spec defines fixes and testing for each, organized in 4 implementation phases with testing after each phase.

**Reference implementation**: `feishu-claude-code-channel` (TypeScript) — used as the canonical MCP channel pattern.

---

## Phase 1: Foundation Fixes

### Fix 8: start.sh `pip` → `uv`

**Problem**: `start.sh:30-33` uses `pip install eclipse-zenoh` which fails when `pip` is not on PATH.

**Fix**: Replace with `uv pip install --system`:
```diff
- pip install eclipse-zenoh --quiet
+ uv pip install --system eclipse-zenoh --quiet
```

`uv` is already a verified dependency (line 18). The `--system` flag installs into the system Python that WeeChat uses.

### Fix 12: Add `pytest-asyncio` dependency

**Problem**: `test_tools.py` uses `@pytest.mark.asyncio` but no dependency declared.

**Fix**: Add to `weechat-channel-server/pyproject.toml`:
```toml
[project.optional-dependencies]
test = ["pytest", "pytest-asyncio"]
```

Update `pytest.ini` to set asyncio mode:
```ini
[pytest]
testpaths = tests
markers = integration: requires real Zenoh peer session
asyncio_mode = auto
```

### Fix 7: Missing files from PRD §4.4

**Problem**: `weechat-channel-server/skills/` directory and `README.md` missing.

**Fix**:
- Create `weechat-channel-server/skills/` with a `.gitkeep`
- Create `weechat-channel-server/README.md` with basic plugin install/usage docs

### Phase 1 Testing

**Automated** (`tests/test_phase1.py` or inline verification):

```bash
# Fix 8: Verify start.sh no longer references bare `pip`
grep -c '^[^#]*\bpip install\b' start.sh  # expect 0

# Fix 12: Verify pytest-asyncio works
cd weechat-channel-server && uv run pytest tests/unit/test_tools.py -v

# Fix 7: Verify files exist
test -d weechat-channel-server/skills && test -f weechat-channel-server/README.md
```

**Manual**: Run `./start.sh ~/tmp testuser` on a clean machine without `pip` on PATH. Verify Zenoh installs via `uv` and system starts normally.

---

## Phase 2: weechat-zenoh Fixes

### Fix 10: Signal field alignment

**Problem**: `zenoh_message_received` signal sends `{"target": ...}` but PRD §3.5 specifies a `"buffer"` field using WeeChat buffer type conventions.

**Fix**: Extract a helper function and use it in `poll_queues_cb`:
```python
def _target_to_buffer_label(target: str) -> str:
    """Convert internal target key to WeeChat-style buffer label.

    'channel:general' → 'channel:#general'
    'private:alice_bob' → 'private:@alice' (the other nick)
    """
    if target.startswith("channel:"):
        return f"channel:#{target[8:]}"
    # Private: extract the other nick from the pair
    pair = target.split(":", 1)[1]
    nicks = pair.split("_")
    other = [n for n in nicks if n != my_nick]
    return f"private:@{other[0]}" if other else f"private:@{pair}"

# In poll_queues_cb:
buffer_label = _target_to_buffer_label(target)
json.dumps({"buffer": buffer_label, "nick": nick, "body": body, "type": msg_type})
```

**Downstream impact**: Update `weechat-agent.py:on_message_signal_cb` to read `msg.get("buffer")` instead of `msg.get("target")`.

### Fix 11: Private `zenoh_message_sent` signal

**Problem**: `buffer_input_cb` sends `zenoh_message_sent` signal for channels but not privates.

**Fix**: Add signal send in the private branch:
```python
elif buf_type == "private":
    pair = weechat.buffer_get_string(buffer, "localvar_private_pair")
    _publish_event(f"private:{pair}", "msg", input_data)
    weechat.prnt(buffer, f"{my_nick}\t{input_data}")
    # Add this:
    target_nick = weechat.buffer_get_string(buffer, "localvar_target")
    weechat.hook_signal_send("zenoh_message_sent",
        weechat.WEECHAT_HOOK_SIGNAL_STRING,
        json.dumps({"buffer": f"private:@{target_nick}", "nick": my_nick, "body": input_data}))
```

### Fix 9: `/me` action support

**Problem**: No way to send `type: "action"` messages from WeeChat.

**Fix**: In `buffer_input_cb`, detect `/me ` prefix (also handle bare `/me`):
```python
if input_data.startswith("/me ") or input_data == "/me":
    action_body = input_data[4:] if len(input_data) > 4 else ""
    _publish_event(pub_key, "action", action_body)
    weechat.prnt(buffer, f" *\t{my_nick} {action_body}")
else:
    _publish_event(pub_key, "msg", input_data)
    weechat.prnt(buffer, f"{my_nick}\t{input_data}")
```

### Fix 2+3: `/zenoh nick` broadcast + liveliness update

**Problem**: Nick change only updates local config. PRD requires broadcasting and updating liveliness tokens.

**Fix** in `zenoh_cmd_cb` nick handler:
1. Broadcast `type: "nick"` to all joined channels:
   ```python
   for channel_id in channels:
       _publish_event(f"channel:{channel_id}", "nick", json.dumps({"old": old, "new": new_nick}))
   ```
2. Update global liveliness token:
   ```python
   liveliness_tokens["_global"].undeclare()
   liveliness_tokens["_global"] = zenoh_session.liveliness().declare_token(f"wc/presence/{new_nick}")
   ```
3. Update channel liveliness tokens:
   ```python
   for channel_id in channels:
       key = f"channel:{channel_id}"
       if key in liveliness_tokens:
           liveliness_tokens[key].undeclare()
       liveliness_tokens[key] = zenoh_session.liveliness().declare_token(
           f"wc/channels/{channel_id}/presence/{new_nick}")
   ```
4. Handle `type: "nick"` in `poll_queues_cb` — update nicklist display.

**Known limitation — private pair staleness on nick change**: Private pairs are based on nicks (e.g., `alice_bob`). After renaming `alice` → `alice2`, the existing private buffer still subscribes to `wc/private/alice_bob/messages` but new messages would use `wc/private/alice2_bob/messages`. **Existing open private conversations will silently break.** For v0.1.0, this is documented as a known limitation:
- Warn the user when changing nick if privates are open
- Print a notice: `[zenoh] Warning: open private buffers may stop working after nick change. Re-open with /zenoh leave @target && /zenoh join @target`
- Future: auto-resubscribe private buffers (close old pair, open new one, update buffer localvars)

### Fix 6: `/zenoh status` enhancement

**Problem**: Status shows minimal info. PRD says "mode, peers, scouting".

**Fix**: Query Zenoh session info:
```python
elif cmd == "status":
    info = zenoh_session.info()
    zid = str(info.zid())
    routers = [str(r.zid) for r in info.routers_zid()]
    peers = [str(p.zid) for p in info.peers_zid()]
    weechat.prnt(buffer,
        f"[zenoh] zid={zid[:8]}... nick={my_nick}\n"
        f"  mode=peer  channels={len(channels)} privates={len(privates)}\n"
        f"  routers={len(routers)} peers={len(peers)}\n"
        f"  session={'open' if zenoh_session else 'closed'}")
```

### Phase 2 Testing

**Automated** — new file `tests/unit/test_zenoh_signals.py`:

| Test | What it verifies |
|------|-----------------|
| `test_signal_channel_format` | Signal payload uses `{"buffer": "channel:#general", ...}` format |
| `test_signal_private_format` | Signal payload uses `{"buffer": "private:@alice", ...}` format |
| `test_private_message_sent_signal` | Private input triggers `zenoh_message_sent` signal |
| `test_me_action_type` | `/me waves` sends `type: "action"` |
| `test_nick_broadcast_channels` | Nick change publishes `type: "nick"` to all channels |
| `test_nick_message_body` | Nick message body contains `{"old": "x", "new": "y"}` |
| `test_status_includes_zid` | `/zenoh status` output includes zid, peers, mode (mock `zenoh_session.info()`) |

These tests mock WeeChat API. Extract pure logic functions from weechat-zenoh.py:
- `format_signal_payload(target: str, nick: str, body: str, msg_type: str) -> dict`
- `parse_input(input_data: str) -> tuple[str, str]` — returns (msg_type, body)

**Automated** — integration test `tests/integration/test_nick_broadcast.py`:

| Test | What it verifies |
|------|-----------------|
| `test_nick_change_liveliness` | Old presence disappears, new one appears |
| `test_nick_message_received` | Channel subscriber gets `type: "nick"` message |

**Cannot automate** (requires WeeChat runtime):
- `/me` rendering in buffer
- Nicklist updates on nick change
- `/zenoh status` output formatting
- Buffer display of signals

**Manual test guide** → `docs/manual-testing.md` (Phase 2 section)

---

## Phase 3: weechat-channel-server Rewrite (Core)

### Fix 1: Rewrite `server.py` — low-level Server + message injection

**Problem**: `_inject_to_claude()` is a stub. No MCP notification sent.

**Architecture**:
```
Zenoh subscriber (background thread)
    → loop.call_soon_threadsafe(queue.put_nowait, (msg, ctx))
        → async poll_zenoh_queue() → write_stream.send(notification)
            → MCP stdio transport → Claude Code receives <channel> event
```

**Key design decision — write_stream, not session**: The Python MCP SDK's `Server.run()` creates a `ServerSession` internally and does not expose it. Unlike the TypeScript SDK which has `server.notification()`, the Python SDK requires going through the session. We bypass this entirely by writing notifications directly to the `write_stream` from `stdio_server()`. This stream is the same one the session uses internally — `anyio.MemoryObjectSendStream` is multi-producer safe.

**Concurrency model**: `Server.run()` is blocking (loops on incoming messages). We use `anyio.create_task_group()` to run both the MCP server and the Zenoh queue poller concurrently. No chicken-and-egg problem because the poller only needs `write_stream`, which is available before `server.run()` starts.

**Rewrite plan**:

1. Replace FastMCP with low-level `mcp.server.lowlevel.Server`
2. Register tools via `@server.list_tools()` / `@server.call_tool()`
3. Declare capabilities with `claude/channel` experimental flag:
   ```python
   init_opts = InitializationOptions(
       server_name=f"weechat-channel-{AGENT_NAME}",
       server_version="0.1.0",
       capabilities=server.get_capabilities(
           notification_options=NotificationOptions(),
           experimental_capabilities={"claude/channel": {}},
       ),
   )
   ```
4. Set up Zenoh before the MCP event loop. Zenoh callbacks run in background threads
   and cannot call `asyncio.get_running_loop()`, so we must capture the loop reference
   and use `loop.call_soon_threadsafe()` to bridge into the async world:
   ```python
   def setup_zenoh(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
       zenoh_session = zenoh.open(config)
       zenoh_session.liveliness().declare_token(f"wc/presence/{AGENT_NAME}")

       def on_dm(sample):
           # ... filter, parse ...
           loop.call_soon_threadsafe(queue.put_nowait, (msg, context))

       def on_room(sample):
           # ... @mention filter, parse ...
           loop.call_soon_threadsafe(queue.put_nowait, (msg, context))

       zenoh_session.declare_subscriber("wc/private/*/messages", on_dm, background=True)
       zenoh_session.declare_subscriber("wc/channels/*/messages", on_room, background=True)
       return zenoh_session
   ```
5. Inject messages by writing directly to the MCP stdio write stream:
   ```python
   async def inject_message(write_stream, msg: dict, context: str):
       notification = JSONRPCNotification(
           jsonrpc="2.0",
           method="notifications/claude/channel",
           params={
               "content": msg.get("body", ""),
               "meta": {
                   "chat_id": context,        # "alice" or "#general"
                   "message_id": msg.get("id", ""),
                   "user": msg.get("nick", "unknown"),
                   "ts": datetime.fromtimestamp(msg.get("ts", 0)).isoformat(),
               },
           },
       )
       await write_stream.send(
           SessionMessage(message=JSONRPCMessage(notification))
       )
   ```
6. Main entrypoint — runs MCP server and queue poller concurrently:
   ```python
   async def main():
       queue = asyncio.Queue()
       loop = asyncio.get_running_loop()

       server = create_server()          # sets up tools, instructions
       init_opts = create_init_options(server)

       async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
           # Zenoh setup AFTER stdio is ready, with 2s delay for Claude init
           await anyio.sleep(2)
           zenoh_session = setup_zenoh(queue, loop)

           async with anyio.create_task_group() as tg:
               tg.start_soon(server.run, read_stream, write_stream, init_opts)
               tg.start_soon(poll_zenoh_queue, queue, write_stream)
   ```
7. Async queue polling task:
   ```python
   async def poll_zenoh_queue(queue, write_stream):
       while True:
           msg, context = await queue.get()
           try:
               await inject_message(write_stream, msg, context)
           except Exception as e:
               print(f"[channel-server] inject error: {e}", file=sys.stderr)
   ```
8. Instructions string (from feishu pattern):
   ```python
   instructions=(
       f'You are "{AGENT_NAME}", a coding assistant connected to '
       f"WeeChat chat via Zenoh P2P messaging.\n"
       f"Messages arrive as <channel> events with sender and context "
       f"(private or #channel).\n"
       f"The sender reads WeeChat, not this terminal. Use the reply "
       f"tool to respond.\n"
       f"Always reply via the reply tool. Never print responses to stdout."
   )
   ```

**`tools.py` changes**:
- Remove `register_tools(mcp, zenoh_session)` pattern
- Export tool handlers as plain async functions
- Register in server.py via `@server.list_tools()` / `@server.call_tool()`
- Tool functions receive `zenoh_session` via closure or module-level reference

**Startup delay** (from feishu pattern): 2-second delay before connecting Zenoh subscribers to let Claude Code initialize. This is a pragmatic choice matching the reference implementation.

### Fix 4: Channel-server channel presence

**Problem**: Agent doesn't declare channel-level liveliness tokens.

**Fix**:
- Maintain `joined_channels: dict[str, LivelinessToken]` in lifespan context
- When agent first receives an @mention from a channel, auto-join:
  ```python
  if channel not in joined_channels:
      token = zenoh_session.liveliness().declare_token(
          f"wc/channels/{channel}/presence/{AGENT_NAME}")
      joined_channels[channel] = token
  ```
- Add optional `join_channel(channel_name: str)` MCP tool for Claude to join proactively
- Clean up tokens in lifespan teardown

### Phase 3 Testing

**Automated** — update `tests/unit/test_tools.py`:

| Test | What it verifies |
|------|-----------------|
| `test_reply_private_topic` | reply("alice", ...) publishes to `wc/private/{pair}/messages` |
| `test_reply_channel_topic` | reply("#general", ...) publishes to `wc/channels/general/messages` |
| `test_reply_message_fields` | Published JSON has id, nick, type, body, ts |
| `test_reply_chunking` | Long text is split into multiple publishes |

**Automated** — new `tests/unit/test_server.py`:

| Test | What it verifies |
|------|-----------------|
| `test_notification_format` | `inject_message()` produces correct JSONRPCNotification |
| `test_notification_private_chat_id` | Private context sets `meta.chat_id` = sender nick |
| `test_notification_channel_chat_id` | Channel context sets `meta.chat_id` = `#channel` |
| `test_notification_meta_fields` | All meta fields present: chat_id, message_id, user, ts |
| `test_dedup_prevents_double_inject` | Same message_id not injected twice |
| `test_own_message_ignored` | Messages from AGENT_NAME are dropped |
| `test_channel_mention_filter` | Only @mentioned messages forwarded from channels |
| `test_private_pair_filter` | Only privates involving AGENT_NAME processed |

For `inject_message()` unit tests: mock `write_stream.send()` and assert the notification payload structure.

**Automated** — new `tests/unit/test_zenoh_asyncio_bridge.py`:

| Test | What it verifies |
|------|-----------------|
| `test_thread_to_queue_bridge` | Simulates Zenoh callback from `threading.Thread`, posts to `asyncio.Queue` via `loop.call_soon_threadsafe()`, verifies async consumer picks it up |
| `test_multiple_concurrent_posts` | 10 threads post concurrently, all messages received |
| `test_write_stream_receives_notification` | Mock write_stream receives `SessionMessage` with correct `notifications/claude/channel` method |

**Automated** — update `tests/integration/test_channel_bridge.py`:

| Test | What it verifies |
|------|-----------------|
| `test_private_roundtrip_real_zenoh` | Publish private → agent filter accepts → can reply |
| `test_channel_mention_roundtrip` | Publish @mention → agent filter accepts → can reply |
| `test_channel_no_mention_ignored` | Publish without @mention → not forwarded |
| `test_channel_auto_join_presence` | First @mention triggers liveliness token declaration |

**Cannot automate** (requires Claude Code runtime):
- Full e2e: user sends WeeChat message → agent receives → Claude replies → WeeChat shows reply
- Verify `<channel>` event rendering in Claude Code session
- Verify instructions display correctly
- Verify startup delay (2s) is sufficient

**Manual test guide** → `docs/manual-testing.md` (Phase 3 section)

---

## Phase 4: weechat-agent Fixes

### Fix 5: `stop_agent()` tmux pane tracking

**Problem**: `create_agent()` doesn't store pane ID. `stop_agent()` sends C-c to entire session.

**Fix**:
1. Capture pane ID on creation:
   ```python
   result = subprocess.run(
       ["tmux", "split-window", "-h", "-P", "-F", "#{pane_id}",
        "-t", TMUX_SESSION, cmd],
       capture_output=True, text=True
   )
   pane_id = result.stdout.strip()
   agents[name]["pane_id"] = pane_id
   ```
2. Target specific pane on stop:
   ```python
   pane_id = agents[name].get("pane_id")
   if pane_id:
       subprocess.run(["tmux", "send-keys", "-t", pane_id, "C-c", ""], capture_output=True)
   ```
3. Update restart logic to use stored pane_id.

**Downstream**: Update `on_message_signal_cb` to use `msg.get("buffer")` instead of `msg.get("target")` (from Fix 10).

### Phase 4 Testing

**Automated** — update `tests/unit/test_agent_lifecycle.py`:

| Test | What it verifies |
|------|-----------------|
| `test_create_agent_stores_pane_id` | `agents[name]` has `pane_id` key after creation |
| `test_stop_agent_uses_pane_id` | tmux command includes `-t {pane_id}` |
| `test_agent0_cannot_stop` | `stop_agent("agent0")` is no-op |
| `test_restart_preserves_workspace` | After restart, workspace is same as before |
| `test_signal_uses_buffer_field` | `on_message_signal_cb` reads `buffer` not `target` |

These tests mock `subprocess.run` and `weechat` module. Extract testable logic:
- `build_tmux_create_cmd(name, workspace, session, plugin_dir) -> list[str]`
- `build_tmux_stop_cmd(pane_id) -> list[str]`
- `parse_signal_payload(signal_data: str) -> dict`

**Cannot automate** (requires tmux + Claude Code):
- Actual tmux pane creation and C-c delivery
- Agent restart with live Claude Code process
- Multi-agent spawn + selective stop

**Manual test guide** → `docs/manual-testing.md` (Phase 4 section)

---

## Manual Testing Guide

Create `docs/manual-testing.md` covering all scenarios that cannot be automated.

### Structure:

```markdown
# Manual Testing Guide

## Prerequisites
- macOS/Linux with tmux, weechat, claude, uv installed
- Two terminal windows minimum
- Claude Code account logged in

## Phase 1: Foundation
### Test: start.sh without pip
1. Ensure `pip` is NOT on PATH (rename temporarily)
2. Run `./start.sh /tmp/test testuser`
3. Verify: eclipse-zenoh installs via uv, tmux session starts

## Phase 2: weechat-zenoh
### Test: /me action rendering
1. Load weechat-zenoh, join #test
2. Type `/me waves hello`
3. Verify: buffer shows ` * alice waves hello`

### Test: Nick change broadcast
1. Alice and Bob in #test
2. Alice: `/zenoh nick alice2`
3. Verify: Bob sees nick change message, nicklist updates

### Test: /zenoh status
1. Join a channel, verify status shows zid, peer count, mode

## Phase 3: Channel Server
### Test: Full message bridge
1. `./start.sh ~/workspace alice`
2. In WeeChat: `/zenoh join @agent0`
3. Send: `hello agent0`
4. Verify: Claude Code session shows <channel> event
5. Verify: Claude uses reply tool → message appears in WeeChat

### Test: Channel @mention
1. In WeeChat: `/zenoh join #dev`
2. Send: `@agent0 list files in src/`
3. Verify: agent receives, replies to #dev

## Phase 4: Agent Management
### Test: Multi-agent pane targeting
1. `/agent create helper1 --workspace /tmp/test`
2. `/agent create helper2 --workspace /tmp/test2`
3. `/agent stop helper1`
4. Verify: Only helper1's tmux pane receives C-c
5. Verify: helper2 still running
```

---

## File Change Summary

| File | Change Type | Phase |
|------|------------|-------|
| `start.sh` | Edit (pip → uv) | 1 |
| `weechat-channel-server/pyproject.toml` | Edit (add pytest-asyncio) | 1 |
| `pytest.ini` | Edit (add asyncio_mode) | 1 |
| `weechat-channel-server/skills/.gitkeep` | Create | 1 |
| `weechat-channel-server/README.md` | Create | 1 |
| `weechat-zenoh/weechat-zenoh.py` | Edit (fixes 2,3,6,9,10,11) | 2 |
| `weechat-agent/weechat-agent.py` | Edit (signal field, fix 5) | 2+4 |
| `tests/unit/test_zenoh_signals.py` | Create | 2 |
| `tests/integration/test_nick_broadcast.py` | Create | 2 |
| `weechat-channel-server/server.py` | Rewrite | 3 |
| `weechat-channel-server/tools.py` | Rewrite (registration pattern) | 3 |
| `tests/unit/test_server.py` | Create | 3 |
| `tests/unit/test_tools.py` | Update | 3 |
| `tests/integration/test_channel_bridge.py` | Update | 3 |
| `tests/unit/test_agent_lifecycle.py` | Update | 4 |
| `docs/manual-testing.md` | Create | 1-4 |

---

## MCP Python SDK Reference

Key imports for the rewrite (verified against mcp >= 1.2.0, Python SDK source):

```python
# Server
from mcp.server.lowlevel import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio

# Notifications — write directly to stdio stream
from mcp.shared.message import SessionMessage       # from mcp.shared.message
from mcp.types import JSONRPCMessage, JSONRPCNotification  # both from mcp.types

# Tool types
from mcp import types

# Concurrency
import anyio
```

**Note**: `JSONRPCMessage` is defined in `mcp.types` (re-exported by `mcp.shared.message` as an import, but canonical location is `mcp.types`).

Server + poller concurrency pattern:
```python
async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
    async with anyio.create_task_group() as tg:
        tg.start_soon(server.run, read_stream, write_stream, init_options)
        tg.start_soon(poll_zenoh_queue, queue, write_stream)
```

Notification send pattern (bypasses ServerSession, writes directly to stdio stream):
```python
await write_stream.send(
    SessionMessage(message=JSONRPCMessage(
        JSONRPCNotification(jsonrpc="2.0", method="notifications/claude/channel",
                           params={"content": text, "meta": {...}})
    ))
)
```

**Why `write_stream.send()` instead of `session.send_message()`**: The Python SDK's `Server.run()` creates `ServerSession` internally and does not expose it. The `write_stream` from `stdio_server()` is an `anyio.MemoryObjectSendStream` that is multi-producer safe. Both the MCP server and our notification poller can write to it concurrently without locking. This matches the TypeScript SDK's `server.notification()` semantics but through the Python SDK's stream abstraction.

**Zenoh info() API** (verify against installed eclipse-zenoh version):
```python
info = zenoh_session.info()
zid = info.zid()              # returns ZenohId
routers = info.routers_zid()  # returns list[ZenohId]
peers = info.peers_zid()      # returns list[ZenohId]
```
These are methods, not properties. Verify at implementation time with `dir(zenoh_session.info())`.
