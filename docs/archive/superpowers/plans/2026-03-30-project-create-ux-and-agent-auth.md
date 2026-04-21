# Project Create UX Overhaul & Agent Auth Fixes — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `project create` prompt flow, MCP auth env vars, channel server SASL, and plugin loading in agent workspaces.

**Architecture:** Four independent changes coordinated across zchat CLI (`app.py`, `project.py`), Claude template (`start.sh`), and channel server submodule (`server.py`). Auth commands decoupled from project config.

**Tech Stack:** Python/typer CLI, bash (start.sh), irc library (built-in SASL), TOML config.

**Spec:** `docs/superpowers/specs/2026-03-30-project-create-ux-and-agent-auth-design.md`

---

## Chunk 1: project.py — Remove [auth] section

### Task 1: Update `create_project_config()` to drop auth params

**Files:**
- Modify: `zchat/cli/project.py`
- Test: `tests/unit/test_project.py`

- [ ] **Step 1: Update test for config without auth**

In `tests/unit/test_project.py`, replace `test_create_project_config_with_auth` and `test_load_project_config_defaults_auth_to_none` and `test_create_project_config_oidc_empty_nick` with a test that verifies auth is NOT in config:

```python
def test_create_project_config_no_auth_section(tmp_path, monkeypatch):
    """config.toml should not contain [auth] section."""
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("test", server="127.0.0.1", port=6667, tls=False,
                          password="", nick="", channels="#general")
    cfg = load_project_config("test")
    assert "auth" not in cfg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_project.py::test_create_project_config_no_auth_section -v`
Expected: FAIL — config still has `[auth]` section.

- [ ] **Step 3: Update `create_project_config()` — remove auth params and [auth] template**

In `zchat/cli/project.py`, change `create_project_config` signature and template:

```python
def create_project_config(name: str, server: str, port: int, tls: bool,
                          password: str, nick: str, channels: str,
                          env_file: str = "", default_type: str = "claude"):
    """Create project directory and write config.toml."""
    pdir = project_dir(name)
    os.makedirs(pdir, exist_ok=True)
    channels_list = [ch.strip() for ch in channels.split(",") if ch.strip()]
    channels_toml = ", ".join(f'"{ch}"' for ch in channels_list)
    tmux_session = _generate_tmux_session_name(name)
    config_content = f'''[irc]
server = "{server}"
port = {port}
tls = {"true" if tls else "false"}
password = "{password}"

[agents]
default_type = "{default_type}"
default_channels = [{channels_toml}]
username = "{nick}"
env_file = "{env_file}"

[tmux]
session = "{tmux_session}"
'''
    with open(os.path.join(pdir, "config.toml"), "w") as f:
        f.write(config_content)
```

- [ ] **Step 4: Update `load_project_config()` — remove auth defaults**

In `zchat/cli/project.py`, remove the auth defaults block (lines 107-110):

Remove:
```python
    auth = cfg.setdefault("auth", {})
    auth.setdefault("provider", "none")
    auth.setdefault("issuer", "")
    auth.setdefault("client_id", "")
```

- [ ] **Step 5: Fix existing tests that pass auth params**

In `tests/unit/test_project.py`:

Remove these three tests entirely:
- `test_create_project_config_with_auth`
- `test_load_project_config_defaults_auth_to_none`
- `test_create_project_config_oidc_empty_nick`

Update `test_load_project_config` to not assert on auth:
```python
def test_load_project_config(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("cfg-test", server="10.0.0.1", port=6697,
                          tls=True, password="pw", nick="bob", channels="#dev,#general")
    cfg = load_project_config("cfg-test")
    assert cfg["irc"]["server"] == "10.0.0.1"
    assert cfg["irc"]["tls"] is True
    assert cfg["agents"]["username"] == "bob"
    assert "auth" not in cfg
```

- [ ] **Step 6: Run all project tests**

Run: `uv run pytest tests/unit/test_project.py -v`
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add zchat/cli/project.py tests/unit/test_project.py
git commit -m "refactor(project): remove [auth] section from config.toml"
```

---

## Chunk 2: app.py — Auth commands decoupled, project create restructured

### Task 2: Decouple `auth login` from project config

**Files:**
- Modify: `zchat/cli/app.py`
- Test: `tests/unit/test_auth.py`

- [ ] **Step 1: Write test for project-independent auth login**

In `tests/unit/test_auth.py`, add:

```python
def test_device_code_flow_stores_token_endpoint_and_client_id(capsys):
    """device_code_flow stores token_endpoint and client_id in result for later use."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "well-known" in url:
            return httpx.Response(200, json={
                "token_endpoint": "https://kc.test/token",
                "device_authorization_endpoint": "https://kc.test/device",
                "userinfo_endpoint": "https://kc.test/userinfo",
            })
        if url == "https://kc.test/device":
            return httpx.Response(200, json={
                "device_code": "dc", "user_code": "UC",
                "verification_uri": "https://kc.test/device",
                "interval": 0, "expires_in": 600,
            })
        if url == "https://kc.test/token":
            return httpx.Response(200, json={
                "access_token": "at", "refresh_token": "rt", "expires_in": 300,
            })
        if url == "https://kc.test/userinfo":
            return httpx.Response(200, json={"email": "a@test.com"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    result = device_code_flow(issuer="https://kc.test/", client_id="my-id", http_client=client)
    # These fields are needed by auth refresh (no project config dependency)
    assert result["client_id"] == "my-id"
    assert result["token_endpoint"] == "https://kc.test/token"
```

- [ ] **Step 2: Run test to verify it passes** (this tests existing behavior)

Run: `uv run pytest tests/unit/test_auth.py::test_device_code_flow_stores_token_endpoint_and_client_id -v`
Expected: PASS (device_code_flow already stores these).

- [ ] **Step 3: Update `cmd_auth_login()` — remove project dependency**

In `zchat/cli/app.py`, replace `cmd_auth_login`:

```python
@auth_app.command("login")
def cmd_auth_login(
    issuer: str = typer.Option("https://6fzzkh.logto.app/", help="OIDC issuer URL"),
    client_id: str = typer.Option("t7ddhdfqrfgwpmounxdsx", help="OIDC client ID"),
):
    """Authenticate via OIDC device code flow."""
    from zchat.cli.auth import _global_auth_dir
    auth_dir = _global_auth_dir()
    existing = load_cached_token(auth_dir)
    if existing:
        typer.echo(f"Already logged in as: {existing.get('username', '?')} ({existing.get('email', '')})")
        typer.echo("Run 'zchat auth logout' first to re-login.")
        raise typer.Exit(0)
    try:
        result = device_code_flow(issuer=issuer, client_id=client_id)
    except Exception as e:
        typer.echo(f"Login failed: {e}")
        raise typer.Exit(1)
    email = result.get("email", result["username"])
    nick = email.split("@")[0] if "@" in email else email
    result["username"] = nick
    save_token(auth_dir, result)
    typer.echo(f"\nLogged in as: {nick} ({email})")
```

- [ ] **Step 4: Update `cmd_auth_refresh()` — read from auth.json**

In `zchat/cli/app.py`, replace `cmd_auth_refresh`:

```python
@auth_app.command("refresh")
def cmd_auth_refresh():
    """Manually refresh access token."""
    from zchat.cli.auth import _global_auth_dir
    import json
    auth_path = os.path.join(_global_auth_dir(), "auth.json")
    if not os.path.isfile(auth_path):
        typer.echo("Not logged in. Run 'zchat auth login'.")
        raise typer.Exit(1)
    with open(auth_path) as f:
        data = json.load(f)
    token_endpoint = data.get("token_endpoint", "")
    client_id = data.get("client_id", "")
    if not token_endpoint or not client_id:
        typer.echo("Token data incomplete. Run 'zchat auth login' again.")
        raise typer.Exit(1)
    result = refresh_token_if_needed(
        _global_auth_dir(),
        token_endpoint=token_endpoint,
        client_id=client_id,
    )
    if result:
        typer.echo(f"Token refreshed for {result['username']}")
    else:
        typer.echo("Refresh failed. Run 'zchat auth login'.")
        raise typer.Exit(1)
```

- [ ] **Step 5: Run auth tests**

Run: `uv run pytest tests/unit/test_auth.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add zchat/cli/app.py tests/unit/test_auth.py
git commit -m "refactor(auth): decouple login/refresh from project config"
```

### Task 3: Restructure `cmd_project_create()` — agent type multi-select

**Dependency:** Task 1 must be completed first (`create_project_config` signature changed).

**Files:**
- Modify: `zchat/cli/app.py`
- Test: `tests/unit/test_project.py`

- [ ] **Step 1: Write tests for new create flow**

In `tests/unit/test_project.py`, add:

```python
def test_project_create_config_with_default_type(tmp_path, monkeypatch):
    """create_project_config stores the selected default_type."""
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("typed", server="127.0.0.1", port=6667, tls=False,
                          password="", nick="", channels="#general",
                          default_type="claude")
    cfg = load_project_config("typed")
    assert cfg["agents"]["default_type"] == "claude"
    assert "auth" not in cfg


def test_project_create_with_env_file(tmp_path, monkeypatch):
    """Proxy env_file path is stored in config."""
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    env_path = str(tmp_path / "projects" / "proxy-test" / "claude.local.env")
    create_project_config("proxy-test", server="127.0.0.1", port=6667, tls=False,
                          password="", nick="", channels="#general",
                          env_file=env_path)
    cfg = load_project_config("proxy-test")
    assert cfg["agents"]["env_file"] == env_path
```

- [ ] **Step 2: Run tests to verify they pass** (these test the already-updated `create_project_config`)

Run: `uv run pytest tests/unit/test_project.py::test_project_create_config_with_default_type tests/unit/test_project.py::test_project_create_with_env_file -v`
Expected: PASS.

- [ ] **Step 3: Rewrite `cmd_project_create()`**

Replace the entire function body with the new flow:

```python
@project_app.command("create")
def cmd_project_create(name: str):
    """Create a new project with interactive config setup."""
    pdir = project_dir(name)
    if os.path.exists(pdir):
        typer.echo(f"Project '{name}' already exists.")
        raise typer.Exit(1)

    # --- IRC server ---
    typer.echo("IRC Server:")
    typer.echo("  1) zchat.inside.h2os.cloud (recommended)")
    typer.echo("  2) Custom server")
    server_choice = typer.prompt("Choose", default="1")
    if server_choice == "1":
        server = "zchat.inside.h2os.cloud"
        port = 6697
        tls = True
        password = ""
    else:
        server = typer.prompt("IRC server", default="127.0.0.1")
        port = typer.prompt("IRC port", default=6667, type=int)
        tls = typer.confirm("TLS", default=False)
        password = typer.prompt("Password", default="", show_default=False)

    # --- Channels ---
    channels = typer.prompt("Default channels", default="#general")

    # --- Agent type multi-select ---
    from zchat.cli.template_loader import list_templates
    templates = list_templates()
    if not templates:
        typer.echo("Error: No agent templates found.")
        raise typer.Exit(1)
    typer.echo("Agent types:")
    for i, tpl in enumerate(templates, 1):
        tname = tpl["template"]["name"]
        tdesc = tpl["template"].get("description", "")
        typer.echo(f"  {i}) {tname} - {tdesc}")
    selection = typer.prompt("Select types (comma-separated)", default="1")
    selected_indices = [int(s.strip()) - 1 for s in selection.split(",") if s.strip().isdigit()]
    selected_types = []
    for idx in selected_indices:
        if 0 <= idx < len(templates):
            selected_types.append(templates[idx]["template"]["name"])
    if not selected_types:
        selected_types = [templates[0]["template"]["name"]]
    default_type = selected_types[0]

    # --- Type-specific config: Claude ---
    env_file = ""
    if "claude" in selected_types:
        typer.echo("Claude configuration:")
        proxy = typer.prompt("  HTTP proxy (ip:port, leave empty for direct connection)",
                             default="", show_default=False)
        if proxy:
            proxy_url = proxy if proxy.startswith("http") else f"http://{proxy}"
            env_path = os.path.join(pdir, "claude.local.env")
            os.makedirs(pdir, exist_ok=True)
            with open(env_path, "w") as f:
                f.write(f"HTTP_PROXY={proxy_url}\n")
                f.write(f"HTTPS_PROXY={proxy_url}\n")
            env_file = env_path

    create_project_config(name, server=server, port=port, tls=tls,
                          password=password, nick="", channels=channels,
                          env_file=env_file, default_type=default_type)
    typer.echo(f"\nProject '{name}' created at {pdir}/")
    typer.echo(f"Config saved to {pdir}/config.toml")
    if env_file:
        typer.echo(f"Proxy config saved to {pdir}/claude.local.env")
```

- [ ] **Step 4: Run all unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add zchat/cli/app.py tests/unit/test_project.py
git commit -m "feat(project): restructure create flow with agent type multi-select

Closes ezagent42/zchat#24"
```

---

## Chunk 3: Channel server — SASL support & packaging

### Task 4: Add SASL and password auth to channel server

**Files:**
- Modify: `zchat-channel-server/server.py`
- Test: `zchat-channel-server/tests/test_channel_server.py`

- [ ] **Step 1: Write tests for IRC auth env var handling and `setup_irc()` connect kwargs**

In `zchat-channel-server/tests/test_channel_server.py`, add:

```python
from unittest.mock import patch, MagicMock


def test_setup_irc_no_auth(monkeypatch):
    """Without auth env vars, connect() is called without password or sasl_login."""
    monkeypatch.setattr("server.IRC_PASSWORD", "")
    monkeypatch.setattr("server.IRC_SASL_USER", "")
    monkeypatch.setattr("server.IRC_SASL_PASS", "")
    monkeypatch.setattr("server.IRC_SERVER", "localhost")
    monkeypatch.setattr("server.IRC_PORT", 6667)
    monkeypatch.setattr("server.AGENT_NAME", "test-agent")
    monkeypatch.setattr("server.IRC_TLS", False)

    mock_conn = MagicMock()
    mock_reactor = MagicMock()
    mock_reactor.server.return_value.connect.return_value = mock_conn

    with patch("irc.client.Reactor", return_value=mock_reactor):
        import asyncio
        loop = asyncio.new_event_loop()
        queue = asyncio.Queue()
        from server import setup_irc
        setup_irc(queue, loop)
        loop.close()

    call_kwargs = mock_reactor.server.return_value.connect.call_args
    assert "password" not in call_kwargs.kwargs
    assert "sasl_login" not in call_kwargs.kwargs


def test_setup_irc_with_password(monkeypatch):
    """IRC_PASSWORD should be passed to connect()."""
    monkeypatch.setattr("server.IRC_PASSWORD", "secret")
    monkeypatch.setattr("server.IRC_SASL_USER", "")
    monkeypatch.setattr("server.IRC_SASL_PASS", "")
    monkeypatch.setattr("server.IRC_SERVER", "localhost")
    monkeypatch.setattr("server.IRC_PORT", 6667)
    monkeypatch.setattr("server.AGENT_NAME", "test-agent")
    monkeypatch.setattr("server.IRC_TLS", False)

    mock_conn = MagicMock()
    mock_reactor = MagicMock()
    mock_reactor.server.return_value.connect.return_value = mock_conn

    with patch("irc.client.Reactor", return_value=mock_reactor):
        import asyncio
        loop = asyncio.new_event_loop()
        queue = asyncio.Queue()
        from server import setup_irc
        setup_irc(queue, loop)
        loop.close()

    call_kwargs = mock_reactor.server.return_value.connect.call_args
    assert call_kwargs.kwargs["password"] == "secret"
    assert "sasl_login" not in call_kwargs.kwargs


def test_setup_irc_with_sasl(monkeypatch):
    """SASL env vars should set sasl_login and password in connect()."""
    monkeypatch.setattr("server.IRC_PASSWORD", "")
    monkeypatch.setattr("server.IRC_SASL_USER", "alice-agent0")
    monkeypatch.setattr("server.IRC_SASL_PASS", "token123")
    monkeypatch.setattr("server.IRC_SERVER", "localhost")
    monkeypatch.setattr("server.IRC_PORT", 6667)
    monkeypatch.setattr("server.AGENT_NAME", "test-agent")
    monkeypatch.setattr("server.IRC_TLS", False)

    mock_conn = MagicMock()
    mock_reactor = MagicMock()
    mock_reactor.server.return_value.connect.return_value = mock_conn

    with patch("irc.client.Reactor", return_value=mock_reactor):
        import asyncio
        loop = asyncio.new_event_loop()
        queue = asyncio.Queue()
        from server import setup_irc
        setup_irc(queue, loop)
        loop.close()

    call_kwargs = mock_reactor.server.return_value.connect.call_args
    assert call_kwargs.kwargs["sasl_login"] == "alice-agent0"
    assert call_kwargs.kwargs["password"] == "token123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd zchat-channel-server && uv run pytest tests/test_channel_server.py::test_setup_irc_no_auth tests/test_channel_server.py::test_setup_irc_with_password tests/test_channel_server.py::test_setup_irc_with_sasl -v`
Expected: FAIL — `IRC_PASSWORD`, `IRC_SASL_USER`, `IRC_SASL_PASS` not defined in `server.py`, and `connect()` does not accept `password`/`sasl_login`.

- [ ] **Step 3: Add env var reads to `server.py`**

In `zchat-channel-server/server.py`, after line 32 (`IRC_TLS = ...`), add:

```python
IRC_PASSWORD = os.environ.get("IRC_PASSWORD", "")
IRC_SASL_USER = os.environ.get("IRC_SASL_USER", "")
IRC_SASL_PASS = os.environ.get("IRC_SASL_PASS", "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd zchat-channel-server && uv run pytest tests/test_channel_server.py -v`
Expected: All PASS.

- [ ] **Step 5: Update `setup_irc()` — use `sasl_login` and `password` kwargs**

In `zchat-channel-server/server.py`, in `setup_irc()` function, replace the `connect()` call:

```python
def setup_irc(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """Initialize IRC client, connect, subscribe to channels."""
    if IRC_SASL_USER and IRC_SASL_PASS and not IRC_TLS:
        print("[channel-server] WARNING: SASL PLAIN over non-TLS is insecure", file=sys.stderr)
    if IRC_PASSWORD and IRC_SASL_USER and IRC_SASL_PASS:
        print("[channel-server] WARNING: IRC_PASSWORD ignored when SASL is enabled (library limitation)", file=sys.stderr)

    reactor = irc.client.Reactor()
    connect_kwargs = {
        "server": IRC_SERVER,
        "port": IRC_PORT,
        "nickname": AGENT_NAME,
    }
    if IRC_PASSWORD:
        connect_kwargs["password"] = IRC_PASSWORD
    if IRC_SASL_USER and IRC_SASL_PASS:
        connect_kwargs["sasl_login"] = IRC_SASL_USER
        connect_kwargs["password"] = IRC_SASL_PASS
    connection = reactor.server().connect(**connect_kwargs)
```

- [ ] **Step 6: Add `login_failed` handler**

After the `connect()` call and existing event handler registrations, add:

```python
    def on_login_failed(conn, event):
        print(f"[channel-server] SASL authentication failed: {event.arguments}", file=sys.stderr)

    connection.add_global_handler("login_failed", on_login_failed)
```

- [ ] **Step 7: Run all channel server tests**

Run: `cd zchat-channel-server && uv run pytest tests/ -v`
Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
cd zchat-channel-server
git add server.py tests/test_channel_server.py
git commit -m "feat(irc): add password and SASL PLAIN auth support

Uses irc library's built-in sasl_login parameter.
Logs warnings for SASL-over-plaintext and password+SASL conflict."
```

### Task 5: Update channel server packaging for plugin distribution

**Files:**
- Modify: `zchat-channel-server/pyproject.toml`
- Create: `zchat-channel-server/__init__.py`

- [ ] **Step 1: Expand `only-include` in pyproject.toml**

In `zchat-channel-server/pyproject.toml`, replace line 27:

```toml
only-include = ["server.py", "message.py", ".claude-plugin", "commands"]
```

- [ ] **Step 2: Create `__init__.py`**

Create `zchat-channel-server/__init__.py`:

```python
"""zchat-channel-server: Claude Code Channel MCP Server."""
```

- [ ] **Step 3: Verify packaging includes plugin files**

Run: `cd zchat-channel-server && uv build --wheel && unzip -l dist/*.whl | grep -E 'claude-plugin|commands'`
Expected: Output shows `.claude-plugin/plugin.json`, `commands/reply.md`, etc.

- [ ] **Step 4: Commit**

```bash
cd zchat-channel-server
git add pyproject.toml __init__.py
git commit -m "build: include .claude-plugin and commands in wheel distribution"
```

---

## Chunk 4: start.sh — MCP env vars & plugin loading

### Task 6: Update `start.sh` with complete env vars, proxy passthrough, and plugin loading

**Files:**
- Modify: `zchat/cli/templates/claude/start.sh`

- [ ] **Step 1: Rewrite `start.sh`**

Replace `zchat/cli/templates/claude/start.sh` with:

```bash
#!/bin/bash
set -euo pipefail

# Parse MCP server command (first word = command, rest = args)
read -ra MCP_PARTS <<< "$MCP_SERVER_CMD"
MCP_CMD="${MCP_PARTS[0]}"
MCP_ARGS=("${MCP_PARTS[@]:1}")

# --- Locate channel server plugin ---
CHANNEL_PKG=$(python3 -c "
from importlib.metadata import files
for f in files('zchat-channel-server'):
    if f.name == 'server.py':
        print(f.locate().parent)
        break
" 2>/dev/null || echo "")

# Symlink plugin into workspace if found
if [ -n "$CHANNEL_PKG" ] && [ -d "$CHANNEL_PKG/.claude-plugin" ]; then
  ln -sfn "$CHANNEL_PKG/.claude-plugin" .claude-plugin
  ln -sfn "$CHANNEL_PKG/commands" commands
fi

# --- Claude settings ---
mkdir -p .claude
cat > .claude/settings.local.json << 'EOF'
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
EOF

# --- Build .mcp.json ---
if [ ${#MCP_ARGS[@]} -gt 0 ]; then
  ARGS_JSON=$(printf '%s\n' "${MCP_ARGS[@]}" | jq -R . | jq -s .)
  ARGS_LINE="\"args\": $ARGS_JSON,"
else
  ARGS_LINE=""
fi

# Build proxy env entries if set
PROXY_ENV=""
if [ -n "${HTTP_PROXY:-}" ]; then
  PROXY_ENV="${PROXY_ENV}\"HTTP_PROXY\": \"$HTTP_PROXY\","
fi
if [ -n "${HTTPS_PROXY:-}" ]; then
  PROXY_ENV="${PROXY_ENV}\"HTTPS_PROXY\": \"$HTTPS_PROXY\","
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
        "IRC_TLS": "$IRC_TLS",
        "IRC_PASSWORD": "${IRC_PASSWORD:-}",
        "IRC_SASL_USER": "${IRC_SASL_USER:-}",
        "IRC_SASL_PASS": "${IRC_SASL_PASS:-}",
        ${PROXY_ENV}
        "placeholder_": ""
      }
    }
  }
}
EOF

# Clean up trailing comma workaround: remove placeholder_ line
sed -i '' '/"placeholder_"/d' .mcp.json 2>/dev/null || sed -i '/"placeholder_"/d' .mcp.json

exec claude --permission-mode bypassPermissions \
  --dangerously-load-development-channels server:zchat-channel
```

Note: The `placeholder_` + `sed` pattern avoids trailing comma issues in the JSON when proxy env vars are empty. An alternative is to build the JSON with `jq`, but this keeps the approach consistent with the existing `start.sh` style.

- [ ] **Step 2: Verify start.sh is executable**

Run: `ls -la zchat/cli/templates/claude/start.sh`
Expected: `-rwxr-xr-x` permissions.

- [ ] **Step 3: Commit**

```bash
git add zchat/cli/templates/claude/start.sh
git commit -m "feat(template): complete MCP env vars, proxy passthrough, and plugin loading

Adds IRC_PASSWORD, IRC_SASL_USER, IRC_SASL_PASS to .mcp.json env.
Passes HTTP_PROXY/HTTPS_PROXY through to MCP server when set.
Discovers and symlinks zchat plugin for slash command support."
```

---

## Chunk 5: Final verification

### Task 7: Run full test suite and update submodule pointers

- [ ] **Step 1: Run zchat CLI unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS.

- [ ] **Step 2: Run channel server tests**

Run: `cd zchat-channel-server && uv run pytest tests/ -v`
Expected: All PASS.

- [ ] **Step 3: Update submodule pointer**

```bash
git add zchat-channel-server
git commit -m "chore: update zchat-channel-server submodule pointer"
```

- [ ] **Step 4: Run E2E tests** (if ergo + tmux available)

Run: `uv run pytest tests/e2e/ -v -m e2e`
Expected: PASS (or skip if infra not running).
