# Fix Agent IRC Nick & Marketplace Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix agent IRC nick (use global username from auth.json instead of $USER) and fix marketplace plugin loading.

**Architecture:** Centralize username as a global identity in `~/.zchat/auth.json`. Remove all `$USER` fallbacks. Add `--method local` to `zchat auth login` for non-OIDC environments. Add ezagent42 marketplace as git submodule.

**Tech Stack:** Python/Typer CLI, IRC (irc library), OIDC auth, git submodules

---

## Chunk 1: Core Auth Changes

### Task 1: Add `get_username()` to auth.py

**Files:**
- Modify: `zchat/cli/auth.py`
- Test: `tests/unit/test_auth.py`

- [ ] **Step 1: Write failing tests for `get_username()`**

Add to `tests/unit/test_auth.py`:

```python
def test_get_username_from_auth(tmp_path):
    """get_username() reads username from auth.json."""
    import json
    from zchat.cli.auth import get_username
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps({"username": "alice"}))
    result = get_username(base_dir=str(tmp_path))
    assert result == "alice"


def test_get_username_raises_when_not_configured(tmp_path):
    """get_username() raises RuntimeError when auth.json missing."""
    import pytest
    from zchat.cli.auth import get_username
    with pytest.raises(RuntimeError, match="No username configured"):
        get_username(base_dir=str(tmp_path))


def test_get_username_raises_when_no_username_field(tmp_path):
    """get_username() raises when auth.json exists but has no username."""
    import json, pytest
    from zchat.cli.auth import get_username
    (tmp_path / "auth.json").write_text(json.dumps({"access_token": "x"}))
    with pytest.raises(RuntimeError, match="No username configured"):
        get_username(base_dir=str(tmp_path))


def test_get_username_works_with_expired_token(tmp_path):
    """get_username() returns username even when token is expired (local auth)."""
    import json
    from zchat.cli.auth import get_username
    (tmp_path / "auth.json").write_text(json.dumps({"username": "bob"}))
    # No expires_at field — simulates --method local
    result = get_username(base_dir=str(tmp_path))
    assert result == "bob"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_auth.py::test_get_username_from_auth tests/unit/test_auth.py::test_get_username_raises_when_not_configured tests/unit/test_auth.py::test_get_username_raises_when_no_username_field tests/unit/test_auth.py::test_get_username_works_with_expired_token -v`

Expected: FAIL with `ImportError` (get_username not defined)

- [ ] **Step 3: Implement `get_username()` in auth.py**

Add to `zchat/cli/auth.py` after the `_global_auth_dir()` function:

```python
def get_username(base_dir: str | None = None) -> str:
    """Return the globally configured username.

    Reads username directly from auth.json, bypassing token expiry
    validation. Username is an identity, not a credential — it remains
    valid even when the access token has expired or when using
    --method local (which has no token at all).
    """
    if base_dir is None:
        base_dir = _global_auth_dir()
    auth_path = os.path.join(base_dir, AUTH_FILE)
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_auth.py -v -k get_username`

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add zchat/cli/auth.py tests/unit/test_auth.py
git commit -m "feat(auth): add get_username() — read global identity from auth.json"
```

### Task 2: Add `--method local` to `zchat auth login`

**Files:**
- Modify: `zchat/cli/app.py:341-364`

- [ ] **Step 1: Modify `cmd_auth_login()` in app.py**

Replace the current `cmd_auth_login` function (lines 341-364) with:

```python
@auth_app.command("login")
def cmd_auth_login(
    issuer: str = typer.Option("https://6fzzkh.logto.app/", help="OIDC issuer URL"),
    client_id: str = typer.Option("t7ddhdfqrfgwpmounxdsx", help="OIDC client ID"),
    method: str = typer.Option("oidc", help="Auth method: oidc or local"),
    username: str = typer.Option("", help="Username for local method"),
):
    """Authenticate via OIDC device code flow or set local username."""
    from zchat.cli.auth import _global_auth_dir, _sanitize_irc_nick
    auth_dir = _global_auth_dir()
    existing = load_cached_token(auth_dir)
    if existing:
        typer.echo(f"Already logged in as: {existing.get('username', '?')} ({existing.get('email', '')})")
        typer.echo("Run 'zchat auth logout' first to re-login.")
        raise typer.Exit(0)

    if method == "local":
        if not username:
            typer.echo("Error: --username is required for --method local")
            raise typer.Exit(1)
        nick = _sanitize_irc_nick(username)
        if not nick:
            typer.echo(f"Error: '{username}' is not a valid IRC nick")
            raise typer.Exit(1)
        save_token(auth_dir, {"username": nick})
        typer.echo(f"Username set: {nick}")
        return

    # OIDC device code flow (default)
    try:
        result = device_code_flow(issuer=issuer, client_id=client_id)
    except Exception as e:
        typer.echo(f"Login failed: {e}")
        raise typer.Exit(1)
    email = result.get("email", result["username"])
    nick = _sanitize_irc_nick(email.split("@")[0] if "@" in email else email)
    result["username"] = nick
    save_token(auth_dir, result)
    typer.echo(f"\nLogged in as: {nick} ({email})")
```

- [ ] **Step 2: Verify auth login still works (manual)**

Run: `uv run python -m zchat.cli auth login --help`

Expected: Shows `--method` and `--username` options

- [ ] **Step 3: Commit**

```bash
git add zchat/cli/app.py
git commit -m "feat(auth): add --method local --username to auth login"
```

### Task 3: Remove `$USER` fallback from project.py

**Files:**
- Modify: `zchat/cli/project.py:128-129`
- Test: `tests/unit/test_project.py`

- [ ] **Step 1: Remove the $USER fallback**

In `zchat/cli/project.py`, delete these two lines (128-129) from `load_project_config()`:

```python
    if not agents.get("username"):
        agents["username"] = os.environ.get("USER", "user")
```

Keep the surrounding code intact. The `agents` dict will now have `username = ""` if not set in config.toml.

- [ ] **Step 2: Run existing unit tests to check for breakage**

Run: `uv run pytest tests/unit/test_project.py -v`

Expected: All pass (existing tests don't depend on the $USER fallback for agent name resolution)

- [ ] **Step 3: Commit**

```bash
git add zchat/cli/project.py
git commit -m "fix(project): remove \$USER fallback for agents.username"
```

### Task 4: Wire `get_username()` into `_get_agent_manager()` and `cmd_project_remove()`

**Files:**
- Modify: `zchat/cli/app.py:68-83` and `zchat/cli/app.py:280-299`

- [ ] **Step 1: Update `_get_agent_manager()`**

In `zchat/cli/app.py`, add import at the top of the function and change line 76:

```python
def _get_agent_manager(ctx: typer.Context) -> AgentManager:
    from zchat.cli.auth import get_username
    cfg = _get_config(ctx)
    project_name = ctx.obj["project"]
    return AgentManager(
        irc_server=cfg["irc"]["server"],
        irc_port=cfg["irc"]["port"],
        irc_tls=cfg["irc"].get("tls", False),
        irc_password=cfg["irc"].get("password", ""),
        username=get_username(),
        default_channels=cfg["agents"]["default_channels"],
        env_file=cfg["agents"].get("env_file", ""),
        default_type=cfg["agents"].get("default_type", "claude"),
        tmux_session=_get_tmux_session(ctx),
        state_file=state_file_path(project_name),
        project_dir=project_dir(project_name),
    )
```

- [ ] **Step 2: Update `cmd_project_remove()`**

In `zchat/cli/app.py`, change the AgentManager construction in `cmd_project_remove()` (around line 284):

```python
    try:
        from zchat.cli.auth import get_username
        cfg = load_project_config(name)
        mgr = AgentManager(
            irc_server=cfg["irc"]["server"], irc_port=cfg["irc"]["port"],
            irc_tls=cfg["irc"].get("tls", False),
            irc_password=cfg["irc"].get("password", ""),
            username=get_username(),
            default_channels=cfg["agents"]["default_channels"],
            state_file=state_file_path(name),
        )
```

- [ ] **Step 3: Commit**

```bash
git add zchat/cli/app.py
git commit -m "fix(app): use get_username() in agent manager and project remove"
```

### Task 5: Fix `irc_manager.py` — remove SASL nick override, use `get_username()`

**Files:**
- Modify: `zchat/cli/irc_manager.py:198,216,297`

- [ ] **Step 1: Fix `start_weechat()` nick resolution (line 198)**

Change:
```python
nick = nick_override or self.config.get("agents", {}).get("username") or os.environ.get("USER", "user")
```
To:
```python
from zchat.cli.auth import get_username
nick = nick_override or get_username()
```

- [ ] **Step 2: Delete the SASL nick override (line 216)**

Delete this single line:
```python
            nick = sasl_user
```

Keep the surrounding `sasl_cmds` code intact — SASL user/pass must still be configured for WeeChat authentication.

After the change, the SASL block should look like:
```python
        sasl_cmds = ""
        from zchat.cli.auth import get_credentials
        creds = get_credentials()
        if creds:
            sasl_user, sasl_pass = creds
            sasl_cmds = (
                f"; /set irc.server.{srv_name}.sasl_mechanism PLAIN"
                f"; /set irc.server.{srv_name}.sasl_username {sasl_user}"
                f"; /set irc.server.{srv_name}.sasl_password {sasl_pass}"
            )
```

- [ ] **Step 3: Fix `status()` nick source (line 297)**

Change:
```python
"nick": self.config.get("agents", {}).get("username"),
```
To:
```python
"nick": get_username(),
```

(Add `from zchat.cli.auth import get_username` at the top of `status()` if not already imported.)

- [ ] **Step 4: Commit**

```bash
git add zchat/cli/irc_manager.py
git commit -m "fix(irc): use get_username(), remove SASL nick override in WeeChat"
```

### Task 6: Handle `get_username()` error in `cmd_project_remove()`

**Files:**
- Modify: `zchat/cli/app.py:282-297`

`cmd_project_remove()` calls `get_username()` which raises `RuntimeError` when auth is not configured. This should be caught alongside the existing `FileNotFoundError`:

- [ ] **Step 1: Wrap the try block to also catch RuntimeError**

Change the existing `try/except FileNotFoundError` block to:

```python
    try:
        from zchat.cli.auth import get_username
        cfg = load_project_config(name)
        mgr = AgentManager(
            irc_server=cfg["irc"]["server"], irc_port=cfg["irc"]["port"],
            irc_tls=cfg["irc"].get("tls", False),
            irc_password=cfg["irc"].get("password", ""),
            username=get_username(),
            default_channels=cfg["agents"]["default_channels"],
            state_file=state_file_path(name),
        )
        running = [n for n, i in mgr.list_agents().items() if i["status"] == "running"]
        if running:
            typer.echo(f"Error: Running agents: {', '.join(running)}. Stop them first.")
            raise typer.Exit(1)
    except (FileNotFoundError, RuntimeError):
        pass
```

- [ ] **Step 2: Commit**

```bash
git add zchat/cli/app.py
git commit -m "fix(app): catch RuntimeError from get_username() in project remove"
```

### Task 7: Run unit tests

- [ ] **Step 1: Run all unit tests**

Run: `uv run pytest tests/unit/ -v`

Expected: All pass

- [ ] **Step 2: Fix any failures, commit if needed**

## Chunk 2: Test Infrastructure & Marketplace

### Task 8: Update E2E test fixtures — write auth.json instead of config.toml username

**Files:**
- Modify: `tests/e2e/conftest.py:62-89`

- [ ] **Step 1: Add auth.json setup to `e2e_context` fixture**

In `tests/e2e/conftest.py`, in the `e2e_context` fixture, after `os.makedirs(project_dir)` (line 67), add:

```python
    # Write auth.json with username "alice" for get_username()
    import json
    auth_json = os.path.join(home, "auth.json")
    with open(auth_json, "w") as f:
        json.dump({"username": "alice"}, f)
```

Keep the existing `username = "alice"` in config.toml for backward compat (it's ignored but doesn't hurt).

- [ ] **Step 2: Run E2E tests**

Run: `uv run pytest tests/e2e/ -v -m e2e`

Expected: All 9 pass (including alice-bob test from prior work)

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/conftest.py
git commit -m "fix(e2e): write auth.json for get_username() in E2E fixtures"
```

### Task 9: Update pre-release test fixtures

**Files:**
- Modify: `tests/pre_release/conftest.py`

- [ ] **Step 1: Add auth setup to pre-release `project` fixture**

In `tests/pre_release/conftest.py`, in the `project` fixture (after `cli("set", "tmux.session", tmux_session)` at line 91), add:

```python
    # Set up local auth for get_username()
    cli("auth", "login", "--method", "local", "--username", os.environ.get("USER", "test"))
```

This uses the new `--method local` login to set username before agent tests run.

- [ ] **Step 2: Commit**

```bash
git add tests/pre_release/conftest.py
git commit -m "fix(pre-release): add local auth login to test fixtures"
```

### Task 10: Add marketplace submodule and update marketplace.json

**Files:**
- Create: `ezagent42-marketplace/` (git submodule)
- Modify: `ezagent42-marketplace/.claude-plugin/marketplace.json`

- [ ] **Step 1: Add the marketplace as a git submodule**

```bash
git submodule add https://github.com/ezagent42/ezagent42.git ezagent42-marketplace
```

- [ ] **Step 2: Read current marketplace.json**

Read: `ezagent42-marketplace/.claude-plugin/marketplace.json`

- [ ] **Step 3: Add zchat plugin entry to marketplace.json**

Add the zchat entry alongside the existing feishu entry:

```json
{
  "plugins": {
    "feishu": { ... existing ... },
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

- [ ] **Step 4: Commit marketplace changes in the submodule**

```bash
cd ezagent42-marketplace
git add .claude-plugin/marketplace.json
git commit -m "feat: add zchat plugin to marketplace"
git push origin master
cd ..
```

- [ ] **Step 5: Commit submodule reference in parent repo**

```bash
git add ezagent42-marketplace .gitmodules
git commit -m "feat: add ezagent42 marketplace as git submodule"
```

### Task 11: Full test verification

- [ ] **Step 1: Run unit tests**

Run: `uv run pytest tests/unit/ -v`

Expected: All pass

- [ ] **Step 2: Run E2E tests**

Run: `uv run pytest tests/e2e/ -v -m e2e`

Expected: All 9 pass

- [ ] **Step 3: Build and install to Homebrew for pre-release testing**

```bash
rm -f dist/*.whl dist/*.tar.gz
uv build
/opt/homebrew/Cellar/zchat/56/libexec/bin/python -m pip install \
  --force-reinstall --no-deps --upgrade \
  --target /opt/homebrew/Cellar/zchat/56/libexec/lib/python3.14/site-packages \
  dist/*.whl
```

- [ ] **Step 4: Run pre-release tests**

Run: `uv run pytest tests/pre_release/ -v -m "prerelease and not manual" --timeout=300 -p pytest_order --order-scope=module`

Expected: 33/33 pass (or 32/33 with known flaky test_agent_send)

- [ ] **Step 5: Final commit if any fixes needed**
