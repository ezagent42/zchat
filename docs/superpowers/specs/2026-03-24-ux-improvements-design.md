# UX Improvements Design — P0 + P1

**Date**: 2026-03-24
**Scope**: Command registry infrastructure, system message protocol, and critical UX fixes

## Overview

Two-phase improvement to weechat-claude's user-facing experience:

- **P0 (Infrastructure)**: Command registry with decorator pattern + system message protocol
- **P1 (Critical UX)**: Agent readiness notification, `/agent stop`, join confirmation, send failure feedback, malformed JSON warning

All P1 items depend on P0 infrastructure.

> **Note**: P1 issue numbers (#1, #3, #4, #5, #7, #13) reference the full UX audit list from the brainstorming session. Items #2, #6, #8-#12 are deferred to P2.

---

## P0: Command Registry

### Location

New shared package `wc_registry/` (sibling to `wc_protocol/`):

```
wc_registry/
  __init__.py      # CommandRegistry class + @command decorator
  types.py         # CommandParam, CommandSpec, CommandResult, ParsedArgs
```

> `export.py` (OpenAPI / JSON Schema export) is deferred to P2 — no consumer exists yet. P0 focuses on dispatch + help generation only.

### Core Types

```python
@dataclass
class CommandParam:
    name: str           # e.g. "name", "--workspace"
    required: bool
    help: str
    default: Any = None

@dataclass
class CommandSpec:
    name: str           # e.g. "agent create"
    args: str           # e.g. "<name> [--workspace <path>]"
    description: str
    params: list[CommandParam]
    handler: Callable

@dataclass
class CommandResult:
    success: bool
    message: str
    details: dict | None = None

    @classmethod
    def ok(cls, msg, **details):
        return cls(success=True, message=msg, details=details or None)

    @classmethod
    def error(cls, msg, **details):
        return cls(success=False, message=msg, details=details or None)

@dataclass
class ParsedArgs:
    """Result of argument parsing. Positional args by name, flags by key."""
    positional: dict[str, str]     # e.g. {"name": "helper"}
    flags: dict[str, str | bool]   # e.g. {"--workspace": "/tmp/test"}
    raw: str                       # Original unparsed string

    def get(self, name: str, default=None):
        """Look up by param name (positional or flag)."""
        return self.positional.get(name, self.flags.get(name, default))
```

### Decorator API

```python
registry = CommandRegistry(prefix="agent")

@registry.command(
    name="create",
    args="<name> [--workspace <path>]",
    description="Launch a new agent",
    params=[
        CommandParam("name", required=True, help="Agent name (without username prefix)"),
        CommandParam("--workspace", required=False, help="Custom workspace path"),
    ],
)
def cmd_agent_create(buffer, args: ParsedArgs) -> CommandResult:
    ...
```

### Argument Parsing Rules

`CommandRegistry.dispatch(buffer, raw_args)` parses the raw string as follows:

1. **Subcommand extraction**: First token matched against registered command names (e.g. `"create helper"` → subcommand `"create"`, remainder `"helper"`)
2. **Flag extraction**: Tokens starting with `--` are consumed as flags. `--key value` for flags with params, `--flag` alone for boolean flags.
3. **Positional matching**: Remaining tokens are matched left-to-right against `CommandParam` entries where `name` does not start with `--`, in declaration order.
4. **Validation**: Missing required params → `CommandResult.error()` with auto-generated usage string.

No external dependency (no argparse). Simple split-based parsing sufficient for the small command set.

### Automatic Capabilities

- **Help generation**: `/agent help` auto-generated from registry, no manual maintenance
- **Param validation**: Missing required params → auto error + usage display
- **Error format**: All errors via `CommandResult.error()` → `[plugin] Error: {msg}`
- **Export** (P2): `registry.to_openapi()`, `registry.to_json_schema()` — deferred, no consumer yet

### Integration with WeeChat

Each plugin registers a single WeeChat hook_command (e.g. `/agent`, `/zenoh`). The hook callback dispatches to the registry:

```python
def agent_command_cb(data, buffer, args):
    result = registry.dispatch(buffer, args)
    if result.success:
        weechat.prnt(buffer, f"[agent] {result.message}")
    else:
        weechat.prnt(buffer, f"[agent] Error: {result.message}")
    return weechat.WEECHAT_RC_OK
```

---

## P0: System Message Protocol

### Motivation

Current message format only supports user-level types (`msg`, `action`, `join`, `leave`, `nick`). No machine-to-machine control channel exists. P1 features (`/agent stop`, `/agent join` confirmation) require a request/response protocol.

### Message Format Extension

```json
{
  "id": "abc123",
  "nick": "alice",
  "type": "sys.stop_request",
  "body": {"reason": "user requested /agent stop"},
  "ref_id": "abc123",
  "ts": 1711276800
}
```

**Conventions:**

- `type` prefixed with `sys.` → control message, never displayed in buffer
- `body` is a JSON object (dict) for sys messages. For user messages (`msg`, `action`), `body` remains a string. The `type` field determines interpretation: `sys.*` → parse body as dict; otherwise → treat body as string. Serialization always uses `json.dumps` on the full message, so both cases are valid JSON on the wire.
- `ref_id` references original message ID for request/response pairing
- Existing types (`msg`, `action`, etc.) unchanged — fully backward compatible

### System Message Types

| type | direction | body | purpose |
|------|-----------|------|---------|
| `sys.ping` | any → any | `{}` | Heartbeat / online check |
| `sys.pong` | any → any | `{}` | Ping reply (ref_id → ping) |
| `sys.ack` | any → any | `{"status": "ok"}` | Generic acknowledgment |
| `sys.nack` | any → any | `{"status": "error", "reason": "..."}` | Generic rejection |
| `sys.stop_request` | user → agent | `{"reason": "..."}` | Request agent shutdown |
| `sys.stop_confirmed` | agent → user | `{}` | Agent confirms will stop |
| `sys.join_request` | user → agent | `{"channel": "#dev"}` | Request agent join channel |
| `sys.join_confirmed` | agent → user | `{"channel": "#dev"}` | Agent confirms joined |

### Message Routing

System messages reuse existing Zenoh topics (private channels). Receivers branch on `type.startswith("sys.")`:

- **WeeChat side**: `on_message_signal_cb` checks type; sys messages go to `_handle_sys_message()`, not buffer display
- **Channel-server side**: Subscriber callback in `server.py` checks `is_sys_message()`; sys messages go to `_handle_sys_message()` which dispatches by type

### Sidecar Communication

The sidecar communicates with the WeeChat plugin via JSON Lines over stdin/stdout (existing mechanism). New events (`joined`, `send_failed`) follow the same pattern as existing events (`message`, `presence`, `error`). The WeeChat plugin reads them in `_read_sidecar_cb()` and dispatches via `_handle_sidecar_event()`.

### Protocol in `wc_protocol/`

Add `sys_messages.py` to `wc_protocol/`:

```python
SYS_PREFIX = "sys."

def is_sys_message(msg: dict) -> bool:
    return msg.get("type", "").startswith(SYS_PREFIX)

def make_sys_message(nick: str, type: str, body: dict, ref_id: str | None = None) -> dict:
    """Create a system message. Caller provides nick (from plugin config or env)."""
    return {
        "id": random_hex(8),
        "nick": nick,
        "type": type,
        "body": body,
        "ref_id": ref_id,
        "ts": time.time(),
    }
```

---

## P1: Critical UX Improvements

### #1 Agent Readiness Notification

**Problem**: `/agent create` prints info immediately, but agent takes ~5s to become `running`. User doesn't know when agent is ready.

**Solution**: In `on_presence_signal_cb`, when agent transitions `starting` → `running`, print notification with elapsed time:

```
[agent] alice:helper is now ready (took 4.2s)
```

**Implementation**: Record `created_at` timestamp in agent registry entry. Compute delta on first presence event.

---

### #3 `/agent stop <name>`

**Problem**: Must manually switch to tmux pane and type `/exit`.

**Solution**: New command with sys message protocol:

```
User: /agent stop helper
  1. Send sys.stop_request via zenoh private (msg_id = "xxx")
  2. Agent channel-server receives sys.stop_request
     → Notifies Claude Code to clean up
     → Replies sys.stop_confirmed (ref_id = "xxx")
  3. WeeChat receives sys.stop_confirmed
     → tmux send-keys "/exit" Enter
     → Prints: [agent] alice:helper is shutting down...
  4. Presence callback detects offline
     → Prints: [agent] alice:helper is now offline
```

**Timeout**: If no `sys.stop_confirmed` within 5s, fallback to direct `tmux send-keys "/exit"`:

```
[agent] alice:helper did not respond, forcing stop...
```

**Edge cases**:
- Agent in `starting` state → skip sys message, go straight to tmux force-stop (channel-server not ready yet)
- Agent already `offline` → `CommandResult.error("alice:helper is already offline")`
- Agent unknown → `CommandResult.error("Unknown agent: alice:helper")`

**Cleanup justification**: The sys.stop_request gives channel-server a chance to gracefully leave Zenoh channels and drop liveliness tokens before the process exits. Without it, other peers see an abrupt disconnect rather than a clean leave.

**Constraint**: Primary agent (`agent0`) cannot be stopped via this command:

```
[agent] Error: alice:agent0 is the primary agent and cannot be stopped
```

---

### #4 `/agent join` Confirmation (replaces fire-and-forget)

**Problem**: Currently sends natural language message asking Claude to join. Unreliable, no confirmation.

**Solution**: Use sys message protocol:

```
User: /agent join helper #dev
  1. Send sys.join_request {"channel": "#dev"}
  2. Agent processes → replies sys.join_confirmed {"channel": "#dev"}
  3. WeeChat displays: [agent] alice:helper joined #dev
```

**Agent-side processing**: When `server.py` subscriber receives `sys.join_request`:
1. Calls the existing `join_channel()` logic (declare liveliness token, add to joined_channels)
2. Replies with `sys.join_confirmed` on the same private topic
3. No Claude Code involvement needed — this is handled entirely by channel-server

**Timeout**: If no confirmation within 10s:

```
[agent] alice:helper did not confirm joining #dev (request may still be pending)
```

---

### #5 `/zenoh join` Completion Confirmation

**Problem**: Buffer opens optimistically, but no feedback on whether Zenoh subscription succeeded.

**Solution**: Sidecar returns ack event after successful join:

```json
{"event": "joined", "channel_id": "general", "members": ["alice", "bob"]}
```

WeeChat displays:

```
[zenoh] Joined #general (2 members online)
```

This also provides presence summary on join (P2 item #8), eliminating the need for a separate implementation.

---

### #7 Message Send Failure Feedback

**Problem**: If sidecar is degraded but not fully crashed, messages are silently lost.

**Solution**: Sidecar returns nack on publish failure:

```json
{"event": "send_failed", "msg_id": "xxx", "reason": "no route to topic"}
```

WeeChat displays:

```
[zenoh] Message delivery failed: no route to topic. Use /zenoh reconnect
```

**Implementation**: WeeChat plugin generates a `msg_id` (random 8-char hex) and includes it in the send command to sidecar:

```json
{"cmd": "send", "msg_id": "a1b2c3d4", "pub_key": "channel:general", "type": "msg", "body": "hello"}
```

Sidecar wraps `session.put()` in try/except. On failure, returns `send_failed` event with the same `msg_id` so WeeChat can correlate. On success, no ack needed (optimistic display already shown).

---

### #13 Invalid JSON Warning

**Problem**: Agent's malformed JSON output silently ignored.

**Solution**: In `on_message_signal_cb`, if message body starts with `{` but fails JSON parse, log warning:

```
[agent] Warning: received malformed structured message from alice:helper
```

Do not print raw content (may be large). Only indicate source.

---

## Command Summary After P0+P1

### `/agent` commands

| command | args | description |
|---------|------|-------------|
| `create` | `<name> [--workspace <path>]` | Launch a new agent |
| `stop` | `<name>` | Stop a running agent (not agent0) |
| `list` | — | List agents with status, pane, workspace |
| `join` | `<agent> <#channel>` | Ask agent to join channel (with confirmation) |
| `help` | — | Show all agent commands (auto-generated) |

### `/zenoh` commands

| command | args | description |
|---------|------|-------------|
| `join` | `<#channel\|@nick>` | Join channel or private (with completion confirmation) |
| `leave` | `[target]` | Leave channel or private |
| `nick` | `<newname>` | Change nickname |
| `list` | — | List joined channels and privates |
| `status` | — | Show connection status |
| `reconnect` | — | Reconnect sidecar |
| `send` | `<target> <msg>` | Send message programmatically |
| `help` | — | Show all zenoh commands (auto-generated) |

---

## Files to Create/Modify

### New files
- `wc_registry/__init__.py` — CommandRegistry + @command decorator
- `wc_registry/types.py` — CommandParam, CommandSpec, CommandResult, ParsedArgs
- `wc_protocol/sys_messages.py` — System message helpers

### Modified files
- `weechat-agent/weechat-agent.py` — Refactor to use registry, add stop command, sys message handling, readiness notification, join confirmation
- `weechat-zenoh/weechat-zenoh.py` — Refactor to use registry, handle joined ack, send failure feedback, sys message routing
- `weechat-zenoh/sidecar.py` — Add joined event, send_failed event, msg_id tracking
- `weechat-channel-server/server.py` — Handle sys.stop_request, sys.join_request, sys.stop_confirmed reply
- `wc_protocol/messages.py` — Add ref_id field support (if not already there)

### Test files
- `tests/unit/test_registry.py` — Registry, decorator, dispatch, validation, help generation
- `tests/unit/test_sys_messages.py` — System message creation, parsing, is_sys_message
- `tests/unit/test_agent_commands.py` — Agent stop/join edge cases (mocked Zenoh)
- `tests/integration/test_sys_roundtrip.py` — sys.stop_request → sys.stop_confirmed round-trip over real Zenoh
