# Project Create UX Overhaul & Agent Auth Fixes

**Date:** 2026-03-30
**Status:** Draft
**Issue:** ezagent42/zchat#24

## Problem

Three related issues with agent setup:

1. **Proxy prompt UX** — `zchat project create` shows an HTTP proxy prompt unconditionally. Proxy is only relevant for Claude agents' `HTTP_PROXY`/`HTTPS_PROXY` env vars. Users who don't need a proxy find it confusing.

2. **MCP connection failure** — Agents launched by zchat cannot connect to IRC via the MCP channel server. `start.sh` only passes 5 env vars (`AGENT_NAME`, `IRC_SERVER`, `IRC_PORT`, `IRC_CHANNELS`, `IRC_TLS`) to `.mcp.json`, missing `IRC_PASSWORD`, `IRC_SASL_USER`, `IRC_SASL_PASS`. Additionally, the channel server's `connect()` call ignores password and SASL entirely.

3. **Plugin not loaded** — The `zchat@ezagent42` plugin (slash commands: `/zchat:reply`, `/zchat:join`, `/zchat:dm`, `/zchat:broadcast`) is not registered in the agent's workspace. The agent sees "Unknown skill: zchat".

A fourth cleanup: the `[auth]` section in project `config.toml` is now redundant since auth login was made global (`zchat auth login` stores credentials in `~/.zchat/auth.json`). It should be removed.

## Compatibility

Existing projects with `[auth]` in their `config.toml` are unaffected — TOML parsing ignores unknown sections. The `[auth]` section becomes dead config. No migration needed.

## Solution

Four coordinated changes across zchat CLI, the Claude template, and the channel server submodule.

---

## Part 1: `project create` Flow Restructure

### Current Flow

```
IRC server -> channels -> proxy -> auth -> nick
```

### New Flow

```
IRC server -> channels -> agent type (multi-select) -> [Claude: proxy]
```

Auth selection and nickname prompts are removed. The `[auth]` section is removed from `config.toml`.

### Agent Type Multi-Select

After channel selection, scan available templates via `list_templates()` (built-in + user `~/.zchat/templates/`) and display a numbered list:

```
Agent types:
  1) claude - Claude Code agent with MCP channel server
Select types (comma-separated): 1
```

- Default: `1` (first template)
- Multiple selection via comma-separated numbers (e.g., `1,2`)
- First selected type becomes `agents.default_type` in config.toml
- Only show type-specific prompts for selected types

### Claude-Specific Prompts

When `claude` is among the selected types:

```
Claude configuration:
  HTTP proxy (ip:port, leave empty for direct connection):
```

If proxy is set, write `claude.local.env` with `HTTP_PROXY`/`HTTPS_PROXY` as before.

### Files Changed

**`zchat/cli/app.py` — `cmd_project_create()`:**
- Remove auth selection prompt (lines 143-159)
- Remove nickname prompt (lines 161-165)
- Remove unconditional proxy prompt (lines 140-141)
- Add agent type multi-select after channels prompt
- Add Claude-specific proxy prompt (conditional)
- Remove `auth_provider`/`auth_issuer`/`auth_client_id` from `create_project_config()` call

**`zchat/cli/app.py` — `cmd_auth_login()`:**
- Remove dependency on project config for issuer/client_id
- Accept `--issuer` and `--client-id` as CLI options with EZagent defaults
- Remove the `_get_config(ctx)` call — auth login no longer requires a project
- Remove the TLS warning (relocated to agent create — see below)

**`zchat/cli/app.py` — `cmd_auth_refresh()`:**
- Read `token_endpoint` and `client_id` from `auth.json` directly (already stored by `device_code_flow`)
- Remove dependency on project config

**`zchat/cli/project.py` — `create_project_config()`:**
- Remove `auth_provider`, `auth_issuer`, `auth_client_id` parameters
- Remove `[auth]` section from config template

**`zchat/cli/project.py` — `load_project_config()`:**
- Remove auth defaults (lines 107-110)

### New `config.toml` Structure

```toml
[irc]
server = "zchat.inside.h2os.cloud"
port = 6697
tls = true
password = ""

[agents]
default_type = "claude"
default_channels = ["#general"]
username = ""
env_file = ""

[tmux]
session = "zchat-xxxxxxxx-local"
```

---

## Part 2: `start.sh` — MCP Env Vars & Plugin Loading

### Missing Env Vars in `.mcp.json`

Add all IRC auth env vars to the `.mcp.json` env block:

```json
{
  "mcpServers": {
    "zchat-channel": {
      "command": "$MCP_CMD",
      "env": {
        "AGENT_NAME": "$AGENT_NAME",
        "IRC_SERVER": "$IRC_SERVER",
        "IRC_PORT": "$IRC_PORT",
        "IRC_CHANNELS": "$IRC_CHANNELS",
        "IRC_TLS": "$IRC_TLS",
        "IRC_PASSWORD": "$IRC_PASSWORD",
        "IRC_SASL_USER": "$IRC_SASL_USER",
        "IRC_SASL_PASS": "$IRC_SASL_PASS"
      }
    }
  }
}
```

Proxy passthrough: if `$HTTP_PROXY` or `$HTTPS_PROXY` are set in the agent's env, include them in the `.mcp.json` env block via conditional bash:

```bash
# Build proxy env entries if set
PROXY_ENV=""
if [ -n "${HTTP_PROXY:-}" ]; then
  PROXY_ENV="$PROXY_ENV\"HTTP_PROXY\": \"$HTTP_PROXY\","
fi
if [ -n "${HTTPS_PROXY:-}" ]; then
  PROXY_ENV="$PROXY_ENV\"HTTPS_PROXY\": \"$HTTPS_PROXY\","
fi
```

### Plugin Registration

The `zchat@ezagent42` plugin must be available in the agent's workspace for Claude to discover slash commands.

**Problem:** The channel server's `pyproject.toml` uses `only-include = ["server.py", "message.py"]`, so `.claude-plugin/` and `commands/` are NOT distributed in pip installs. The package is a CLI tool, not an importable module — `import zchat_channel_server` will fail.

**Approach:** Include `.claude-plugin/` and `commands/` in the package distribution by updating `pyproject.toml`, then locate them via `importlib.resources` or the `zchat-channel` script path.

#### Step 1: Update channel server packaging

In `zchat-channel-server/pyproject.toml`, expand `only-include` to include plugin files:

```toml
[tool.hatch.build.targets.wheel]
packages = ["."]
only-include = ["server.py", "message.py", ".claude-plugin", "commands"]
```

Add an `__init__.py` to make the package importable for path discovery:

```python
# zchat-channel-server/__init__.py
"""zchat-channel-server: Claude Code Channel MCP Server."""
```

#### Step 2: Discover plugin path in `start.sh`

Use `importlib.metadata` to reliably locate the installed package directory:

```bash
# Locate channel server package (contains .claude-plugin/ and commands/)
CHANNEL_PKG=$(python3 -c "
from importlib.metadata import files
for f in files('zchat-channel-server'):
    if f.name == 'server.py':
        print(f.locate().parent)
        break
" 2>/dev/null || echo "")
```

Note: `find_spec('server')` is avoided because `server` is a generic module name that may collide with other packages in the Python path.

#### Step 3: Symlink plugin into workspace

```bash
if [ -n "$CHANNEL_PKG" ] && [ -d "$CHANNEL_PKG/.claude-plugin" ]; then
  ln -sfn "$CHANNEL_PKG/.claude-plugin" .claude-plugin
  ln -sfn "$CHANNEL_PKG/commands" commands
fi
```

#### Step 4: Enable plugin in settings

Add `enabledPlugins` to `.claude/settings.local.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__zchat-channel__reply",
      "mcp__zchat-channel__join_channel"
    ]
  },
  "enabledPlugins": {
    "zchat@ezagent42": true
  }
}
```

### Files Changed

**`zchat/cli/templates/claude/start.sh`:**
- Add `IRC_PASSWORD`, `IRC_SASL_USER`, `IRC_SASL_PASS` to `.mcp.json` env
- Add conditional proxy env passthrough
- Add plugin discovery and symlinking
- Add `enabledPlugins` to `settings.local.json`

**`zchat-channel-server/pyproject.toml`:**
- Expand `only-include` to include `.claude-plugin` and `commands`

**`zchat-channel-server/__init__.py`:** (new file)
- Empty init to make package importable for path discovery

---

## Part 3: Channel Server SASL Support

The channel server's IRC `connect()` call at `server.py:75` currently ignores all auth:

```python
connection = reactor.server().connect(
    IRC_SERVER, IRC_PORT, AGENT_NAME,
)
```

### Changes

**New env var reads** (after existing ones at lines 28-32):

```python
IRC_PASSWORD = os.environ.get("IRC_PASSWORD", "")
IRC_SASL_USER = os.environ.get("IRC_SASL_USER", "")
IRC_SASL_PASS = os.environ.get("IRC_SASL_PASS", "")
```

**TLS warning:** When SASL credentials are set but TLS is disabled, log a warning:

```python
if IRC_SASL_USER and IRC_SASL_PASS and not IRC_TLS:
    print("[channel-server] WARNING: SASL PLAIN over non-TLS is insecure", file=sys.stderr)
if IRC_PASSWORD and IRC_SASL_USER and IRC_SASL_PASS:
    print("[channel-server] WARNING: IRC_PASSWORD ignored when SASL is enabled (library limitation)", file=sys.stderr)
```

**Password + SASL auth:** The `irc` library (>=20.0) has built-in SASL PLAIN support via the `connect()` method. The `sasl_login` parameter triggers automatic CAP negotiation:

```python
connect_kwargs = {
    "server": IRC_SERVER,
    "port": IRC_PORT,
    "nickname": AGENT_NAME,
}
if IRC_PASSWORD:
    connect_kwargs["password"] = IRC_PASSWORD
if IRC_SASL_USER and IRC_SASL_PASS:
    connect_kwargs["sasl_login"] = IRC_SASL_USER
    connect_kwargs["password"] = IRC_SASL_PASS  # reused for SASL PLAIN
connection = reactor.server().connect(**connect_kwargs)
```

When `sasl_login` is set, the library automatically handles the full SASL state machine:
`connect` → `CAP LS` → `CAP REQ :sasl` → `AUTHENTICATE PLAIN` → `903 SASL success` → `CAP END` → `on_welcome`

The `on_welcome` handler (which joins channels) fires only after SASL completes. No manual gating needed.

**Error handling:** The library emits a `login_failed` event on SASL failure (numeric `904`/`905`). Add a handler:

```python
def on_login_failed(conn, event):
    print(f"[channel-server] SASL authentication failed: {event.arguments}", file=sys.stderr)
connection.add_global_handler("login_failed", on_login_failed)
```

### Files Changed

**`zchat-channel-server/server.py`:**
- Add `IRC_PASSWORD`, `IRC_SASL_USER`, `IRC_SASL_PASS` env var reads
- Add TLS warning when SASL is used without TLS
- Use `sasl_login` and `password` kwargs in `connect()`
- Add `login_failed` event handler

---

## Part 4: Auth Command Cleanup

### `zchat auth login`

**Before:**
```python
@auth_app.command("login")
def cmd_auth_login(ctx: typer.Context):
    cfg = _get_config(ctx)          # requires project
    auth_cfg = cfg.get("auth", {})  # reads from project config
    issuer = auth_cfg["issuer"]
    client_id = auth_cfg["client_id"]
```

**After:**
```python
@auth_app.command("login")
def cmd_auth_login(
    issuer: str = typer.Option("https://6fzzkh.logto.app/", help="OIDC issuer URL"),
    client_id: str = typer.Option("t7ddhdfqrfgwpmounxdsx", help="OIDC client ID"),
):
    # No project config dependency
```

### `zchat auth refresh`

**Before:** Reads `auth_cfg["issuer"]` and `auth_cfg["client_id"]` from project config, then calls `discover_oidc_endpoints()`.

**After:** Reads `token_endpoint` and `client_id` directly from `~/.zchat/auth.json` (already stored there by `device_code_flow()` at `auth.py:157-158`).

### `zchat auth status`

No change needed — already reads from global `auth.json`.

### `zchat auth logout`

No change needed — already operates on global `auth.json`.

### Files Changed

**`zchat/cli/app.py`:**
- `cmd_auth_login()`: remove `ctx` param, add `--issuer`/`--client-id` options with defaults
- `cmd_auth_refresh()`: remove project config dependency, read from `auth.json`
- Remove `set_config_value(ctx.obj["project"], "agents.username", nick)` from login — username is set globally

---

## Testing

### Unit Tests

- `project create` flow: mock `typer.prompt`, verify new prompt order and config.toml output
- `project create` with claude selected: verify proxy prompt appears and `claude.local.env` is written
- `project create` without claude: verify no proxy prompt
- `auth login`/`auth refresh`: verify no project config dependency
- `load_project_config()`: verify no `[auth]` defaults

### E2E Tests

- Full `project create` → `auth login` → `agent create` → verify MCP connects
- Agent can execute `/zchat:reply` (plugin loaded)

### Channel Server Tests

- `setup_irc()` with SASL env vars: verify SASL negotiation
- `setup_irc()` with password only: verify password passed to `connect()`
- `setup_irc()` with no auth: verify existing behavior unchanged
