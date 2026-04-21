# Separate IRC Credentials from Nickname

**Date:** 2026-04-01

## Problem

The codebase conflates two distinct IRC identity concepts:

- **Credential** — proof of identity: `(username, token)`. The username is always the OIDC user (e.g., `linyilun`). The token is an OIDC access token shared by all connections belonging to that user.
- **Nickname** — IRC display identity. For a user: `linyilun`. For an agent: `linyilun-agent0`.

The environment variable `IRC_SASL_USER` was used to pass the OIDC username to the channel server, which then used it as the SASL login. But ergo treats the SASL login as the `accountName`, which determines the connection's nick. This caused agents to lose their scoped nick (e.g., `linyilun-agent0` → `linyilun`).

A one-line fix (`sasl_login = AGENT_NAME`) was applied, but the underlying naming confusion remains: `IRC_SASL_USER` still exists as an env var, `irc_sasl_user` as a template placeholder, and the code still passes credentials and nickname through ambiguously named variables.

## Design

### Concept Model

```
IRC connection = (nickname, token)
  - nickname: who I am on IRC (AGENT_NAME for agents, username for WeeChat)
  - token: OIDC access token proving I belong to the user who owns this nickname

SASL PLAIN = \x00{nickname}\x00{token}
  - ergo auth script receives accountName=nickname, validates owner matches token
```

There is no separate "SASL user" — the nickname IS the SASL login. The token is the only credential. `IRC_SASL_USER` is eliminated entirely.

### Changes

#### 1. Environment Variables

| Old | New | Notes |
|-----|-----|-------|
| `IRC_SASL_USER` | Removed | Nickname comes from `AGENT_NAME` |
| `IRC_SASL_PASS` | `IRC_AUTH_TOKEN` | Semantic: it's a token, not a password |

#### 2. `agent_manager.py` — `_build_env_context()` (lines 147-159)

Old context keys:
```python
"irc_sasl_user": "",
"irc_sasl_pass": "",
```

New:
```python
"irc_auth_token": "",
```

When credentials exist (`get_credentials()` returns `(username, token)`), only the token is passed:
```python
creds = get_credentials()
if creds:
    _, token = creds
    context["irc_auth_token"] = token
```

The credential username is not passed — it's not needed. The agent's nickname (`AGENT_NAME`) is already in the context.

#### 3. `.env.example` Template

Old:
```
IRC_SASL_USER={{irc_sasl_user}}
IRC_SASL_PASS={{irc_sasl_pass}}
```

New:
```
IRC_AUTH_TOKEN={{irc_auth_token}}
```

#### 4. `start.sh` Template

Update the `jq` command that builds `.mcp.json` environment block:

Old args: `--arg sasl_user "${IRC_SASL_USER:-}"` + `--arg sasl_pass "${IRC_SASL_PASS:-}"`
New args: `--arg auth_token "${IRC_AUTH_TOKEN:-}"`

Old env block:
```json
IRC_SASL_USER: $sasl_user,
IRC_SASL_PASS: $sasl_pass,
```

New env block:
```json
IRC_AUTH_TOKEN: $auth_token,
```

#### 5. `server.py` (channel-server)

Old:
```python
IRC_SASL_USER = os.environ.get("IRC_SASL_USER", "")
IRC_SASL_PASS = os.environ.get("IRC_SASL_PASS", "")

if IRC_SASL_USER and IRC_SASL_PASS:
    connect_kwargs["sasl_login"] = AGENT_NAME
    connect_kwargs["password"] = IRC_SASL_PASS
```

New:
```python
IRC_AUTH_TOKEN = os.environ.get("IRC_AUTH_TOKEN", "")

if IRC_AUTH_TOKEN:
    connect_kwargs["sasl_login"] = AGENT_NAME
    connect_kwargs["password"] = IRC_AUTH_TOKEN
```

Single condition (`IRC_AUTH_TOKEN` exists), single source of truth for login (`AGENT_NAME`).

#### 6. `irc_manager.py` — WeeChat SASL (lines 212-221)

Old:
```python
creds = get_credentials()
if creds:
    sasl_user, sasl_pass = creds
    sasl_cmds = (
        f"; /set irc.server.{srv_name}.sasl_mechanism PLAIN"
        f"; /set irc.server.{srv_name}.sasl_username {sasl_user}"
        f"; /set irc.server.{srv_name}.sasl_password {sasl_pass}"
    )
```

New:
```python
creds = get_credentials()
if creds:
    _, token = creds
    sasl_cmds = (
        f"; /set irc.server.{srv_name}.sasl_mechanism PLAIN"
        f"; /set irc.server.{srv_name}.sasl_username {nick}"
        f"; /set irc.server.{srv_name}.sasl_password {token}"
    )
```

`sasl_username` = `nick` (already resolved via `get_username()`), `sasl_password` = token.

#### 7. Nick Assertion in `server.py` (防回归)

Add to the `on_welcome` handler in `setup_irc()`:

```python
def on_welcome(connection, event):
    if connection.real_nickname != AGENT_NAME:
        print(f"[channel-server] WARNING: nick mismatch! "
              f"expected={AGENT_NAME} actual={connection.real_nickname}",
              file=sys.stderr)
```

This detects future regressions where ergo overrides the nick.

### Files Changed

| File | Change |
|------|--------|
| `zchat/cli/agent_manager.py` | Replace `irc_sasl_user`/`irc_sasl_pass` with `irc_auth_token` |
| `zchat/cli/templates/claude/.env.example` | Replace `IRC_SASL_USER`/`IRC_SASL_PASS` with `IRC_AUTH_TOKEN` |
| `zchat/cli/templates/claude/start.sh` | Update jq args and env block |
| `zchat-channel-server/server.py` | Replace `IRC_SASL_USER`/`IRC_SASL_PASS` with `IRC_AUTH_TOKEN`, add nick assertion |
| `zchat/cli/irc_manager.py` | Use `nick` for sasl_username, `token` for sasl_password |

### What Is NOT Changed

- `auth.py` — `get_credentials()` returns `(username, token)` as before
- `get_username()` — unchanged
- `ergo_auth_script.py` — unchanged (validates owner from token matches nick owner)
- `zchat_protocol/naming.py` — `scoped_name()` unchanged
- `AGENT_NAME` env var — unchanged, already correct
