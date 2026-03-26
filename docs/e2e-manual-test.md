# E2E Manual Test Guide

Step-by-step manual test for the full WeeChat-Claude system using `wc-agent` CLI.

## Prerequisites

- `ergo` IRC server binary installed (`~/.local/bin/ergo`)
- `ergo` languages at `~/.local/share/ergo/languages/`
- `uv`, `tmux`, `weechat`, `claude` installed

## Setup

```bash
# Enter the project
cd ~/Workspace/weechat-claude

# Sync deps (first time)
(cd wc-agent && uv sync)
(cd weechat-channel-server && uv sync)
```

All commands below use the wrapper script at project root:

```bash
./wc-agent.sh <command>
```

---

## Step 0: Create a project (first time only)

```bash
./wc-agent.sh project create e2e-test
```

Interactive prompts:
```
IRC server [127.0.0.1]:
IRC port [6667]:
TLS [false]:
Password []:
Nickname [alice]: alice
Default channels [#general]:
```

Set as default:
```bash
./wc-agent.sh project use e2e-test
```

Verify:
```bash
./wc-agent.sh project list
./wc-agent.sh project show e2e-test
```

## Step 1: Start ergo IRC server

```bash
./wc-agent.sh irc daemon start
```

Expected: `ergo running (pid XXXXX, port 6667).`

Verify:
```bash
pgrep -x ergo && echo "running"
```

## Step 2: Start WeeChat

Open a separate terminal, then:

```bash
weechat -r '/server add wc-local 127.0.0.1/6667 -notls -nicks=alice; /connect wc-local; /join #general'
```

Or use the CLI to start WeeChat in a tmux pane:
```bash
./wc-agent.sh irc start
```

Then attach:
```bash
tmux -CC attach -t weechat-claude    # iTerm2
tmux attach -t weechat-claude        # standard terminal
```

## Step 3: Check IRC status

```bash
./wc-agent.sh irc status
```

Expected:
```
IRC Server:
  status: running (pid XXXXX)
  server: 127.0.0.1:6667

IRC Client (WeeChat):
  status: running (pane %X)
  nick: alice
```

## Step 4: Create agent0

```bash
./wc-agent.sh agent create agent0    # workspace defaults to /tmp/wc-agent-<name>/
```

Expected:
```
Created alice-agent0
  pane: %X
  workspace: /tmp/wc-agent-alice_agent0    # default temp workspace
```

To make the agent work in a specific code directory:
```bash
./wc-agent.sh agent create agent0 --workspace /path/to/your/project
```

In WeeChat, you should see `alice-agent0` join `#general`.

Verify:
```
/names #general
```
Should show: `alice` and `alice-agent0`

## Step 5: Test @mention

In WeeChat `#general`, type:
```
@alice-agent0 what is the capital of France?
```

Expected: `alice-agent0` responds in `#general` within ~30 seconds.

## Step 6: Send text to agent via CLI

```bash
./wc-agent.sh agent send agent0 'Use the reply MCP tool to send "Hello from CLI!" to #general'
```

Expected: `Sent to alice-agent0 (pane %X)`, message appears in WeeChat `#general`.

## Step 7: List and check agent status

```bash
./wc-agent.sh agent list
./wc-agent.sh agent status agent0
```

Expected:
```
alice-agent0
  status:    running
  uptime:    Xm Xs
  pane:      %X
  workspace: /tmp/wc-agent-alice_agent0
  channels:  #general
```

## Step 8: Create a second agent

```bash
./wc-agent.sh agent create helper     # or: --workspace /path/to/code
./wc-agent.sh agent list
```

Expected:
- New pane opens with `claude` for helper
- `alice-helper` joins `#general` in WeeChat

Note: `agent create helper` produces `alice-helper` on IRC (username prefix from config).

## Step 9: Agent-to-agent communication

```bash
./wc-agent.sh agent send agent0 'Use the reply tool to send "hello helper, please respond with PONG" to "alice-helper"'
```

Watch the helper's tmux pane — it should receive the message and respond.

## Step 10: Stop helper

```bash
./wc-agent.sh agent stop helper
./wc-agent.sh agent list
```

Expected:
- helper pane exits
- WeeChat shows `alice-helper has quit`
- `agent list` shows helper as `offline`

## Step 11: Restart agent0

```bash
./wc-agent.sh agent restart agent0
```

Expected: agent0 stops and restarts, rejoins `#general`.

## Step 12: Shutdown everything

```bash
./wc-agent.sh shutdown
```

Expected:
- All agents stop
- WeeChat quits
- ergo stops
- `Shutdown complete.`

---

## Troubleshooting

### ergo won't start
- Check if port 6667 is in use: `lsof -i :6667`
- Check ergo data dir: `ls ~/.local/share/ergo/`
- Ensure `languages/` exists: `ls ~/.local/share/ergo/languages/`

### Agent not joining IRC
- Check channel-server logs in the agent's tmux pane (stderr output)
- Verify ergo is running: `pgrep -x ergo`
- Check project config: `./wc-agent.sh project show`
- Ensure `no_proxy` includes IRC server (for proxied environments)

### WeeChat can't connect
- Use `127.0.0.1` not `localhost` (IPv4 vs IPv6)
- Ensure `-notls` flag is set (ergo listens on plaintext port)
- Ensure ergo started before WeeChat

### Agent has no reply tool
- Wait longer for MCP channel-server to initialize (~10s)
- Check if `Listening for channel messages` appears in agent pane
- Verify `.mcp.json` in agent's workspace has correct `IRC_SERVER`

### `wc-agent.sh` command not found
```bash
chmod +x wc-agent.sh
./wc-agent.sh --help
```

## Project Config Reference

Configs are stored at `~/.wc-agent/projects/<name>/config.toml`:

```toml
[irc]
server = "127.0.0.1"    # IRC server address
port = 6667              # IRC port
tls = false              # TLS encryption
password = ""            # Server password (optional)

[agents]
default_channels = ["#general"]  # Channels agents auto-join
username = "alice"               # IRC nick prefix
```

Edit this file to change IRC server, port, or default username.

## Using a Public IRC Server

```bash
./wc-agent.sh project create libera
# IRC server: irc.libera.chat
# IRC port: 6697
# TLS: true
# Nickname: your-nick
# Default channels: #your-channel

./wc-agent.sh --project libera agent create agent0
```

No `irc daemon start` needed — connects directly to the public server.
