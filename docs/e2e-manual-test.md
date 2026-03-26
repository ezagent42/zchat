# E2E Manual Test Guide

## Prerequisites

- `ergo` IRC server (`~/.local/bin/ergo`)
- `ergo` languages (`~/.local/share/ergo/languages/`)
- `uv`, `tmux`, `weechat`, `claude` installed

## Setup

Create a tmux session, then source the setup script:

```bash
tmux -CC new -s test        # iTerm2
tmux new -s test            # standard terminal

source tests/e2e/e2e-setup.sh
```

This creates an isolated test environment (unique ergo port, temp `WC_AGENT_HOME`).

## Steps

### 1. Start ergo

```bash
./wc-agent.sh irc daemon start
```

### 2. Start WeeChat

```bash
./wc-agent.sh irc start
```

### 3. Check status

```bash
./wc-agent.sh irc status
```

### 4. Create agent

```bash
./wc-agent.sh agent create agent0
```

In WeeChat `#general`, verify `alice-agent0` joined.

### 5. Test @mention

In WeeChat `#general`:
```
@alice-agent0 what is the capital of France?
```

Agent should respond within ~15s.

### 6. Agent commands

```bash
./wc-agent.sh agent list
./wc-agent.sh agent status agent0
./wc-agent.sh agent send agent0 'Use the reply MCP tool to send "Hello!" to #general'
```

### 7. Second agent

```bash
./wc-agent.sh agent create helper
./wc-agent.sh agent stop helper
```

### 8. Shutdown

```bash
./wc-agent.sh shutdown
source tests/e2e/e2e-cleanup.sh    # if cleanup script exists
```

Or just close the tmux session.
