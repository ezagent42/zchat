# IRC Migration Design — Zenoh → IRC + Independent CLI

**Date**: 2026-03-25
**Scope**: Replace Zenoh P2P messaging with standard IRC, extract agent management into independent CLI, eliminate all WeeChat custom plugins.

## Overview

Fundamental architecture simplification: replace the custom Zenoh-based messaging layer with standard IRC protocol, and extract agent lifecycle management from WeeChat plugins into an independent CLI tool `wc-agent`.

**Result**: Zero custom WeeChat code. Any IRC client works. Agent management is a standalone CLI.

## Motivation

- WeeChat's built-in Python interpreter limits library usage (no asyncio, PyO3 subinterpreter issues)
- Custom plugins (weechat-zenoh.py, weechat-agent.py, zenoh_sidecar.py) total 1500+ lines maintaining a custom messaging layer that duplicates what IRC already provides
- Tight coupling to WeeChat prevents using other IRC clients
- Agent management embedded in WeeChat plugin makes it impossible to manage agents without WeeChat running

## Architecture After Migration

```
┌────────────────────────────────────────────────────────┐
│ Any IRC Client (WeeChat, irssi, hexchat, etc.)         │
│  alice, bob, ...                                       │
└────────────┬───────────────────────────────────────────┘
             │ IRC
             ▼
┌────────────────────────────┐
│ IRC Server                 │  ← Any: Libera.Chat, ergo local, corporate
│ (public or local)          │
└──┬─────────┬─────────┬─────┘
   │ IRC     │ IRC     │ IRC
   ▼         ▼         ▼
┌──────┐  ┌──────┐  ┌──────────────┐
│agent0│  │agent1│  │ wc-agent CLI │
│(chan- │  │(chan- │  │ (lifecycle   │
│server)│  │server)│  │  management) │
└──┬───┘  └──┬───┘  └──────────────┘
   │MCP      │MCP
   ▼         ▼
 claude    claude
```

### Component Responsibilities

| Component | Responsibility | Dependencies |
|-----------|---------------|-------------|
| IRC Server | Message routing, presence (JOIN/PART/QUIT), channel management | System install (ergo) or public server |
| `wc-agent` CLI | Agent lifecycle: create, stop, list, restart, status | Python 3.11+ (uses `tomllib` from stdlib) |
| `weechat-channel-server` | MCP server for Claude, IRC client for message send/receive | `irc`, `mcp[cli]` |
| `commands.json` | OpenAPI 3.1 schema defining all wc-agent commands | — |
| `weechat-claude.toml` | Shared config: IRC server address, default channels, username | — |

### Deleted Components

| Component | Lines | Reason |
|-----------|-------|--------|
| `weechat-zenoh/weechat-zenoh.py` | 600+ | WeeChat native IRC replaces custom chat plugin |
| `weechat-zenoh/zenoh_sidecar.py` | 300+ | Zenoh no longer used |
| `weechat-agent/weechat-agent.py` | 600+ | Agent management moves to `wc-agent` CLI |
| `wc_registry/` | 200+ | No WeeChat commands to register |
| `wc_protocol/signals.py` | 10 | No WeeChat signal communication |
| `wc_protocol/topics.py` | 68 | Zenoh topics no longer used |
| `wc_protocol/config.py` | 26 | Zenoh config no longer used |
| `eclipse-zenoh` dependency | — | Completely removed |

### Retained/Modified Components

| Component | Change |
|-----------|--------|
| `wc_protocol/naming.py` | **Change separator from `:` to `-`** — IRC RFC 2812 forbids `:` in nicks. `alice-agent0` → `alice-agent0`. `AGENT_SEPARATOR = "-"` |
| `wc_protocol/sys_messages.py` | Transport changes from Zenoh to IRC PRIVMSG. Sys messages prefixed with `__wc_sys:` to avoid collision with user text. JSON format unchanged. |
| `weechat-channel-server/server.py` | Zenoh client → IRC client |
| `weechat-channel-server/message.py` | Remove message dedup (IRC does not have message IDs; dedup was Zenoh-specific). Mention detection and chunking unchanged. |

---

## Configuration

### weechat-claude.toml

```toml
[irc]
server = "192.168.1.100"     # IRC server address
port = 6667                   # IRC server port
tls = false                   # TLS for IRC connection
password = ""                 # Server password (optional)

[agents]
default_channels = ["#general"]
username = ""                 # Empty = use $USER
```

### Configuration Flow

1. `wc-agent` reads `weechat-claude.toml` for IRC server address
2. When creating an agent, `wc-agent` generates `.mcp.json` with IRC connection info from config:

```json
{
  "mcpServers": {
    "weechat-channel": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--project", "<channel-server-dir>", "python3", "<channel-server-dir>/server.py"],
      "env": {
        "AGENT_NAME": "alice-agent0",
        "IRC_SERVER": "192.168.1.100",
        "IRC_PORT": "6667",
        "IRC_CHANNELS": "#general",
        "IRC_TLS": "false"
      }
    }
  }
}
```

3. channel-server reads IRC connection from environment variables
4. Users configure their IRC client independently (WeeChat `/server add`, irssi config, etc.)

---

## commands.json (OpenAPI 3.1)

Defines all `wc-agent` commands. Consumed by:
- `wc-agent` CLI: command dispatch, arg parsing, help generation
- Future: API documentation, client codegen

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "WeeChat-Claude Agent Commands",
    "version": "1.0.0",
    "description": "Agent lifecycle management for WeeChat-Claude"
  },
  "paths": {
    "/agent/start": {
      "post": {
        "summary": "Start IRC server (if local) and primary agent",
        "operationId": "agent.start",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "config": {"type": "string", "description": "Path to weechat-claude.toml"}
                }
              }
            }
          }
        }
      }
    },
    "/agent/create": {
      "post": {
        "summary": "Create and launch a new agent",
        "operationId": "agent.create",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["name"],
                "properties": {
                  "name": {"type": "string", "description": "Agent name (without username prefix)"},
                  "workspace": {"type": "string", "description": "Custom workspace path"},
                  "channels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Channels to auto-join (default from config)"
                  }
                }
              }
            }
          }
        }
      }
    },
    "/agent/stop": {
      "post": {
        "summary": "Stop a running agent",
        "operationId": "agent.stop",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["name"],
                "properties": {
                  "name": {"type": "string"}
                }
              }
            }
          }
        }
      }
    },
    "/agent/list": {
      "get": {
        "summary": "List all agents with status",
        "operationId": "agent.list"
      }
    },
    "/agent/status": {
      "post": {
        "summary": "Show detailed info for a single agent",
        "operationId": "agent.status",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["name"],
                "properties": {
                  "name": {"type": "string"}
                }
              }
            }
          }
        }
      }
    },
    "/agent/restart": {
      "post": {
        "summary": "Restart an agent (stop + create with same config)",
        "operationId": "agent.restart",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["name"],
                "properties": {
                  "name": {"type": "string"}
                }
              }
            }
          }
        }
      }
    },
    "/agent/shutdown": {
      "post": {
        "summary": "Stop all agents and local IRC server",
        "operationId": "agent.shutdown"
      }
    }
  }
}
```

---

## wc-agent CLI

### Interface

```bash
wc-agent start [--config weechat-claude.toml]   # Start local ergo + primary agent (agent0)
wc-agent create <name> [--workspace <path>]      # Create new agent
wc-agent stop <name>                             # Graceful stop
wc-agent restart <name>                          # Stop + re-create
wc-agent list                                    # List agents with status
wc-agent status <name>                           # Detailed agent info
wc-agent shutdown                                # Stop all agents + local ergo
```

### Internal Design

```
wc-agent/
  __init__.py
  cli.py              # CLI entry point (argparse or click)
  config.py           # Read weechat-claude.toml
  agent_manager.py    # Agent lifecycle (create workspace, spawn tmux, track state)
  irc_monitor.py      # Optional: connect to IRC to monitor agent presence
  sys_protocol.py     # Send/receive sys messages via IRC PRIVMSG
```

### Agent State Tracking

`wc-agent` tracks agents via a state file `~/.local/state/wc-agent/agents.json`:

```json
{
  "alice-agent0": {
    "workspace": "/tmp/wc-agent-alice-agent0",
    "pane_id": "%41",
    "pid": 12345,
    "status": "running",
    "created_at": 1711276800,
    "channels": ["#general"]
  }
}
```

Status is derived from:
- `running`: tmux pane exists + pid alive
- `offline`: tmux pane gone or pid dead
- `starting`: just created, waiting for IRC JOIN

### Agent Lifecycle: create

1. Read `weechat-claude.toml` for IRC server info
2. Scope name: `helper` → `alice-helper`
3. Create workspace: `/tmp/wc-agent-alice-helper/`
4. Generate `.mcp.json` with IRC env vars
5. Spawn tmux pane: `tmux split-window -v ... claude --dangerously-load-development-channels server:weechat-channel`
6. Auto-confirm development channels prompt (3s timer)
7. Save to `agents.json`
8. Print: `Created alice-helper (pane: %42, workspace: /tmp/...)`

### Agent Lifecycle: stop

1. Look up agent in `agents.json`
2. If agent is running, send sys.stop_request via IRC PRIVMSG:
   - Uses persistent IRC monitor connection (started with `wc-agent start`)
   - If monitor not running, falls back to direct tmux force-stop
3. Wait up to 5s for sys.stop_confirmed
4. If no response, force: `tmux send-keys -t <pane> /exit Enter`
5. Wait for pane to close
6. Cleanup workspace
7. Update `agents.json`

### Agent Lifecycle: restart

1. Save agent config (workspace, channels)
2. Execute stop flow
3. Wait for offline
4. Execute create flow with saved config

---

## weechat-channel-server Modifications

### Replace Zenoh with IRC

Current `setup_zenoh()` is replaced with IRC client setup:

```python
# Current (Zenoh):
zenoh_session = zenoh.open(config)
zenoh_session.declare_subscriber("wc/channels/*/messages", on_channel)
zenoh_session.declare_subscriber("wc/private/*/messages", on_private)

# New (IRC):
irc_client = irc.client.Reactor()
conn = irc_client.server().connect(
    os.environ["IRC_SERVER"],
    int(os.environ.get("IRC_PORT", "6667")),
    AGENT_NAME
)
for channel in os.environ.get("IRC_CHANNELS", "").split(","):
    conn.join(f"#{channel.strip().lstrip('#')}")
# on_pubmsg → replaces on_channel
# on_privmsg → replaces on_private
```

### Message Handling (on_pubmsg — replaces on_channel)

```python
def on_pubmsg(connection, event):
    """Handle channel messages — filter for @mentions."""
    nick = event.source.nick
    if nick == AGENT_NAME:
        return  # Skip own messages
    body = event.arguments[0]
    if not detect_mention(body, AGENT_NAME):
        return
    body = clean_mention(body, AGENT_NAME)
    channel = event.target
    msg = {"nick": nick, "body": body, "type": "msg", "id": random_hex(8), "ts": time.time()}
    # Inject MCP notification (same as current)
    inject_message(write_stream, msg, channel)
```

### Private Message Handling (on_privmsg — replaces on_private)

```python
def on_privmsg(connection, event):
    """Handle private messages and sys messages."""
    nick = event.source.nick
    body = event.arguments[0]
    # Sys messages use __wc_sys: prefix to avoid collision with user text
    SYS_PREFIX = "__wc_sys:"
    if body.startswith(SYS_PREFIX):
        msg = json.loads(body[len(SYS_PREFIX):])
    else:
        msg = {"nick": nick, "body": body, "type": "msg"}

    if is_sys_message(msg):
        _handle_sys_message(msg, nick, connection)
        return

    # Regular private message → MCP notification
    inject_message(write_stream, msg, nick)
```

### Reply Tool (replaces Zenoh publish)

```python
async def _handle_reply(connection, arguments):
    chat_id = arguments["chat_id"]
    text = arguments["text"]
    for chunk in chunk_message(text):
        if chat_id.startswith("#"):
            connection.privmsg(chat_id, chunk)
        else:
            connection.privmsg(chat_id, chunk)
    return [TextContent(type="text", text=f"Sent to {chat_id}")]
```

### Sys Protocol (transport change only)

JSON format unchanged. Transport: Zenoh private topic → IRC PRIVMSG.

```python
def _handle_sys_message(msg, sender_nick, connection):
    msg_type = msg.get("type", "")
    if msg_type == "sys.stop_request":
        reply = make_sys_message(AGENT_NAME, "sys.stop_confirmed", {}, ref_id=msg["id"])
        connection.privmsg(sender_nick, f"__wc_sys:{json.dumps(reply)}")
    elif msg_type == "sys.join_request":
        channel = msg.get("body", {}).get("channel", "").lstrip("#")
        if channel:
            connection.join(f"#{channel}")
            reply = make_sys_message(AGENT_NAME, "sys.join_confirmed", {"channel": f"#{channel}"}, ref_id=msg["id"])
            connection.privmsg(sender_nick, f"__wc_sys:{json.dumps(reply)}")
    elif msg_type == "sys.status_request":
        reply = make_sys_message(AGENT_NAME, "sys.status_response", {
            "channels": list(joined_channels),
            "messages_sent": _msg_counter["sent"],
            "messages_received": _msg_counter["received"],
        }, ref_id=msg["id"])
        connection.privmsg(sender_nick, f"__wc_sys:{json.dumps(reply)}")
```

### Presence (replaces Zenoh liveliness)

IRC native. Agent joins channel → all clients see JOIN. Agent disconnects → QUIT.
No custom presence protocol needed.

---

## Data Flow Examples

### User chats in #general

```
alice types "hello everyone" in WeeChat #general
  → WeeChat IRC plugin: PRIVMSG #general :hello everyone
  → IRC server broadcasts to all #general members
  → bob's WeeChat displays message
  → agent0's channel-server on_pubmsg fires
  → No @mention → ignored
```

### User @mentions agent

```
alice: "@alice-agent0 what is the capital of France?"
  → IRC PRIVMSG #general :@alice-agent0 what is the capital of France?
  → agent0 channel-server on_pubmsg
  → detect_mention() → match
  → clean_mention() → "what is the capital of France?"
  → MCP notification → Claude
  → Claude calls reply tool
  → connection.privmsg("#general", "Paris is the capital of France.")
  → alice and bob see reply in #general
```

### wc-agent creates agent

```
$ wc-agent create helper

1. Read weechat-claude.toml → IRC server = 192.168.1.100:6667
2. Scope: helper → alice-helper
3. Create /tmp/wc-agent-alice-helper/
4. Generate .mcp.json with IRC_SERVER=192.168.1.100
5. tmux split-window → claude starts
6. channel-server connects to IRC as alice-helper
7. channel-server JOINs #general
8. All IRC clients see: "alice-helper has joined #general"
9. wc-agent prints: "Created alice-helper (pane: %42)"
```

### wc-agent stops agent

```
$ wc-agent stop helper

1. Look up alice-helper in agents.json
2. Connect to IRC temporarily (or reuse monitor connection)
3. PRIVMSG alice-helper :__wc_sys:{"type":"sys.stop_request",...}
4. channel-server receives → replies sys.stop_confirmed
5. wc-agent receives confirmation
6. tmux send-keys -t %42 /exit Enter
7. claude exits → channel-server disconnects → IRC QUIT
8. All clients see: "alice-helper has quit"
9. wc-agent cleans up workspace, updates agents.json
10. Prints: "Stopped alice-helper"
```

### Private message to agent

```
alice in WeeChat: /msg alice-agent0 help me review this code
  → IRC PRIVMSG alice-agent0 :help me review this code
  → channel-server on_privmsg
  → Not sys message → MCP notification → Claude
  → Claude calls reply tool
  → connection.privmsg("alice", "Sure, let me look at the code...")
  → alice sees private reply in WeeChat
```

---

## Deployment Modes

### Mode 1: Public IRC Server

```bash
# weechat-claude.toml
[irc]
server = "irc.libera.chat"
port = 6697
tls = true
```

- Zero infrastructure to manage
- Multi-user collaboration out of the box
- Use NickServ for agent nick protection

### Mode 2: Local IRC Server

```bash
# weechat-claude.toml
[irc]
server = "192.168.1.100"
port = 6667
```

- `wc-agent start` auto-launches ergo if not running
- Offline capable
- Full control over server config

### Mode 3: Corporate IRC

```bash
# weechat-claude.toml
[irc]
server = "irc.corp.internal"
port = 6667
password = "team-token"
```

- Uses existing infrastructure
- Team-wide agent visibility

---

## E2E Test Changes

### helpers.sh

```bash
install_weechat_plugins() {
    # No plugins to install — WeeChat uses native IRC
    :
}

start_infrastructure() {
    # Start local ergo for testing
    ergo --config "$E2E_DIR/ergo-test.toml" &
    ERGOD_PID=$!
    sleep 1

    # Create primary agent
    wc-agent start --config "$E2E_DIR/test-config.toml"
    sleep 5
}

cleanup() {
    wc-agent shutdown
    kill $ERGOD_PID 2>/dev/null
    # ... existing tmux cleanup
}
```

### e2e-test.sh changes

- Phase 0: Start ergo + `wc-agent start` (replaces plugin installation)
- Phase 1: WeeChat connects to local IRC (`/server add test localhost; /connect test; /join #general`)
- Phase 2-4: Unchanged (user types in IRC channel, agent responds)
- Phase 5: `wc-agent create agent1` in separate terminal (replaces `/agent create`)
- Phase 6: `wc-agent stop agent1` (replaces tmux /exit)

### test-config.toml

```toml
[irc]
server = "127.0.0.1"
port = 6667

[agents]
default_channels = ["#general"]
username = "alice"
```

---

## Migration Checklist

### New files to create
- `wc-agent/cli.py` — CLI entry point
- `wc-agent/config.py` — TOML config reader
- `wc-agent/agent_manager.py` — Agent lifecycle
- `wc-agent/irc_monitor.py` — IRC connection for sys messages
- `wc-agent/sys_protocol.py` — sys message send/receive over IRC
- `commands.json` — OpenAPI 3.1 command schema
- `weechat-claude.toml` — Shared config (with example)
- `ergo.toml` — Default local IRC server config

### Files to modify
- `weechat-channel-server/server.py` — Zenoh → IRC client
- `wc_protocol/sys_messages.py` — No format change, document IRC transport
- `start.sh` — Launch ergo + wc-agent instead of tmux + plugins
- `stop.sh` — `wc-agent shutdown`
- `tests/e2e/e2e-test.sh` — Adapt to IRC + CLI
- `tests/e2e/helpers.sh` — Simplify plugin install, add ergo startup

### Files to delete
- `weechat-zenoh/weechat-zenoh.py`
- `weechat-zenoh/zenoh_sidecar.py`
- `weechat-agent/weechat-agent.py`
- `wc_registry/__init__.py`
- `wc_registry/types.py`
- `wc_protocol/signals.py`
- `wc_protocol/topics.py`
- `wc_protocol/config.py`
- All Zenoh-related unit tests

### Dependencies to remove
- `eclipse-zenoh`

### Dependencies to add
- `irc` (Python IRC client library, for channel-server + wc-agent)
- `tomllib` (stdlib in Python 3.11+, no external dependency)
- `ergo` (system install, local IRC server — `brew install ergochat/tap/ergo` or equivalent)

---

## Failure Modes

### IRC Server Unreachable

**channel-server**: Retry with exponential backoff (1s, 2s, 4s, ..., max 60s). During disconnection, Claude receives no messages. On reconnect, rejoin all channels. MCP notification to Claude: `"IRC connection lost, reconnecting..."` so it knows not to attempt replies.

**wc-agent**: Commands that require IRC (stop with graceful sys protocol) fall back to direct tmux force-stop. Print warning: `"IRC unreachable, using force stop."`

### Nick Collision (ERR_NICKNAMEINUSE 433)

**channel-server**: If `alice-agent0` is taken, append suffix: `alice-agent0_`, `alice-agent0__`, etc. (max 3 retries). Log the actual nick used. If all retries fail, exit with clear error.

**wc-agent**: When creating agent, check IRC nick availability first (via monitor connection). If taken, fail fast: `"Nick alice-helper is already in use on IRC server."`

### PRIVMSG Length Limit

IRC PRIVMSG has ~512 byte line limit (~400 usable after protocol overhead). Constraints:
- **Sys messages**: All sys payloads MUST fit in a single PRIVMSG. Validated at construction time in `make_sys_message()`. The `sys.status_response` channels list is truncated if it would exceed the limit.
- **Chat messages**: Already handled by `chunk_message()` in `message.py` (4000 char chunks, well within IRC limits per line).

### Agent Process Crash

If a claude process crashes (tmux pane exits unexpectedly):
- `wc-agent list` detects via pid/pane check → marks as `offline`
- channel-server IRC connection drops → other users see QUIT
- No automatic restart (user must explicitly `wc-agent restart`)

---

## wc-agent IRC Connection Strategy

`wc-agent` maintains a **persistent IRC connection** via `irc_monitor.py` (started with `wc-agent start`, stopped with `wc-agent shutdown`). This connection:
- Nick: `__wc-agent` (or configurable)
- Joins no channels (sys-only, PRIVMSG communication)
- Used for: sending sys.stop_request, sys.join_request, receiving confirmations
- Monitors agent nicks via WHO/WHOIS for status checks

This avoids the race condition of connecting on demand — the monitor is always ready.

---

## Migration Checklist Additions

### Tests to create
- `tests/unit/test_wc_agent_cli.py` — CLI arg parsing, config loading
- `tests/unit/test_agent_manager.py` — Agent lifecycle (mocked tmux/IRC)
- `tests/unit/test_channel_server_irc.py` — IRC message handling, mention detection, sys protocol
- `tests/integration/test_irc_roundtrip.py` — Message send/receive via real IRC server

### Documentation to update
- `CLAUDE.md` — New architecture, terminology (`-` separator), commands
- `docs/dev/` — Updated component docs

### Dependency files
- `wc-agent/pyproject.toml` — New package
- `weechat-channel-server/pyproject.toml` — Replace `eclipse-zenoh` with `irc`
- `wc_protocol/__init__.py` — Update after deleting signals.py, topics.py, config.py

---

## Future Extension: Zenoh S2S Transport

Not in scope for this migration. Documented for future reference.

When multi-site federation is needed, a Zenoh transport adapter can bridge IRC S2S protocol over Zenoh P2P:

```
ergo (site A) ←→ zenoh-irc-transport ←── Zenoh ──→ zenoh-irc-transport ←→ ergo (site B)
```

This preserves IRC's native nick/channel/presence synchronization while gaining Zenoh's NAT traversal and P2P discovery. The adapter is a thin TCP-to-Zenoh bridge, not a message-level translator.
