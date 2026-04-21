# OIDC Authentication for zchat

## Context

zchat currently has **zero authentication**. The `password` field in `config.toml` is collected but never used. Any user knowing the IRC server address can connect with any nick, impersonating others. This design adds real identity verification via Keycloak (OIDC) integrated into the IRC layer through ergo's auth-script mechanism.

**Goals:**
- Ensure IRC nick identity is trustworthy (prevent impersonation)
- Integrate with existing Keycloak IdP for all users (internal + temporary)
- IRC-level enforcement via ergo SASL
- Agent authentication via owner's token delegation

## Architecture

```
┌─────────────┐     OIDC Device Code     ┌────────────┐
│ zchat CLI   │ ◄──────────────────────► │  Keycloak  │
│             │     access_token          │  (IdP)     │
└──────┬──────┘                           └────────────┘
       │                                        ▲
       │ SASL PLAIN                             │
       │ (username + token)                     │ HTTP /userinfo
       │                                        │
       ▼                                        │
┌──────────────┐    auth-script    ┌────────────┴─┐
│  ergo IRC    │ ──────────────► │  verify.py     │
│  server      │    stdin/stdout   │  (~30 lines)  │
└──────────────┘                   └───────────────┘
```

### Authentication Flow

1. User runs `zchat auth login` (or first `zchat project create` with OIDC config)
2. CLI initiates OIDC device code flow with Keycloak
3. User opens browser URL, enters device code, logs in via Keycloak
4. CLI polls Keycloak token endpoint, receives `access_token` + `refresh_token`
5. Tokens cached to `~/.zchat/projects/<name>/auth.json` (mode 0600)
6. Subsequent IRC connections (WeeChat, channel-server) use SASL PLAIN with `username:access_token`
7. Ergo's auth-script receives credentials, calls Keycloak `/userinfo` to validate
8. On success, ergo auto-creates account and logs user in

### Agent Authentication

Agents (e.g., `alice-agent0`) authenticate using the owner's cached token:
- `zchat agent create agent0` reads `auth.json`, passes token to channel-server as `IRC_SASL_PASS`
- auth-script validates the token, checks that `preferred_username` from Keycloak matches the agent's owner prefix (e.g., `alice-agent0` → owner `alice`)
- No additional Keycloak configuration needed per agent

## Components

### New: `zchat/cli/auth.py` — OIDC Authentication Module

Responsibilities:
- `device_code_flow(issuer, client_id)` → initiates flow, returns `access_token`, `username`
- `load_cached_token(project_dir)` → reads `auth.json`, checks expiry
- `refresh_token_if_needed(project_dir, issuer, client_id)` → auto-refresh using `refresh_token`
- `save_token(project_dir, token_data)` → writes `auth.json` with mode 0600
- `get_credentials(project_dir)` → returns `(username, token)` for IRC connections, refreshing if needed

OIDC discovery via `GET {issuer}/.well-known/openid-configuration` to find endpoints.

Dependencies: `httpx` (must be added explicitly to `zchat`'s `pyproject.toml`).

### New: `ergo-auth-script.py` — Ergo Authentication Script

~30 lines. Ergo auth-script protocol:
- Reads JSON from stdin: `{"accountName": "alice", "passphrase": "<token>"}`
- Calls Keycloak userinfo: `GET /userinfo` with `Authorization: Bearer <token>`
- For agents: checks `preferred_username` from Keycloak matches owner prefix of `accountName`
  - e.g., accountName `alice-agent0` → expects `preferred_username == "alice"`
- Writes JSON to stdout: `{"success": true, "accountName": "alice"}` or `{"success": false, "error": "..."}`

Configuration via environment variables:
- `KEYCLOAK_USERINFO_URL` — Keycloak userinfo endpoint

Packaged alongside ergo data, copied during `daemon_start()`.

### New: CLI commands — `zchat auth`

```
zchat auth login    — Trigger OIDC device code flow, cache token
zchat auth status   — Show current auth state (username, token expiry)
zchat auth refresh  — Manually refresh access token (for debugging)
zchat auth logout   — Clear cached tokens
```

### Modified: `zchat/cli/project.py` — Config Schema

New `[auth]` section in `config.toml`:

```toml
[auth]
provider = "oidc"         # "oidc" | "none"
issuer = "https://keycloak.company.com/realms/zchat"
client_id = "zchat-cli"
```

- `provider = "none"` preserves backward compatibility (no auth, current behavior)
- `create_project_config()` accepts new auth parameters
- `load_project_config()` defaults `auth.provider` to `"none"`

### Modified: `zchat/cli/app.py` — Project Create + Auth Commands

- `zchat project create` adds optional OIDC prompts (issuer URL, client_id)
- Register `auth_app` typer group with login/status/logout commands
- After `project create` with OIDC config, prompt user to `zchat auth login`

### Modified: `zchat/cli/irc_manager.py`

**`daemon_start()`:**
- When generating ergo config, inject auth-script settings:
  ```yaml
  accounts:
    auth-script:
      enabled: true
      command: "/path/to/ergo-auth-script.py"
      autocreate: true
    require-sasl:
      enabled: true   # when auth.provider == "oidc"
  ```
- Copy `ergo-auth-script.py` to ergo data directory
- Set `KEYCLOAK_USERINFO_URL` env var for the auth-script process

**`start_weechat()`:**
- When auth is configured, add SASL settings to WeeChat:
  ```
  /set irc.server.wc-local.sasl_mechanism PLAIN
  /set irc.server.wc-local.sasl_username {username}
  /set irc.server.wc-local.sasl_password {token}
  ```
- Load credentials via `auth.get_credentials()`

### Modified: `zchat-channel-server/server.py`

- `setup_irc()`: use `sasl_login` and `password` parameters in `connection.connect()`:
  ```python
  connection = reactor.server().connect(
      IRC_SERVER, IRC_PORT, AGENT_NAME,
      sasl_login=os.environ.get("IRC_SASL_USER"),
      password=os.environ.get("IRC_SASL_PASS"),
  )
  ```
- Graceful fallback: if `IRC_SASL_USER` not set, connect without auth (for `provider = "none"`)

### Modified: `zchat/cli/agent_manager.py`

- `AgentManager` receives `project_dir` path, calls `auth.get_credentials()` internally
- When creating agent MCP config, inject auth credentials:
  ```python
  env["IRC_SASL_USER"] = scoped_name  # e.g., "alice-agent0"
  env["IRC_SASL_PASS"] = cached_token
  env["AUTH_TOKEN_FILE"] = auth_json_path  # for reconnect refresh
  ```
- `zchat agent create` checks for valid credentials first; prompts user to `zchat auth login` if missing

## Token Lifecycle

```
login → access_token (short-lived, e.g., 5min)
      → refresh_token (long-lived, e.g., 30 days)

connect IRC → check access_token expiry
            → if expired, use refresh_token to get new access_token
            → if refresh_token expired, prompt re-login

agent create → snapshot current access_token into agent env
             → agent reconnect handler should re-read token (future improvement)
```

## Why auth-script over ergo's native OAuth2

Ergo has a built-in `accounts.oauth2` section with introspection support. We chose auth-script instead because:
- Ergo's OAuth2 requires SASL OAUTHBEARER mechanism, which the Python `irc` library and many IRC clients do not support
- auth-script works with SASL PLAIN, which has universal client support (`irc` lib's `sasl_login`, WeeChat native)
- auth-script gives us flexibility to validate token + check agent owner-prefix in the same script

## Agent Token Lifecycle

Ergo only validates SASL credentials at connection time — it does not re-validate mid-session. This means:
- A connected agent stays connected even after its token expires
- The critical moment is **reconnection** (after ergo restart, network issues, etc.)

Strategy:
- Agent's `on_disconnect` handler reads fresh credentials from `auth.json` before reconnecting (not the stale env var snapshot)
- `auth.json` is kept fresh by the CLI's auto-refresh mechanism (`refresh_token_if_needed()`)
- Keycloak access token lifetime should be ≥1 hour for robustness (configured in Keycloak realm settings)
- If refresh_token is also expired, the agent logs an error and stops reconnecting — user must `zchat auth login` again

Implementation in `server.py`:
```python
def on_disconnect(conn, event):
    # Read fresh credentials from auth.json (not env var snapshot)
    fresh_token = _read_auth_token()  # reads from AUTH_TOKEN_FILE env
    if fresh_token:
        conn.reconnect()  # with updated password
    else:
        print("Auth token expired, cannot reconnect", file=sys.stderr)
```

## Security

1. **Token storage**: `auth.json` with file permission `0600`, contains `access_token`, `refresh_token`, `expires_at`
2. **Transport**: SASL PLAIN transmits token in base64. Safe on loopback (127.0.0.1). Remote ergo MUST use TLS.
3. **TLS enforcement**: `zchat auth login` warns/errors when `auth.provider=oidc` + remote server + `tls=false`
4. **auth-script isolation**: ergo spawns the script per authentication attempt with configurable concurrency limit and timeout (9s default)
5. **Token rotation**: access_token is short-lived; refresh_token handles seamless renewal
6. **Revocation**: Keycloak admin can revoke sessions; auth-script calls `/userinfo` which will fail for revoked tokens
7. **Env var exposure**: `IRC_SASL_PASS` in agent env is visible via `ps`. Acceptable for local dev; for production, consider writing token to a temp file instead.

## Backward Compatibility

- `auth.provider = "none"` (default) preserves current behavior — no SASL, no auth-script
- Existing projects without `[auth]` section continue to work unchanged
- `require-sasl` only enabled when `auth.provider == "oidc"`

## Verification

1. **Unit tests**: Test `auth.py` functions (token caching, refresh logic, credential loading)
2. **auth-script test**: Mock Keycloak userinfo endpoint, test script stdin/stdout protocol
3. **Integration test**: Start ergo with auth-script → connect via SASL PLAIN → verify identity
4. **E2E test**: Full flow — `zchat project create` with OIDC → `zchat auth login` (mock Keycloak) → `zchat agent create` → verify agent connected with correct nick

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `zchat/cli/auth.py` | New | OIDC device code flow, token management |
| `ergo-auth-script.py` | New | Ergo auth-script for Keycloak validation |
| `zchat/cli/app.py` | Modify | Add `zchat auth` commands, update project create |
| `zchat/cli/project.py` | Modify | Add `[auth]` config section |
| `zchat/cli/irc_manager.py` | Modify | Inject auth-script config, WeeChat SASL |
| `zchat-channel-server/server.py` | Modify | SASL connection params |
| `zchat/cli/agent_manager.py` | Modify | Pass auth credentials to agents |
| `pyproject.toml` | Modify | Add `httpx` dependency (if not present) |
