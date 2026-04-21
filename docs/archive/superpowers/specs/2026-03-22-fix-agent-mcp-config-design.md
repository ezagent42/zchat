# Fix: Agent Launch via --mcp-config

**Date:** 2026-03-22
**Base:** PR #6 (`fix-e2e-testing`)

## Problem

`weechat-agent.py:create_agent()` and `start.sh` launch claude with deprecated
`--dangerously-load-development-channels plugin:weechat-channel`. Claude CLI no
longer accepts bare `plugin:<name>` format, causing immediate exit.

## Solution

Replace with `--mcp-config` pattern, matching E2E tests' proven approach.

### Changes

**1. `weechat-agent.py`**

- Add `generate_mcp_config(name) → path` — writes `/tmp/wc-mcp-{name}.json`
  with `type: "stdio"`, `AGENT_NAME` in env field
- `create_agent()` — use `--permission-mode bypassPermissions --mcp-config <path>`
- `stop_agent()` — cleanup temp config file
- `agent_deinit()` — cleanup all temp configs

**2. `start.sh`**

- Generate MCP config before launching agent0
- Use `--permission-mode bypassPermissions --mcp-config <path>`

### MCP Config Format (from E2E)

```json
{
  "mcpServers": {
    "weechat-channel": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--project", "<dir>/weechat-channel-server",
               "python3", "<dir>/weechat-channel-server/server.py"],
      "env": { "AGENT_NAME": "<scoped_name>" }
    }
  }
}
```

### What Does Not Change

- `server.py` — no changes (PR #6 lazy init already applied)
- `.mcp.json` — retained for local dev reference
- Zenoh connection logic, agent lifecycle management
