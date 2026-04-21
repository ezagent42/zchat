# UX Improvements Design — P0 + P1 + P2

**Date**: 2026-03-24
**Scope**: Command registry infrastructure, system message protocol, critical UX fixes, and enhancement features

## Overview

Three-phase improvement to weechat-claude's user-facing experience:

- **P0 (Infrastructure)**: Command registry with decorator pattern + system message protocol
- **P1 (Critical UX)**: Agent readiness notification, `/agent stop`, join confirmation, send failure feedback, malformed JSON warning
- **P2 (Enhancements)**: Richer agent/channel info, new commands, export, quality-of-life improvements

All P1 items depend on P0 infrastructure. P2 items depend on P0 + P1.

> **Note**: Issue numbers (#1–#14) reference the full UX audit list from the brainstorming session.

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
| `sys.status_request` | user → agent | `{}` | Request agent status (P2) |
| `sys.status_response` | agent → user | `{"channels": [...], "messages_sent": N, "messages_received": N}` | Agent status reply (P2) |

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

## P2: Enhancement Features

### #2 `/agent list` Enhanced Output

**Problem**: Current output only shows name, status, pane, workspace. No uptime or channel membership info.

**Solution**: Enrich the list output with uptime and joined channels:

```
[agent] Agents:
  alice:agent0   running  12m  %41  #general, #dev     /tmp/wc-agent-alice-agent0
  alice:helper   running   3m  %42  #dev               /tmp/wc-agent-alice-helper
  alice:writer   offline   —   —    —                   /tmp/wc-agent-alice-writer
```

**Implementation**:
- Uptime: computed from `created_at` timestamp (added in P1 #1)
- Channel membership: requires new `sys.status_request` / `sys.status_response` to query agent's `joined_channels` set from channel-server. Alternatively, track locally in weechat-agent by listening to `sys.join_confirmed` events.
- Recommended approach: track locally — when weechat-agent receives `sys.join_confirmed` on a private buffer, record the channel in the agent's local state. This avoids an extra round-trip and works even if the agent is temporarily unresponsive.

---

### #6 `/zenoh leave` Error on Non-existent Target

**Problem**: `leave_channel()` silently returns if `channel_id not in channels`. Same for `leave_private()`.

**Solution**: Return `CommandResult.error()` when target doesn't exist:

```
[zenoh] Error: not in #nonexistent
[zenoh] Error: no private chat with @unknown
```

**Implementation**: In the registry-based handlers, check membership before sending leave command:

```python
@zenoh_registry.command(name="leave", ...)
def cmd_zenoh_leave(buffer, args):
    target = args.get("target") or current_buffer_target(buffer)
    if target.startswith("#"):
        channel_id = target.lstrip("#")
        if channel_id not in channels:
            return CommandResult.error(f"not in #{channel_id}")
        leave_channel(channel_id)
    elif target.startswith("@"):
        nick = target.lstrip("@")
        pair = make_private_pair(my_nick, nick)
        if pair not in privates:
            return CommandResult.error(f"no private chat with @{nick}")
        leave_private(nick)
    else:
        return CommandResult.error(f"invalid target: {target} (use #channel or @nick)")
    return CommandResult.ok(f"Left {target}")
```

---

### #8 Presence Summary on Join

**Status**: Mostly covered by P1 #5 — the `joined` event from sidecar already includes `members` list and displays online count.

**Remaining work**: Display the member list when count is small (≤ 10):

```
[zenoh] Joined #dev (3 members online: alice, bob, alice:agent0)
```

When count > 10, keep the summary form:

```
[zenoh] Joined #general (24 members online)
```

**Implementation**: Conditional formatting in the `joined` event handler based on `len(members)`.

---

### #9 `/agent status <name>`

**Problem**: No way to get detailed info about a single agent.

**Solution**: New command that queries the agent via sys message and shows combined local + remote state:

```
[agent] alice:helper
  status:    running
  uptime:    12m 34s
  pane:      %42
  workspace: /tmp/wc-agent-alice-helper
  channels:  #dev, #general
  messages:  sent 23, received 47
```

**Implementation**:
1. New sys message pair: `sys.status_request` → `sys.status_response`
2. `sys.status_response` body:

```json
{
  "channels": ["dev", "general"],
  "messages_sent": 23,
  "messages_received": 47
}
```

3. Channel-server tracks message counters (simple integer increments in `reply()` and subscriber callback)
4. WeeChat-agent merges local state (status, uptime, pane, workspace) with remote response

**Timeout**: If agent doesn't respond within 3s, display local-only info with note:

```
[agent] alice:helper (agent not responding — showing local info only)
  status:    running
  uptime:    12m 34s
  pane:      %42
  workspace: /tmp/wc-agent-alice-helper
```

**New sys message types** to add to the protocol table:

| type | direction | body | purpose |
|------|-----------|------|---------|
| `sys.status_request` | user → agent | `{}` | Request agent status |
| `sys.status_response` | agent → user | `{"channels": [...], "messages_sent": N, "messages_received": N}` | Agent status reply |

---

### #10 `/zenoh who <#channel>`

**Problem**: No way to see channel members with online/offline status from the command line (only the nicklist sidebar).

**Solution**: New zenoh command:

```
[zenoh] #general members:
  ● alice          (online)
  ● alice:agent0   (online)
  ● bob            (online)
  ○ carol          (offline)
```

**Implementation**:
- New sidecar command: `{"cmd": "who", "channel_id": "general"}`
- Sidecar queries liveliness tokens for `wc/channels/{channel_id}/presence/*` and returns:

```json
{"event": "who_response", "channel_id": "general", "members": [
  {"nick": "alice", "online": true},
  {"nick": "alice:agent0", "online": true},
  {"nick": "bob", "online": true},
  {"nick": "carol", "online": false}
]}
```

- `●` / `○` indicators for online/offline (works in all terminal emulators with UTF-8)
- If not in the channel: `CommandResult.error("not in #general")`

---

### #11 `/agent restart <name>`

**Problem**: Restarting an agent requires manual `/agent stop` + `/agent create`.

**Solution**: Convenience command that chains stop → wait for offline → create with same config:

```python
@agent_registry.command(
    name="restart",
    args="<name>",
    description="Restart an agent (stop then re-create with same config)",
)
def cmd_agent_restart(buffer, args):
    name = scoped(args.get("name"))
    agent = agents.get(name)
    if not agent:
        return CommandResult.error(f"Unknown agent: {name}")
    if name == PRIMARY_AGENT:
        return CommandResult.error(f"{name} is the primary agent and cannot be restarted")

    # Save config before stop
    workspace = agent["workspace"]

    # Trigger stop, schedule re-create on offline callback
    agent["pending_restart"] = True
    cmd_agent_stop(buffer, args)
    return CommandResult.ok(f"Restarting {name}...")
```

**Flow**:
1. `/agent restart helper`
2. Sets `pending_restart = True` on agent entry
3. Triggers `/agent stop` flow (sys.stop_request → tmux /exit)
4. In `on_presence_signal_cb`, when agent goes offline and `pending_restart` is True:
   - Clears the flag
   - Calls `create_agent(name, workspace)` with saved config
5. User sees:

```
[agent] alice:helper is shutting down...
[agent] alice:helper is now offline
[agent] Restarting alice:helper...
[agent] Created alice:helper
  workspace: /tmp/wc-agent-alice-helper
  pane: %43
[agent] alice:helper is now ready (took 4.8s)
```

---

### #12 Message Delivery Confirmation

**Problem**: No feedback that a message was actually received by anyone.

**Solution**: Lightweight read-receipt via sys protocol. Opt-in, not default (to avoid noise).

**Design**: When an agent receives a message addressed to it (mention or private), the channel-server automatically sends a `sys.ack` with the message ID as `ref_id`:

```json
{"type": "sys.ack", "body": {"status": "ok"}, "ref_id": "original_msg_id"}
```

WeeChat plugin tracks pending message IDs. On receiving ack, updates the message display with a subtle indicator (e.g., `✓` suffix on the timestamp or nick column). If no ack within 30s, no indicator shown (absence of confirmation, not an error).

**Scope limitation**: Only agent-to-user confirmations. Human-to-human delivery confirmation is not in scope (would require protocol changes on all clients).

**Implementation**:
- Channel-server: in subscriber callback, after processing a message, publish `sys.ack` on the sender's private topic
- WeeChat: track last N message IDs in a dict `{msg_id: (buffer, line_ptr)}`. On `sys.ack`, update display if line still visible.
- No config for now — always enabled for agent messages

---

### #14 Friendly Error for Missing `channel_plugin_dir`

**Problem**: Current error says `Use /set plugins.var.python.weechat-agent.channel_plugin_dir` but doesn't suggest the likely path.

**Solution**: Auto-detect common locations and suggest:

```python
def _suggest_channel_plugin_dir():
    """Try to find weechat-channel-server relative to this plugin."""
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "weechat-channel-server"),
        os.path.expanduser("~/Workspace/weechat-claude/weechat-channel-server"),
    ]
    for path in candidates:
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "server.py")):
            return os.path.realpath(path)
    return None
```

Output when not configured:

```
[agent] Error: channel_plugin_dir not set.
  Detected: /Users/alice/Workspace/weechat-claude/weechat-channel-server
  Run: /set plugins.var.python.weechat-agent.channel_plugin_dir /Users/alice/Workspace/weechat-claude/weechat-channel-server
```

If auto-detect fails:

```
[agent] Error: channel_plugin_dir not set.
  Run: /set plugins.var.python.weechat-agent.channel_plugin_dir /path/to/weechat-channel-server
```

---

### P2-export: Registry Export (Future)

**Status**: Not implemented. Code should include a `# TODO: export.py — OpenAPI / JSON Schema / plain text export` comment in `wc_registry/__init__.py` to mark the extension point.

**Future scope**: `to_json_schema()`, `to_openapi()`, `to_text()` methods on `CommandRegistry`, iterating registered `CommandSpec` entries. No file created for now.

---

## Command Summary After P0+P1+P2

### `/agent` commands

| command | args | description | phase |
|---------|------|-------------|-------|
| `create` | `<name> [--workspace <path>]` | Launch a new agent | P0 (registry migration) |
| `stop` | `<name>` | Stop a running agent (not agent0) | P1 |
| `list` | — | List agents with status, uptime, channels, pane, workspace | P0 (registry) + P2 (enhanced) |
| `join` | `<agent> <#channel>` | Ask agent to join channel (with confirmation) | P1 |
| `status` | `<name>` | Show detailed single-agent info | P2 |
| `restart` | `<name>` | Stop then re-create agent with same config | P2 |
| `help` | — | Show all agent commands (auto-generated) | P0 |

### `/zenoh` commands

| command | args | description | phase |
|---------|------|-------------|-------|
| `join` | `<#channel\|@nick>` | Join channel or private (with completion confirmation) | P1 |
| `leave` | `[target]` | Leave channel or private (with error on invalid target) | P0 (registry) + P2 (error) |
| `nick` | `<newname>` | Change nickname | P0 (registry migration) |
| `list` | — | List joined channels and privates | P0 (registry migration) |
| `status` | — | Show connection status | P0 (registry migration) |
| `reconnect` | — | Reconnect sidecar | P0 (registry migration) |
| `send` | `<target> <msg>` | Send message programmatically | P0 (registry migration) |
| `who` | `<#channel>` | List channel members with online/offline status | P2 |
| `help` | — | Show all zenoh commands (auto-generated) | P0 |

---

## Files to Create/Modify

### New files
- `wc_registry/__init__.py` — CommandRegistry + @command decorator (with `# TODO: export.py` comment)
- `wc_registry/types.py` — CommandParam, CommandSpec, CommandResult, ParsedArgs
- `wc_protocol/sys_messages.py` — System message helpers

### Modified files
- `weechat-agent/weechat-agent.py`:
  - P0: Refactor to use registry
  - P1: Add stop command, sys message handling, readiness notification, join confirmation
  - P2: Enhanced list (uptime + channels), status command, restart command, friendly config error
- `weechat-zenoh/weechat-zenoh.py`:
  - P0: Refactor to use registry
  - P1: Handle joined ack, send failure feedback, sys message routing
  - P2: Leave error on invalid target, who command, presence summary formatting
- `weechat-zenoh/zenoh_sidecar.py`:
  - P1: Add joined event, send_failed event, msg_id tracking
  - P2: Add who command handler (liveliness query)
- `weechat-channel-server/server.py`:
  - P1: Handle sys.stop_request, sys.join_request
  - P2: Handle sys.status_request, track message counters, send sys.ack for delivery confirmation
- `wc_protocol/messages.py` — Add ref_id field support (if not already there)

### Test files
- `tests/unit/test_registry.py` — Registry, decorator, dispatch, validation, help generation
- `tests/unit/test_sys_messages.py` — System message creation, parsing, is_sys_message
- `tests/unit/test_agent_commands.py` — Agent stop/join/restart/status edge cases (mocked Zenoh)
- `tests/unit/test_zenoh_commands.py` — Leave error, who command (mocked sidecar)
- `tests/integration/test_sys_roundtrip.py` — sys message round-trips over real Zenoh
