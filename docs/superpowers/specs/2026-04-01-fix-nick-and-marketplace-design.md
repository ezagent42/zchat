# Fix Agent IRC Nick & Marketplace Plugin Loading

**Date:** 2026-04-01
**Related:** [ezagent42/zchat#30](https://github.com/ezagent42/zchat/issues/30)

## Problem

### 1. Agent IRC Nick Incorrect

When OIDC auth is enabled, the agent connects to IRC with the wrong nick:
- Expected: `linyilun-agent0` (OIDC username + agent name)
- Actual: `linyilun` (raw OIDC username, no agent suffix)

Root cause chain:
1. `project.py:128` falls back to `$USER` (e.g. `h2oslabs`) when `agents.username` is empty
2. `agent_manager.py:58` scopes agent as `h2oslabs-agent0` using `$USER`
3. `agent_manager.py:158` sets `irc_sasl_user` to OIDC username (`linyilun`)
4. `server.py:88-92` connects with nick `h2oslabs-agent0` but SASL login `linyilun`
5. ergo auth script rejects the mismatch → ergo forces nick to `linyilun`

Additionally, `irc_manager.py:216` overrides WeeChat nick to OIDC username, creating inconsistency between WeeChat nick and agent scoped names.

### 2. Marketplace Plugin Loading Failure

`zchat@ezagent42` plugin shows `Status: ✘ failed to load` because:
- The `ezagent42` marketplace repo is not cloned locally
- The marketplace.json in `ezagent42/ezagent42` lacks a `zchat` plugin entry

## Design

### Part 1: Username Unification

**Principle:** Username is a global, unique user identity — not a project-level config. Sources: OIDC username or explicit local config. Never auto-inferred from `$USER`.

#### New: `get_username()` in `auth.py`

```python
def get_username() -> str:
    """Return the globally configured username.

    Reads username directly from ~/.zchat/auth.json, bypassing token
    expiry validation. Username is an identity, not a credential —
    it remains valid even when the access token has expired or when
    using --method local (which has no token at all).
    """
    auth_path = os.path.join(_global_auth_dir(), AUTH_FILE)
    if not os.path.isfile(auth_path):
        raise RuntimeError(
            "No username configured. Run one of:\n"
            "  zchat auth login                              # OIDC authentication\n"
            "  zchat auth login --method local --username <name>  # Local mode"
        )
    with open(auth_path) as f:
        data = json.load(f)
    username = data.get("username", "")
    if not username:
        raise RuntimeError(
            "No username configured. Run one of:\n"
            "  zchat auth login                              # OIDC authentication\n"
            "  zchat auth login --method local --username <name>  # Local mode"
        )
    return username
```

Note: `get_username()` reads auth.json directly — it does NOT use `load_cached_token()` which rejects entries without a valid `expires_at`. This is intentional: username is an identity, not a credential. For `--method local` (no token, no expiry), only `{"username": "..."}` is stored.

#### `zchat auth login` — Add `--method` Parameter

Current: OIDC device code flow only.

New signature:
```python
@auth_app.command("login")
def cmd_auth_login(
    issuer: str = ...,
    client_id: str = ...,
    method: str = typer.Option("oidc", help="Auth method: oidc or local"),
    username: str = typer.Option("", help="Username for local method"),
):
```

Behavior:
- `--method oidc` (default): Current OIDC device code flow. Username extracted from OIDC userinfo.
- `--method local --username <name>`: Write `{"username": sanitize_irc_nick(name)}` to auth.json. No token. For local ergo without OIDC.
- `--method local` without `--username`: Error, require `--username`.
- If auth.json already has credentials: current behavior is early-exit with "Already logged in... Run 'zchat auth logout' first." Keep this behavior — `zchat auth logout` + `zchat auth login` is the re-login flow.

#### Remove `$USER` Fallback

**`project.py`** — `load_project_config()`:
- Delete lines 128-129: `if not agents.get("username"): agents["username"] = os.environ.get("USER", "user")`
- The `[agents].username` field in config.toml becomes unused for identity. Keep the field for backward compat but ignore it for nick resolution.

**`app.py`** — `_get_agent_manager()`:
- Change `username=cfg["agents"]["username"]` to `username=get_username()`
- Import `get_username` from `zchat.cli.auth`

**`app.py`** — `_get_irc_manager()` (or wherever IrcManager is created):
- Same: use `get_username()` instead of config username

**`irc_manager.py`** — `start_weechat()`:
- Line 198: Change `nick = nick_override or self.config.get("agents", {}).get("username") or os.environ.get("USER", "user")` to `nick = nick_override or get_username()`
- Lines 213-216: Delete `nick = sasl_user` (the line that overrides nick with SASL username). Keep the surrounding `sasl_cmds` setup — SASL user/pass still need to be configured for WeeChat authentication. The nick is already correct from `get_username()`.
- Line 298 (`status()` method): Change nick source from `self.config.get("agents", {}).get("username")` to `get_username()` for consistency.

**`agent_manager.py`** — `_build_env_context()`:
- Lines 155-160: `get_credentials()` returns `(username, token)` for OIDC or `None` for local auth. For OIDC, `irc_sasl_user` and `irc_sasl_pass` are set. For local auth (no token), `get_credentials()` returns `None` and SASL env vars stay empty — local ergo doesn't require SASL. No code change needed here.

**`project create`** — `cmd_project_create()`:
- Remove `--nick` parameter. Username is global, not per-project.
- `config.toml` template: set `username = ""` (ignored, kept for compat).

#### Result After Fix

```
get_username() → "linyilun"  (from auth.json)
    ↓
scoped_name("agent0", "linyilun") → "linyilun-agent0"
    ↓
AGENT_NAME env var → "linyilun-agent0"
    ↓
server.py connect(nick="linyilun-agent0", sasl_login="linyilun")
    ↓
ergo auth: owner "linyilun" == SASL user "linyilun" ✓
    ↓
IRC nick: linyilun-agent0 ✓
```

WeeChat:
```
get_username() → "linyilun"
    ↓
WeeChat nick: linyilun
SASL user: linyilun (same)
    ↓
ergo auth: nick "linyilun" == SASL user "linyilun" ✓
```

### Part 2: Marketplace Fix

#### Add `ezagent42/ezagent42` as Git Submodule

```bash
git submodule add https://github.com/ezagent42/ezagent42.git ezagent42-marketplace
```

#### Update marketplace.json

Add zchat plugin entry to `ezagent42-marketplace/.claude-plugin/marketplace.json`:

```json
{
  "plugins": {
    "feishu": { ... },
    "zchat": {
      "version": "0.1.0",
      "description": "IRC channel for Claude Code — reply, join, dm, broadcast via slash commands",
      "source": {
        "type": "git-subdir",
        "repo": "ezagent42/claude-zchat-channel",
        "subdir": "."
      }
    }
  }
}
```

#### Push & Re-register

After pushing the marketplace.json update:
```bash
claude plugin marketplace add ezagent42/ezagent42
claude plugin install zchat@ezagent42 --scope project
```

### Part 3: Test Impact

#### Unit Tests

- Update `_make_manager()` helper — `username` parameter now comes from `get_username()`, not config
- Tests that create AgentManager need to pass a valid username directly
- New test: `test_get_username_from_auth` — verify `get_username()` reads from auth.json
- New test: `test_get_username_raises_when_not_configured` — verify error message

#### E2E Tests

- E2E `conftest.py` — currently sets `username = "alice"` in config.toml. Change to write auth.json with `{"username": "alice"}` in the isolated `ZCHAT_HOME`.
- E2E tests use local ergo without OIDC, so no SASL auth. The scoped name `alice-agent0` continues to work.

#### Pre-release Tests

- Pre-release tests use the installed binary with real OIDC or local auth.
- If running with OIDC, username comes from OIDC.
- If running without OIDC, tests need `zchat auth login --method local --username <name>` before agent tests.

### Files Changed

| File | Change |
|------|--------|
| `zchat/cli/auth.py` | Add `get_username()` function |
| `zchat/cli/app.py` | `auth login`: add `--method`/`--username` params; `_get_agent_manager()`: use `get_username()` |
| `zchat/cli/project.py` | Remove `$USER` fallback in `load_project_config()` |
| `zchat/cli/irc_manager.py` | `start_weechat()`: use `get_username()`, delete `nick = sasl_user` line; `status()`: use `get_username()` |
| `zchat/cli/app.py` | `cmd_project_remove()`: use `get_username()` for AgentManager construction |
| `zchat/cli/agent_manager.py` | No changes (receives username from caller) |
| `tests/unit/test_agent_manager.py` | Update `_make_manager()` to not depend on config username |
| `tests/unit/test_auth.py` | Add tests for `get_username()` |
| `tests/e2e/conftest.py` | Write auth.json with `username: "alice"` instead of config.toml username |
| `tests/pre_release/conftest.py` | Ensure auth is configured before agent tests |
| `ezagent42-marketplace/` | New git submodule |
| `ezagent42-marketplace/.claude-plugin/marketplace.json` | Add zchat plugin entry |

### What Is NOT Changed

- `zchat_protocol/naming.py` — `scoped_name()` logic unchanged
- `zchat-channel-server/server.py` — IRC connection logic unchanged (nick and SASL user are now correct upstream)
- `ergo_auth_script.py` — Validation logic unchanged (owner == SASL user will now match)
- `config.toml` schema — `[agents].username` field kept but ignored for identity
