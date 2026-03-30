# Agent Template System Design

**Date:** 2026-03-29
**Status:** Draft

## Problem

zchat agent creation is hardcoded to Claude Code. The `AgentManager` directly writes `.claude/settings.local.json`, `.mcp.json`, and spawns `claude` with fixed args. This prevents users from running other agent types (Gemini CLI, Codex CLI, custom Python bots, arbitrary scripts).

## Solution

A template system that decouples agent type configuration from the agent lifecycle manager. Templates are directories containing metadata, a startup script, and environment variable definitions.

## Template Registry

Templates are stored in `~/.zchat/templates/`, one directory per template. zchat ships a built-in `claude` template that is written to this location on install.

### Load Priority

1. `~/.zchat/templates/{name}/` — user directory (takes precedence)
2. zchat package built-in `templates/{name}/` — fallback

## Template Directory Structure

```
~/.zchat/templates/{name}/
├── template.toml    # Metadata and hooks (shareable)
├── start.sh         # Startup script (shareable)
├── .env.example     # Required variables with defaults/placeholders (shareable)
└── .env             # User's actual values (gitignored, not shared)
```

### template.toml

```toml
[template]
name = "claude"
description = "Claude Code agent with MCP channel server"

[hooks]
pre_stop = "/exit"   # Command sent to tmux pane before stopping. Empty = kill pane directly.
```

### .env.example

Declares all environment variables the template needs. Values use `{{placeholder}}` syntax for variables that zchat injects automatically, or empty string for user-provided values.

```bash
# Auto-injected by zchat
AGENT_NAME={{agent_name}}
IRC_SERVER={{irc_server}}
IRC_PORT={{irc_port}}
IRC_CHANNELS={{irc_channels}}
IRC_TLS={{irc_tls}}
IRC_PASSWORD={{irc_password}}
WORKSPACE={{workspace}}

# User must configure
ANTHROPIC_API_KEY=
```

Built-in placeholders:

| Placeholder | Source |
|---|---|
| `{{agent_name}}` | `scoped_name(name, username)` |
| `{{irc_server}}` | `config.toml [irc].server` |
| `{{irc_port}}` | `config.toml [irc].port` |
| `{{irc_channels}}` | channels param, comma-joined, no `#` prefix |
| `{{irc_tls}}` | `config.toml [irc].tls` |
| `{{irc_password}}` | `config.toml [irc].password` |
| `{{workspace}}` | agent workspace directory path |

### .env

User's personal overrides. Not committed to git. Written by `zchat template set`.

```bash
ANTHROPIC_API_KEY=sk-xxx
```

### start.sh

Executable script that starts the agent process. Environment variables from `.env.example` + `.env` are already injected. Working directory is `$WORKSPACE`.

Must `exec` the final process so the tmux pane tracks the correct PID.

## Built-in Claude Template

### template.toml

```toml
[template]
name = "claude"
description = "Claude Code agent with MCP channel server"

[hooks]
pre_stop = "/exit"
```

### .env.example

```bash
AGENT_NAME={{agent_name}}
IRC_SERVER={{irc_server}}
IRC_PORT={{irc_port}}
IRC_CHANNELS={{irc_channels}}
IRC_TLS={{irc_tls}}
IRC_PASSWORD={{irc_password}}
WORKSPACE={{workspace}}
ANTHROPIC_API_KEY=
# MCP server command — override for dev (e.g., "uv run --project /path zchat-channel")
MCP_SERVER_CMD=zchat-channel
```

### start.sh

```bash
#!/bin/bash
set -euo pipefail

# Parse MCP server command (first word = command, rest = args)
read -ra MCP_PARTS <<< "$MCP_SERVER_CMD"
MCP_CMD="${MCP_PARTS[0]}"
MCP_ARGS="${MCP_PARTS[*]:1}"

mkdir -p .claude
cat > .claude/settings.local.json << 'EOF'
{
  "permissions": {
    "allow": [
      "mcp__zchat-channel__reply",
      "mcp__zchat-channel__join_channel"
    ]
  }
}
EOF

# Build .mcp.json with optional args
if [ -n "$MCP_ARGS" ]; then
  ARGS_JSON=$(printf '%s\n' $MCP_ARGS | jq -R . | jq -s .)
  ARGS_LINE="\"args\": $ARGS_JSON,"
else
  ARGS_LINE=""
fi

cat > .mcp.json << EOF
{
  "mcpServers": {
    "zchat-channel": {
      "command": "$MCP_CMD",
      ${ARGS_LINE}
      "env": {
        "AGENT_NAME": "$AGENT_NAME",
        "IRC_SERVER": "$IRC_SERVER",
        "IRC_PORT": "$IRC_PORT",
        "IRC_CHANNELS": "$IRC_CHANNELS",
        "IRC_TLS": "$IRC_TLS"
      }
    }
  }
}
EOF

exec claude --permission-mode bypassPermissions \
  --dangerously-load-development-channels server:zchat-channel
```

## CLI Changes

### New Commands

```bash
# Project configuration — reads/writes config.toml using tomli-w
zchat set <key> <value>                              # Set project config value
zchat set agents.default_type codex                  # Example

# Template management
zchat template list                                  # List available templates
zchat template show claude                           # Show template details
zchat template set claude ANTHROPIC_API_KEY sk-xxx   # Set .env variable
zchat template create my-bot                         # Create empty template scaffold
```

**Implementation note:** `zchat set` uses `tomllib` to read and `tomli-w` to write `config.toml`. Add `tomli-w` as a dependency in `pyproject.toml`.

`zchat template create my-bot` generates:
```
~/.zchat/templates/my-bot/
├── template.toml    # name="my-bot", description="", hooks.pre_stop=""
├── start.sh         # #!/bin/bash\nexec echo "TODO: implement"
└── .env.example     # default placeholders (AGENT_NAME, IRC_*, WORKSPACE)
```

### Modified Commands

```bash
# agent create gains --type parameter
zchat agent create agent0                        # Uses default_type from config.toml
zchat agent create agent0 --type claude          # Explicit type
zchat agent create agent0 --type irc-bot         # Custom template
```

### config.toml Changes

```toml
[agents]
default_type = "claude"          # New field, default template type
default_channels = ["#general"]
username = ""

# claude_args and mcp_server_cmd removed — now in template
```

## Agent State Changes

`agents.json` records template type per agent:

```json
{
  "alice-agent0": {
    "type": "claude",
    "workspace": "/tmp/zchat-alice_agent0",
    "pane_id": "%42",
    "status": "running",
    "created_at": 1711700000.0,
    "channels": ["#general"]
  }
}
```

## Core Flow: Agent Creation

```
zchat agent create agent0 --type claude
         │
         ▼
    resolve_template("claude")
    ├── ~/.zchat/templates/claude/   (user, priority)
    └── builtin templates/claude/    (fallback)
         │
         ▼
    create workspace (/tmp/zchat-alice_agent0/)
         │
         ▼
    render env:
    ├── .env.example → render {{placeholder}} with actual values
    └── .env → override matching variable names
         │
         ▼
    spawn tmux pane:
      cd $WORKSPACE && env $RENDERED_ENV bash <path-to-start.sh>
         │
         ▼
    save state (agents.json with type: "claude")
```

## Core Flow: Agent Stop

```
zchat agent stop agent0
         │
         ▼
    load agent state → type: "claude"
         │
         ▼
    load_template("claude") → hooks.pre_stop: "/exit"
         │
         ▼
    if pre_stop is non-empty:
      send pre_stop command to tmux pane
      poll pane alive for up to 5s
         │
         ▼
    if pane still alive (or pre_stop was empty):
      tmux kill-pane
```

## Core Flow: Agent Restart

```
zchat agent restart agent0
         │
         ▼
    read agent state → type: "claude", channels: ["#general"]
         │
         ▼
    stop(agent0)
         │
         ▼
    create(agent0, type="claude", channels=["#general"])
    # type is read from saved state, not default_type
```

## AgentManager Changes

### New: template_loader.py

```python
def load_template(name: str) -> dict:
    """Load template, user directory takes priority over built-in."""

def get_start_script(name: str) -> Path:
    """Return path to start.sh, user priority."""

def render_env(name: str, context: dict) -> dict:
    """Read .env.example, render placeholders, overlay .env."""

def list_templates() -> list[dict]:
    """List all available templates (user + built-in, deduplicated)."""
```

### Modified: AgentManager

- `create()` — accepts `type` parameter, delegates workspace setup to template's `start.sh`
- `_spawn_tmux()` — executes template's `start.sh` with rendered env instead of hardcoded `claude` command
- `_force_stop()` — reads `hooks.pre_stop` from template instead of hardcoded `/exit`
- Remove `_create_workspace()` file-writing logic (moved to `start.sh`)
- Remove `claude_args` and `mcp_server_cmd` instance variables

## Sharing Templates

Templates are plain directories, shareable via git:

```bash
# Share
cd ~/.zchat/templates/my-bot
git init && echo ".env" >> .gitignore && git add . && git push

# Install
git clone https://github.com/someone/zchat-template-codex ~/.zchat/templates/codex
cp .env.example .env  # Fill in personal values
```

## Built-in Template Packaging

The built-in `claude` template is shipped as package data in the zchat Python package:

```
zchat/cli/templates/claude/
├── template.toml
├── start.sh
└── .env.example
```

Included via `pyproject.toml`:
```toml
[tool.setuptools.package-data]
"zchat.cli" = ["templates/**/*"]
```

`resolve_template()` checks `~/.zchat/templates/{name}/` first, then falls back to this package data directory. Built-in templates are updated automatically with `zchat self-update`.

## Project-level env_file

The existing `env_file` in config.toml (used for proxies, API keys shared across all agents) is kept as a project-level concept. It is loaded before template env, so template `.env` can override project-level values if needed.

Load order:
1. `config.toml [agents].env_file` — project-wide (proxies, shared keys)
2. Template `.env.example` — rendered placeholders
3. Template `.env` — user overrides per template

## Out of Scope

- Template versioning
- Template dependencies
- Remote template registry / `zchat template install <url>` (users git clone manually)
