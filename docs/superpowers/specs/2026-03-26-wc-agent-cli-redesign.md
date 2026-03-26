# wc-agent CLI Redesign — Two-Level Subcommands + Manual Test Guide

**Date**: 2026-03-26
**Scope**: Restructure wc-agent CLI from flat commands to `irc`/`agent` subgroups using Typer, add missing commands, create manual test guide.

## Overview

Redesign the wc-agent CLI to support a clean manual testing workflow. Replace the flat argparse structure with Typer-based two-level subcommands: `wc-agent irc <cmd>` for IRC infrastructure and `wc-agent agent <cmd>` for agent lifecycle.

## Command Structure

```
wc-agent irc daemon start              # Start ergo IRC server
wc-agent irc daemon stop               # Stop ergo
wc-agent irc start                     # Start WeeChat in tmux + auto-connect IRC
wc-agent irc stop                      # Stop WeeChat (/quit)
wc-agent irc status                    # Show IRC server + client status

wc-agent agent create <name>           # Create agent (claude + channel-server)
  [--workspace <path>]
wc-agent agent stop <name>             # Stop agent
wc-agent agent list                    # List all agents
wc-agent agent status <name>           # Single agent details
wc-agent agent send <name> <text>      # Send text to agent's tmux pane
wc-agent agent restart <name>          # Restart agent

wc-agent shutdown                      # Stop all agents + WeeChat + ergo
```

## Migration from Current CLI

| Current | New | Change |
|---------|-----|--------|
| `wc-agent start` | `wc-agent irc daemon start` + `wc-agent irc start` + `wc-agent agent create agent0` | Split into 3 independent commands |
| `wc-agent create <n>` | `wc-agent agent create <n>` | Move to `agent` group |
| `wc-agent stop <n>` | `wc-agent agent stop <n>` | Move to `agent` group |
| `wc-agent list` | `wc-agent agent list` | Move to `agent` group |
| `wc-agent status <n>` | `wc-agent agent status <n>` | Move to `agent` group |
| `wc-agent restart <n>` | `wc-agent agent restart <n>` | Move to `agent` group |
| `wc-agent shutdown` | `wc-agent shutdown` | Unchanged |
| — | `wc-agent irc daemon start/stop` | **New** |
| — | `wc-agent irc start/stop` | **New** |
| — | `wc-agent irc status` | **New** |
| — | `wc-agent agent send <name> <text>` | **New** |

## Cross-File Impact

### `server.py` `_handle_create_agent` MCP tool

**Current**: Calls `wc-agent/cli.py` as subprocess: `[sys.executable, cli_path, "create", name]`
**Change**: Replace with direct import of `AgentManager`. No CLI subprocess — use the Python library directly since channel-server can import it.

```python
async def _handle_create_agent(arguments: dict) -> list[TextContent]:
    from wc_agent.agent_manager import AgentManager
    # Build manager from env vars (IRC_SERVER, etc. are already available)
    # Call manager.create(scoped_name) directly
```

This eliminates: CLI path resolution, subprocess overhead, Typer dependency in channel-server.

### `start.sh`

**Current**: `python3 wc-agent/cli.py start --workspace $WORKSPACE` (single command does everything)
**Change**: Three separate commands:
```bash
wc-agent irc daemon start
wc-agent irc start
wc-agent agent create agent0 --workspace "$WORKSPACE"
```

### `stop.sh`

**Current**: `python3 wc-agent/cli.py shutdown`
**Change**: `wc-agent shutdown` — unchanged behavior, shutdown is kept as convenience command.

### E2E tests (`e2e-test.sh`, `e2e-test-manual.sh`, `helpers.sh`)

All `wc-agent` invocations need `irc`/`agent` subgroup prefix:
- `create agent1` → `agent create agent1`
- `stop agent1` → `agent stop agent1`
- `list` → `agent list`
- `start` → `irc daemon start` + `irc start` + `agent create agent0`

### Unit tests

- `test_channel_server_irc.py`: Remove `test_create_agent_tool_cli_path` (no longer uses CLI path)
- `test_agent_manager.py`: Tests remain valid — AgentManager API unchanged

## Implementation: Typer

```python
import typer

app = typer.Typer(name="wc-agent", help="Claude Code agent lifecycle management")
irc_app = typer.Typer(name="irc", help="IRC server and client management")
irc_daemon_app = typer.Typer(name="daemon", help="Local ergo IRC server")
agent_app = typer.Typer(name="agent", help="Claude Code agent lifecycle")

app.add_typer(irc_app, name="irc")
irc_app.add_typer(irc_daemon_app, name="daemon")
app.add_typer(agent_app, name="agent")
```

### irc daemon commands

```python
@irc_daemon_app.command("start")
def irc_daemon_start():
    """Start local ergo IRC server."""
    # Read config → check if local
    # mkdir -p $ERGO_DATA_DIR
    # cd $ERGO_DATA_DIR && ergo run --conf <ergo.yaml> &
    # Save PID to state file

@irc_daemon_app.command("stop")
def irc_daemon_stop():
    """Stop local ergo IRC server."""
    # pkill -x ergo
```

### irc client commands

```python
@irc_app.command("start")
def irc_start():
    """Start WeeChat in tmux, auto-connect to IRC."""
    # Create/reuse tmux session
    # tmux send-keys: weechat -r '/server add wc-local <server>/<port> -notls -nicks=<nick>; /connect; /join #general'
    # Save weechat pane_id to state

@irc_app.command("stop")
def irc_stop():
    """Stop WeeChat."""
    # tmux send-keys -t <pane> /quit Enter

@irc_app.command("status")
def irc_status():
    """Show IRC server and client status."""
    # Check ergo process → running/stopped
    # Check weechat pane → running/stopped
    # Print summary
```

### agent commands

```python
@agent_app.command("create")
def agent_create(name: str, workspace: str = None):
    """Create and launch a new agent."""
    # AgentManager.create(name, workspace)

@agent_app.command("stop")
def agent_stop(name: str):
    """Stop a running agent."""
    # AgentManager.stop(name)

@agent_app.command("list")
def agent_list():
    """List all agents with status."""
    # AgentManager.list_agents()

@agent_app.command("status")
def agent_status(name: str):
    """Show detailed info for a single agent."""
    # AgentManager.get_status(name)

@agent_app.command("send")
def agent_send(name: str, text: str):
    """Send text to agent's tmux pane (tmux send-keys)."""
    # Look up pane_id from state
    # subprocess: tmux send-keys -t <pane> <text> Enter

@agent_app.command("restart")
def agent_restart(name: str):
    """Restart an agent (stop + create with same config)."""
    # AgentManager.restart(name)
```

### Top-level commands

```python
@app.command()
def shutdown():
    """Stop all agents + WeeChat + ergo."""
    # agent_manager.shutdown() for all agents
    # irc_stop()
    # irc_daemon_stop()
```

### Global options

```python
# Typer callback for global options
@app.callback()
def main(
    config: str = typer.Option(None, help="Path to weechat-claude.toml"),
    tmux_session: str = typer.Option("weechat-claude", help="tmux session name"),
):
    """Claude Code agent lifecycle management."""
    # Store in context or global state
```

## State File

`~/.local/state/wc-agent/state.json`:

```json
{
  "irc": {
    "daemon_pid": 12345,
    "weechat_pane_id": "%5"
  },
  "agents": {
    "alice-agent0": {
      "workspace": "/tmp/wc-agent-alice_agent0",
      "pane_id": "%7",
      "status": "running",
      "created_at": 1711276800,
      "channels": ["#general"]
    }
  }
}
```

Merged from current separate `agents.json` — now includes IRC state too.

## Command Output Examples

### `wc-agent irc status`

```
IRC Server:
  type:   local (ergo)
  status: running (pid 12345)
  listen: 127.0.0.1:6667

IRC Client (WeeChat):
  status: running
  pane:   %5
  nick:   alice
```

### `wc-agent agent list`

```
NAME             STATUS   UPTIME  PANE  CHANNELS    WORKSPACE
alice-agent0     running  12m     %7    #general    /tmp/wc-agent-alice_agent0
alice-helper     running  3m      %9    #general    /tmp/wc-agent-alice_helper
```

### `wc-agent agent send agent0 "hello"`

```
Sent to alice-agent0 (pane %7)
```

## Dependencies

Add to `wc-agent` (new pyproject.toml or inline script deps):
- `typer[all]>=0.9.0` — CLI framework

## Files to Create/Modify

### Create
- `docs/e2e-manual-test.md` — Manual test guide

### Modify
- `wc-agent/cli.py` — Full rewrite: argparse → Typer two-level subcommands
- `wc-agent/agent_manager.py` — Add `send()` method, add WeeChat/ergo pane management
- `tests/e2e/e2e-test.sh` — Update to new command format
- `tests/e2e/e2e-test-manual.sh` — Simplify using new CLI
- `tests/e2e/helpers.sh` — Update `wc_agent` helper
- `start.sh` / `stop.sh` — Update to new command format

## Manual Test Guide

`docs/e2e-manual-test.md`:

```markdown
# E2E Manual Test Guide

## Prerequisites

- ergo installed: `~/.local/bin/ergo`
- ergo languages: `~/.local/share/ergo/languages/`
- `weechat-claude.toml` configured with IRC server address
- tmux installed

## Step-by-Step

### 1. Start IRC Server

    $ wc-agent irc daemon start
    Starting ergo IRC server...
    ergo running (pid 12345).

### 2. Start WeeChat

    $ wc-agent irc start
    Starting WeeChat in tmux...
    WeeChat started in pane %5.

Attach to observe:

    $ tmux -CC attach -t weechat-claude

### 3. Verify IRC Status

    $ wc-agent irc status

Should show both server and client running.

### 4. Create Primary Agent

    $ wc-agent agent create agent0

In WeeChat, you should see `alice-agent0` join #general.

### 5. Test Agent Reply

    $ wc-agent agent send agent0 'Use the reply MCP tool to send "Hello everyone, agent0 here!" to #general'

Watch WeeChat #general for the message.

### 6. Test @mention

In WeeChat #general, type:

    @alice-agent0 what is the capital of France?

Agent should auto-respond in the channel.

### 7. Check Agent Status

    $ wc-agent agent list
    $ wc-agent agent status agent0

### 8. Create Second Agent

    $ wc-agent agent create helper
    $ wc-agent agent list

### 9. Agent-to-Agent Communication

    $ wc-agent agent send agent0 'Use the reply tool to send "hello helper, please respond with PONG" to "alice-helper"'

### 10. Stop Agents

    $ wc-agent agent stop helper
    $ wc-agent agent list

### 11. Shutdown Everything

    $ wc-agent shutdown

Verify: no ergo process, no tmux session, no agent panes.
```
