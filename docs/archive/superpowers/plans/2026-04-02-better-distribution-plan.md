# Better Distribution Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace PyPI+Homebrew with a `curl | bash` installer using uv, and add update/upgrade commands with background version checking.

**Architecture:** Install script bootstraps Homebrew (system deps) + uv (Python deps), then `uv tool install` for zchat and zchat-channel-server in isolated venvs. Background check runs once daily via fork in the CLI callback; actual upgrade is user-initiated via `zchat upgrade`. Global config in `~/.zchat/config.toml` manages update channel (main/dev/release).

**Tech Stack:** Bash (install script), Python/Typer (CLI), uv (package management), git ls-remote + PyPI JSON API (version checking)

---

## Chunk 1: Update/Upgrade Core

### Task 1: Create `zchat/cli/update.py` — version checking logic

**Files:**
- Create: `zchat/cli/update.py`
- Create: `tests/unit/test_update.py`

This module handles reading/writing `update.json`, checking remote versions, and running `uv tool upgrade`.

- [ ] **Step 1: Write failing tests for update.json read/write**

```python
# tests/unit/test_update.py
"""Tests for update module: version checking, state management, upgrade."""
import json
import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


@pytest.fixture
def update_json(tmp_path):
    """Provide a tmp update.json path."""
    return str(tmp_path / "update.json")


def test_load_state_missing_file(update_json):
    from zchat.cli.update import load_update_state
    state = load_update_state(update_json)
    assert state["channel"] == "main"
    assert state["update_available"] is False
    assert state["zchat"]["installed_ref"] == ""
    assert state["channel_server"]["installed_ref"] == ""


def test_save_and_load_state(update_json):
    from zchat.cli.update import load_update_state, save_update_state
    state = load_update_state(update_json)
    state["channel"] = "dev"
    state["zchat"]["installed_ref"] = "abc1234"
    save_update_state(state, update_json)
    reloaded = load_update_state(update_json)
    assert reloaded["channel"] == "dev"
    assert reloaded["zchat"]["installed_ref"] == "abc1234"


def test_should_check_today_no_previous(update_json):
    from zchat.cli.update import load_update_state, should_check_today
    state = load_update_state(update_json)
    assert should_check_today(state) is True


def test_should_check_today_already_checked(update_json):
    from zchat.cli.update import load_update_state, save_update_state, should_check_today
    state = load_update_state(update_json)
    state["last_check"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_update_state(state, update_json)
    reloaded = load_update_state(update_json)
    assert should_check_today(reloaded) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/feat-better-distribution && uv run pytest tests/unit/test_update.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'zchat.cli.update'`

- [ ] **Step 3: Implement update.py — state management**

```python
# zchat/cli/update.py
"""Update checking and upgrade logic."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone, date

from zchat.cli.project import ZCHAT_DIR

UPDATE_STATE_FILE = os.path.join(ZCHAT_DIR, "update.json")

_ZCHAT_REPO = "https://github.com/ezagent42/zchat.git"
_CHANNEL_REPO = "https://github.com/ezagent42/claude-zchat-channel.git"

_DEFAULT_STATE = {
    "last_check": "",
    "channel": "main",
    "zchat": {"installed_ref": "", "remote_ref": ""},
    "channel_server": {"installed_ref": "", "remote_ref": ""},
    "update_available": False,
}


def load_update_state(path: str = UPDATE_STATE_FILE) -> dict:
    """Load update state from JSON file. Returns defaults if missing."""
    if os.path.isfile(path):
        with open(path) as f:
            data = json.load(f)
        # Ensure all keys present
        for key, default in _DEFAULT_STATE.items():
            data.setdefault(key, default if not isinstance(default, dict) else dict(default))
        for pkg in ("zchat", "channel_server"):
            if isinstance(data.get(pkg), dict):
                data[pkg].setdefault("installed_ref", "")
                data[pkg].setdefault("remote_ref", "")
        return data
    return json.loads(json.dumps(_DEFAULT_STATE))  # deep copy


def save_update_state(state: dict, path: str = UPDATE_STATE_FILE) -> None:
    """Save update state to JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def should_check_today(state: dict) -> bool:
    """Return True if no check has been done today."""
    last = state.get("last_check", "")
    if not last:
        return True
    try:
        last_date = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").date()
        return last_date < date.today()
    except ValueError:
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/feat-better-distribution && uv run pytest tests/unit/test_update.py -v`
Expected: 4 PASS

- [ ] **Step 5: Add tests for remote version checking**

```python
# append to tests/unit/test_update.py

import subprocess


def test_check_remote_git_success():
    from zchat.cli.update import _check_remote_git
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="abc1234def5678901234567890abcdef01234567\trefs/heads/main\n"
        )
        ref = _check_remote_git("https://github.com/test/repo.git", "main")
        assert ref == "abc1234"


def test_check_remote_git_timeout():
    from zchat.cli.update import _check_remote_git
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5)):
        ref = _check_remote_git("https://github.com/test/repo.git", "main")
        assert ref is None


def test_check_remote_pypi_success():
    from zchat.cli.update import _check_remote_pypi
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"info": {"version": "0.4.0"}}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_response):
        ver = _check_remote_pypi("zchat")
        assert ver == "0.4.0"


def test_check_remote_pypi_failure():
    from zchat.cli.update import _check_remote_pypi
    with patch("urllib.request.urlopen", side_effect=Exception("network")):
        ver = _check_remote_pypi("zchat")
        assert ver is None
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/feat-better-distribution && uv run pytest tests/unit/test_update.py -v`
Expected: FAIL — `_check_remote_git` not found

- [ ] **Step 7: Implement remote version checking**

Add to `zchat/cli/update.py`:

```python
import urllib.request


def _check_remote_git(repo_url: str, branch: str) -> str | None:
    """Get latest commit hash (7 chars) from a git remote. Returns None on failure."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", repo_url, f"refs/heads/{branch}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split()[0][:7]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _check_remote_pypi(package: str) -> str | None:
    """Get latest version from PyPI. Returns None on failure."""
    try:
        url = f"https://pypi.org/pypi/{package}/json"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data["info"]["version"]
    except Exception:
        return None


def check_for_updates(state: dict) -> dict:
    """Check remote versions and update state. Does not download anything."""
    channel = state["channel"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state["last_check"] = now

    if channel in ("main", "dev"):
        zchat_ref = _check_remote_git(_ZCHAT_REPO, channel)
        channel_ref = _check_remote_git(_CHANNEL_REPO, channel)
        if zchat_ref:
            state["zchat"]["remote_ref"] = zchat_ref
        if channel_ref:
            state["channel_server"]["remote_ref"] = channel_ref
    elif channel == "release":
        zchat_ver = _check_remote_pypi("zchat")
        channel_ver = _check_remote_pypi("zchat-channel-server")
        if zchat_ver:
            state["zchat"]["remote_ref"] = zchat_ver
        if channel_ver:
            state["channel_server"]["remote_ref"] = channel_ver

    # Determine if update is available.
    # If installed_ref is empty (fresh install), set it to remote_ref — no update needed.
    for pkg in ("zchat", "channel_server"):
        if not state[pkg]["installed_ref"] and state[pkg]["remote_ref"]:
            state[pkg]["installed_ref"] = state[pkg]["remote_ref"]

    state["update_available"] = (
        (state["zchat"]["remote_ref"] != "" and
         state["zchat"]["remote_ref"] != state["zchat"]["installed_ref"])
        or
        (state["channel_server"]["remote_ref"] != "" and
         state["channel_server"]["remote_ref"] != state["channel_server"]["installed_ref"])
    )
    return state
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/feat-better-distribution && uv run pytest tests/unit/test_update.py -v`
Expected: 8 PASS

- [ ] **Step 9: Add tests for upgrade logic**

```python
# append to tests/unit/test_update.py

def test_build_install_args_main():
    from zchat.cli.update import _build_install_args
    args = _build_install_args("main")
    assert any("git+" in a and "@main" in a for a in args)
    assert len(args) == 2  # zchat + channel-server


def test_build_install_args_release():
    from zchat.cli.update import _build_install_args
    args = _build_install_args("release")
    assert args == ["zchat", "zchat-channel-server"]


def test_run_upgrade_success():
    from zchat.cli.update import run_upgrade
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ok = run_upgrade("main")
        assert ok is True
        # Should call uv tool install --force
        call_args = mock_run.call_args[0][0]
        assert "uv" in call_args
        assert "--force" in call_args
```

- [ ] **Step 10: Run tests to verify they fail, then implement**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/feat-better-distribution && uv run pytest tests/unit/test_update.py::test_build_install_args_main -v`
Expected: FAIL

Add to `zchat/cli/update.py`:

```python
def _build_install_args(channel: str) -> list[str]:
    """Build uv tool install package specs for the given channel."""
    if channel in ("main", "dev"):
        return [
            f"zchat @ git+{_ZCHAT_REPO}@{channel}",
            f"zchat-channel-server @ git+{_CHANNEL_REPO}@{channel}",
        ]
    else:  # release
        return ["zchat", "zchat-channel-server"]


def run_upgrade(channel: str) -> bool:
    """Run uv tool install --force for both packages. Returns True on success.

    Treats the two-package upgrade as atomic: if the second fails, rolls
    back the first by re-installing from the previous channel/ref.
    """
    specs = _build_install_args(channel)
    installed: list[str] = []
    for spec in specs:
        result = subprocess.run(
            ["uv", "tool", "install", "--force", spec],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            # Rollback previously installed packages
            state = load_update_state()
            old_channel = state.get("channel", channel)
            old_specs = _build_install_args(old_channel)
            for old_spec in old_specs[:len(installed)]:
                subprocess.run(
                    ["uv", "tool", "install", "--force", old_spec],
                    capture_output=True, text=True,
                )
            return False
        installed.append(spec)
    return True


def _background_check_main() -> None:
    """Entry point for background update check (called via subprocess)."""
    import sys
    auto_upgrade = "--auto-upgrade" in sys.argv
    state = load_update_state()
    state = check_for_updates(state)
    if state.get("update_available") and auto_upgrade:
        ok = run_upgrade(state["channel"])
        if ok:
            state["zchat"]["installed_ref"] = state["zchat"]["remote_ref"]
            state["channel_server"]["installed_ref"] = state["channel_server"]["remote_ref"]
            state["update_available"] = False
    save_update_state(state)


if __name__ == "__main__":
    _background_check_main()
```

- [ ] **Step 11: Run all update tests**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/feat-better-distribution && uv run pytest tests/unit/test_update.py -v`
Expected: 11 PASS

- [ ] **Step 12: Commit**

```bash
git add zchat/cli/update.py tests/unit/test_update.py
git commit -m "feat: add update module with version checking and upgrade logic"
```

---

### Task 2: Create `zchat/cli/config_cmd.py` — global config management

**Files:**
- Create: `zchat/cli/config_cmd.py`
- Create: `tests/unit/test_config_cmd.py`

Global config lives at `~/.zchat/config.toml`. Distinct from per-project config in `project.py`.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_config_cmd.py
"""Tests for global config management."""
import os
import pytest


@pytest.fixture
def config_toml(tmp_path, monkeypatch):
    """Point ZCHAT_DIR to tmp for isolated config."""
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
    # Also patch the module-level ZCHAT_DIR
    import zchat.cli.project as proj
    monkeypatch.setattr(proj, "ZCHAT_DIR", str(tmp_path))
    import zchat.cli.config_cmd as cfg
    monkeypatch.setattr(cfg, "_GLOBAL_CONFIG", str(tmp_path / "config.toml"))
    return str(tmp_path / "config.toml")


def test_load_default_config(config_toml):
    from zchat.cli.config_cmd import load_global_config
    cfg = load_global_config(config_toml)
    assert cfg["update"]["channel"] == "main"
    assert cfg["update"]["auto_upgrade"] is True


def test_set_and_get(config_toml):
    from zchat.cli.config_cmd import load_global_config, save_global_config, set_config_value, get_config_value
    cfg = load_global_config(config_toml)
    set_config_value(cfg, "update.channel", "release")
    save_global_config(cfg, config_toml)
    cfg2 = load_global_config(config_toml)
    assert get_config_value(cfg2, "update.channel") == "release"


def test_set_bool_value(config_toml):
    from zchat.cli.config_cmd import load_global_config, set_config_value, get_config_value
    cfg = load_global_config(config_toml)
    set_config_value(cfg, "update.auto_upgrade", "false")
    assert get_config_value(cfg, "update.auto_upgrade") is False


def test_get_invalid_key(config_toml):
    from zchat.cli.config_cmd import load_global_config, get_config_value
    cfg = load_global_config(config_toml)
    assert get_config_value(cfg, "nonexistent.key") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/feat-better-distribution && uv run pytest tests/unit/test_config_cmd.py -v`
Expected: FAIL

- [ ] **Step 3: Implement config_cmd.py**

```python
# zchat/cli/config_cmd.py
"""Global configuration management (~/.zchat/config.toml)."""
from __future__ import annotations

import os
import tomllib
import tomli_w

from zchat.cli.project import ZCHAT_DIR

_GLOBAL_CONFIG = os.path.join(ZCHAT_DIR, "config.toml")

_DEFAULTS = {
    "update": {
        "channel": "main",
        "auto_upgrade": True,
    },
}


def load_global_config(path: str = _GLOBAL_CONFIG) -> dict:
    """Load global config, filling defaults for missing keys."""
    data: dict = {}
    if os.path.isfile(path):
        with open(path, "rb") as f:
            data = tomllib.load(f)
    # Fill defaults
    for section, defaults in _DEFAULTS.items():
        data.setdefault(section, {})
        for key, value in defaults.items():
            data[section].setdefault(key, value)
    return data


def save_global_config(config: dict, path: str = _GLOBAL_CONFIG) -> None:
    """Write global config to TOML file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(config, f)


def get_config_value(config: dict, dotted_key: str):
    """Get a value from config by dotted key (e.g. 'update.channel')."""
    parts = dotted_key.split(".")
    node = config
    for part in parts:
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def set_config_value(config: dict, dotted_key: str, value: str) -> None:
    """Set a value in config by dotted key. Auto-converts 'true'/'false' to bool."""
    parts = dotted_key.split(".")
    node = config
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    # Type coercion
    if value.lower() in ("true", "false"):
        node[parts[-1]] = value.lower() == "true"
    else:
        node[parts[-1]] = value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/feat-better-distribution && uv run pytest tests/unit/test_config_cmd.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add zchat/cli/config_cmd.py tests/unit/test_config_cmd.py
git commit -m "feat: add global config management (config.toml)"
```

---

### Task 3: Wire update/upgrade/config commands into app.py

**Files:**
- Modify: `zchat/cli/app.py:22-37` (add config_app typer group)
- Modify: `zchat/cli/app.py:107-126` (add background check in callback)
- Modify: `zchat/cli/app.py:782-820` (replace self-update with update/upgrade)

- [ ] **Step 1: Add config subcommand group and import**

In `zchat/cli/app.py`, add after the existing typer groups (line ~29):

```python
config_app = typer.Typer(help="Global configuration management")
app.add_typer(config_app, name="config")
```

Add imports at top of file (after existing imports):

```python
from zchat.cli.update import (
    load_update_state, save_update_state, should_check_today,
    check_for_updates, run_upgrade, UPDATE_STATE_FILE,
)
from zchat.cli.config_cmd import (
    load_global_config, save_global_config,
    get_config_value, set_config_value,
)
```

- [ ] **Step 2: Add background update check in main callback**

In `zchat/cli/app.py`, inside the `main()` callback function, after the project resolution block (after line ~125), add:

```python
    # Background update check (once per day)
    try:
        global_cfg = load_global_config()
        state = load_update_state()
        if should_check_today(state):
            auto_upgrade = global_cfg["update"]["auto_upgrade"]
            _spawn_update_check(state, auto_upgrade=auto_upgrade)
        elif state.get("update_available") and not global_cfg["update"]["auto_upgrade"]:
            typer.echo("💡 New version available. Run `zchat upgrade` to update.", err=True)
    except Exception:
        pass  # Never block CLI startup
```

Add the fork helper function (before the `main` callback):

```python
def _spawn_update_check(state: dict, auto_upgrade: bool = True) -> None:
    """Spawn a detached background process to check for updates (and optionally upgrade).

    Uses subprocess.Popen instead of os.fork() to avoid deadlocks with
    threaded modules (libtmux, httpx) and to prevent stdout/stderr leakage.
    """
    import sys
    cmd = [sys.executable, "-m", "zchat.cli.update", "--background-check"]
    if auto_upgrade:
        cmd.append("--auto-upgrade")
    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
```

- [ ] **Step 3: Replace self-update with update/upgrade commands**

Remove the entire `self-update` section (lines 782-820). Replace with:

```python
# ============================================================
# update / upgrade
# ============================================================

@app.command("update")
def cmd_update():
    """Check for new versions (does not install)."""
    state = load_update_state()
    typer.echo(f"Channel: {state['channel']}")
    typer.echo("Checking...")
    state = check_for_updates(state)
    save_update_state(state)

    if state["update_available"]:
        typer.echo(f"zchat:          {state['zchat']['installed_ref'] or '?'} → {state['zchat']['remote_ref']}")
        typer.echo(f"channel-server: {state['channel_server']['installed_ref'] or '?'} → {state['channel_server']['remote_ref']}")
        typer.echo("\nRun `zchat upgrade` to install.")
    else:
        typer.echo("Already up to date.")


@app.command("upgrade")
def cmd_upgrade(
    channel: Optional[str] = typer.Option(None, help="Override update channel (main/dev/release)"),
):
    """Download and install the latest version."""
    global_cfg = load_global_config()
    ch = channel or global_cfg["update"]["channel"]

    # Check first
    state = load_update_state()
    state["channel"] = ch
    state = check_for_updates(state)

    if not state["update_available"]:
        typer.echo("Already up to date.")
        save_update_state(state)
        return

    typer.echo(f"Upgrading from channel '{ch}'...")
    ok = run_upgrade(ch)
    if ok:
        # Update installed refs to match remote
        state["zchat"]["installed_ref"] = state["zchat"]["remote_ref"]
        state["channel_server"]["installed_ref"] = state["channel_server"]["remote_ref"]
        state["update_available"] = False
        save_update_state(state)
        typer.echo("Done. Restart any running zchat commands to use the new version.")
    else:
        typer.echo("Error: Upgrade failed. Run `zchat upgrade` to retry.")
        raise typer.Exit(1)
```

- [ ] **Step 4: Add config commands**

```python
# ============================================================
# config
# ============================================================

@config_app.command("get")
def cmd_config_get(key: str):
    """Get a global config value."""
    cfg = load_global_config()
    val = get_config_value(cfg, key)
    if val is None:
        typer.echo(f"Key '{key}' not found.")
        raise typer.Exit(1)
    typer.echo(str(val))


@config_app.command("set")
def cmd_config_set(key: str, value: str):
    """Set a global config value."""
    # Validate known keys
    if key == "update.channel" and value not in ("main", "dev", "release"):
        typer.echo(f"Error: channel must be one of: main, dev, release")
        raise typer.Exit(1)
    cfg = load_global_config()
    set_config_value(cfg, key, value)
    save_global_config(cfg)
    typer.echo(f"{key} = {get_config_value(cfg, key)}")
    # If channel changed, reset update state
    if key == "update.channel":
        state = load_update_state()
        state["channel"] = value
        state["zchat"] = {"installed_ref": "", "remote_ref": ""}
        state["channel_server"] = {"installed_ref": "", "remote_ref": ""}
        state["update_available"] = False
        save_update_state(state)


@config_app.command("list")
def cmd_config_list():
    """Show all global config values."""
    cfg = load_global_config()
    for section, values in cfg.items():
        if isinstance(values, dict):
            for k, v in values.items():
                typer.echo(f"{section}.{k} = {v}")
```

- [ ] **Step 5: Run all unit tests to ensure nothing broke**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/feat-better-distribution && uv run pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add zchat/cli/app.py
git commit -m "feat: wire update/upgrade/config commands, add background update check"
```

---

## Chunk 2: start.sh Fix + Doctor Enhancement

### Task 4: Fix start.sh cross-venv package resolution

**Files:**
- Modify: `zchat/cli/agent_manager.py:144-178`
- Modify: `zchat/cli/templates/claude/start.sh:9-16`
- Modify: `zchat/cli/templates/claude/.env.example`
- Modify: `tests/unit/test_agent_manager.py`

- [ ] **Step 1: Add test for _find_channel_pkg_dir**

```python
# append to tests/unit/test_agent_manager.py (or create new section)

def test_find_channel_pkg_dir_via_uv(tmp_path):
    """_find_channel_pkg_dir locates package via uv tool dir."""
    from unittest.mock import patch, MagicMock
    import zchat.cli.agent_manager as am

    # Create fake uv tool venv structure
    pkg_dir = tmp_path / "zchat-channel-server" / "lib" / "python3.11" / "site-packages" / "zchat_channel_server"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "server.py").touch()
    (pkg_dir / ".claude-plugin").mkdir()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=str(tmp_path) + "\n")
        result = am._find_channel_pkg_dir()
        assert result is not None
        assert "zchat_channel_server" in result


def test_find_channel_pkg_dir_no_uv(tmp_path):
    """Falls back to None when uv is not available."""
    from unittest.mock import patch, MagicMock
    import zchat.cli.agent_manager as am

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = am._find_channel_pkg_dir()
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/feat-better-distribution && uv run pytest tests/unit/test_agent_manager.py::test_find_channel_pkg_dir_via_uv -v`
Expected: FAIL

- [ ] **Step 3: Add _find_channel_pkg_dir to agent_manager.py**

Add at module level in `zchat/cli/agent_manager.py` (after imports):

```python
import glob as _glob
import subprocess as _sp


def _find_channel_pkg_dir() -> str | None:
    """Locate zchat-channel-server package dir in its uv tool venv."""
    result = _sp.run(["uv", "tool", "dir"], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    tool_dir = result.stdout.strip()
    patterns = _glob.glob(
        os.path.join(tool_dir, "zchat-channel-server", "lib", "python*",
                     "site-packages", "zchat_channel_server")
    )
    return patterns[0] if patterns else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/feat-better-distribution && uv run pytest tests/unit/test_agent_manager.py::test_find_channel_pkg_dir_via_uv tests/unit/test_agent_manager.py::test_find_channel_pkg_dir_no_uv -v`
Expected: 2 PASS

- [ ] **Step 5: Wire _find_channel_pkg_dir into _build_env_context**

In `agent_manager.py:_build_env_context()` (around line 144), add `CHANNEL_PKG_DIR` to the context:

```python
        # After building the context dict, add channel pkg dir
        channel_pkg = _find_channel_pkg_dir()
        if channel_pkg:
            context["channel_pkg_dir"] = channel_pkg
        else:
            context["channel_pkg_dir"] = ""
```

- [ ] **Step 6: Add CHANNEL_PKG_DIR to .env.example**

Add to `zchat/cli/templates/claude/.env.example`:

```
# Channel server package directory (resolved by zchat agent create)
CHANNEL_PKG_DIR={{channel_pkg_dir}}
```

- [ ] **Step 7: Update start.sh to use CHANNEL_PKG_DIR**

Replace lines 9-16 of `zchat/cli/templates/claude/start.sh`:

```bash
# --- Locate channel server plugin ---
# CHANNEL_PKG_DIR is set by zchat agent create (resolves via uv tool dir)
# Fallback to importlib.metadata for non-uv installs (editable dev mode)
if [ -z "${CHANNEL_PKG_DIR:-}" ]; then
  CHANNEL_PKG_DIR=$(python3 -c "
from importlib.metadata import files
for f in files('zchat-channel-server'):
    if f.name == 'server.py':
        print(f.locate().parent)
        break
" 2>/dev/null || echo "")
fi
```

Also update the copy section (originally lines 18-23) to use the new variable name `$CHANNEL_PKG_DIR` instead of the old `$CHANNEL_PKG`:

```bash
if [ -n "$CHANNEL_PKG_DIR" ] && [ -d "$CHANNEL_PKG_DIR/.claude-plugin" ]; then
  rm -rf .claude-plugin commands
  cp -r "$CHANNEL_PKG_DIR/.claude-plugin" .claude-plugin
  cp -r "$CHANNEL_PKG_DIR/commands" commands
fi
```

Note: We keep the `python3` fallback for developers running in editable mode without uv tool install. The env var takes priority.

- [ ] **Step 8: Run full unit tests**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/feat-better-distribution && uv run pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add zchat/cli/agent_manager.py zchat/cli/templates/claude/start.sh zchat/cli/templates/claude/.env.example tests/unit/test_agent_manager.py
git commit -m "feat: resolve channel-server pkg via uv tool dir, fix cross-venv issue"
```

---

### Task 5: Enhance doctor.py with new checks

**Files:**
- Modify: `zchat/cli/doctor.py:40-46, 70-78`

- [ ] **Step 1: Add uv, Python, tmuxp, and update status checks**

In `doctor.py`, update `_VERSION_CMDS`:

```python
_VERSION_CMDS = {
    "uv": ["--version"],       # "uv 0.6.x"
    "python3": ["--version"],  # "Python 3.11.x"
    "tmux": ["-V"],            # "tmux 3.6a"
    "tmuxp": ["--version"],    # "tmuxp, version 1.x.x"
    "claude": ["--version"],   # "2.1.86 (Claude Code)"
    "zchat-channel": None,     # MCP server, no --version
    "ergo": ["--version"],     # "ergo-2.18.0"
    "weechat": ["--version"],  # "4.8.2"
}
```

Update `run_doctor()` checks list:

```python
def run_doctor():
    """Check all dependencies and report status."""
    checks = [
        ("uv", True, "curl -LsSf https://astral.sh/uv/install.sh | sh"),
        ("python3", True, "uv python install 3.11"),
        ("tmux", True, "brew install tmux"),
        ("tmuxp", True, "uv tool install tmuxp"),
        ("claude", True, "https://docs.anthropic.com/en/docs/claude-code"),
        ("zchat-channel", True, "uv tool install zchat-channel-server"),
        ("ergo", False, "brew install ezagent42/zchat/ergo"),
        ("weechat", False, "brew install weechat"),
    ]
```

After the existing checks and project info, add update status:

```python
    # Update status
    try:
        from zchat.cli.update import load_update_state
        state = load_update_state()
        if state.get("update_available"):
            typer.echo(f"  💡 Update available — run: zchat upgrade")
        elif state.get("last_check"):
            typer.echo(f"  ✓ Up to date (checked: {state['last_check'][:10]})")
    except Exception:
        pass
```

- [ ] **Step 2: Run all unit tests**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/feat-better-distribution && uv run pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add zchat/cli/doctor.py
git commit -m "feat: enhance doctor with uv/tmuxp/update status checks"
```

---

## Chunk 3: Install Script + Pre-release Test Update

### Task 6: Create install.sh

**Files:**
- Create: `install.sh`

- [ ] **Step 1: Write install.sh**

```bash
#!/bin/bash
set -euo pipefail

# zchat installer — bootstraps all dependencies and installs zchat
# Usage: curl -fsSL https://raw.githubusercontent.com/ezagent42/zchat/main/install.sh | bash
#        curl ... | bash -s -- --channel release

CHANNEL="main"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --channel) CHANNEL="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

info()  { echo "==> $*"; }
warn()  { echo "WARNING: $*" >&2; }
error() { echo "ERROR: $*" >&2; exit 1; }

# ---- 1. Detect OS ----
OS="$(uname -s)"
case "$OS" in
  Darwin) PLATFORM="macos" ;;
  Linux)  PLATFORM="linux" ;;
  *)      error "Unsupported OS: $OS" ;;
esac
info "Detected platform: $PLATFORM"

# ---- 2. System dependencies via Homebrew ----
NEED_BREW=false
for cmd in tmux weechat; do
  if ! command -v "$cmd" &>/dev/null; then
    NEED_BREW=true
    break
  fi
done

# ergo always from tap
if ! command -v ergo &>/dev/null; then
  NEED_BREW=true
fi

if [ "$NEED_BREW" = true ]; then
  if ! command -v brew &>/dev/null; then
    info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add brew to PATH for this session
    if [ "$PLATFORM" = "linux" ]; then
      eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv 2>/dev/null || true)"
    fi
  fi

  info "Installing system dependencies via Homebrew..."
  brew tap ezagent42/zchat 2>/dev/null || true

  for pkg in tmux weechat; do
    if ! command -v "$pkg" &>/dev/null; then
      info "  Installing $pkg..."
      brew install "$pkg"
    else
      info "  $pkg already installed, skipping"
    fi
  done

  if ! command -v ergo &>/dev/null; then
    info "  Installing ergo..."
    brew install ezagent42/zchat/ergo
  else
    info "  ergo already installed, skipping"
  fi
fi

# ---- 3. Install uv ----
if ! command -v uv &>/dev/null; then
  info "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
info "uv: $(uv --version)"

# ---- 4. Ensure Python 3.11+ ----
PYTHON_OK=false
if command -v python3 &>/dev/null; then
  PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
  if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 11 ]; then
    PYTHON_OK=true
  fi
fi

if [ "$PYTHON_OK" = false ]; then
  info "Installing Python 3.11 via uv..."
  uv python install 3.11
fi

# ---- 5. Install zchat + channel-server ----
info "Installing zchat (channel: $CHANNEL)..."

case "$CHANNEL" in
  main|dev)
    uv tool install --force \
      "zchat @ git+https://github.com/ezagent42/zchat.git@${CHANNEL}"
    uv tool install --force \
      "zchat-channel-server @ git+https://github.com/ezagent42/claude-zchat-channel.git@${CHANNEL}"
    ;;
  release)
    uv tool install --force zchat
    uv tool install --force zchat-channel-server
    ;;
  *)
    error "Unknown channel: $CHANNEL (expected: main, dev, release)"
    ;;
esac

# ---- 6. Install tmuxp ----
if ! command -v tmuxp &>/dev/null; then
  info "Installing tmuxp..."
  uv tool install tmuxp
fi

# ---- 7. Check Claude CLI ----
if ! command -v claude &>/dev/null; then
  warn "Claude Code CLI not found."
  echo "  Install it from: https://docs.anthropic.com/en/docs/claude-code"
  echo "  zchat agents require Claude Code to run."
fi

# ---- 8. Write initial update state ----
ZCHAT_DIR="${ZCHAT_HOME:-$HOME/.zchat}"
mkdir -p "$ZCHAT_DIR"

# Save channel to global config
if [ ! -f "$ZCHAT_DIR/config.toml" ]; then
  cat > "$ZCHAT_DIR/config.toml" <<TOML
[update]
channel = "$CHANNEL"
auto_upgrade = true
TOML
fi

# ---- 9. Initialize update state ----
# Run zchat update to set initial installed refs (prevents false "update available")
info "Initializing update state..."
zchat update >/dev/null 2>&1 || true

# ---- 10. Verify ----
info "Verifying installation..."
echo ""
zchat doctor || true
echo ""

info "Installation complete!"
echo ""
echo "Quick start:"
echo "  zchat project create local"
echo "  zchat irc daemon start"
echo "  zchat irc start"
echo "  zchat agent create agent0"
echo ""
echo "Update channel: $CHANNEL"
echo "  Change with: zchat config set update.channel <main|dev|release>"
echo "  Upgrade:     zchat upgrade"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x install.sh
```

- [ ] **Step 3: Commit**

```bash
git add install.sh
git commit -m "feat: add curl|bash install script with Homebrew + uv bootstrapping"
```

---

### Task 7: Update pre-release test

**Files:**
- Modify: `tests/pre_release/test_07_self_update.py`

- [ ] **Step 1: Update test to use upgrade command**

```python
# tests/pre_release/test_07_self_update.py
"""Pre-release: update/upgrade commands."""
import pytest


@pytest.mark.manual
@pytest.mark.order(1)
def test_update_check(cli):
    """update command checks for new versions."""
    result = cli("update", check=False)
    assert isinstance(result.returncode, int)


@pytest.mark.manual
@pytest.mark.order(2)
def test_upgrade(cli):
    """upgrade command is callable."""
    result = cli("upgrade", check=False)
    assert isinstance(result.returncode, int)


@pytest.mark.manual
@pytest.mark.order(3)
def test_config_list(cli):
    """config list shows update settings."""
    result = cli("config", "list", check=False)
    assert "update.channel" in result.stdout
```

- [ ] **Step 2: Commit**

```bash
git add tests/pre_release/test_07_self_update.py
git commit -m "test: update pre-release tests for upgrade/config commands"
```

---

### Task 8: Run full test suite and E2E validation

**Files:** None (validation only)

- [ ] **Step 1: Run unit tests**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/feat-better-distribution && uv run pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 2: Run E2E tests**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/feat-better-distribution && uv run pytest tests/e2e/ -v -m e2e`
Expected: All PASS (these should not be affected by our changes)

- [ ] **Step 3: Manual smoke test of new commands**

```bash
# Test update
zchat update

# Test config
zchat config list
zchat config set update.channel dev
zchat config get update.channel

# Test upgrade (dry run — will actually upgrade if changes exist)
zchat upgrade --channel main

# Test doctor shows new checks
zchat doctor
```

- [ ] **Step 4: Verify install.sh syntax**

```bash
bash -n install.sh  # syntax check only, does not execute
```
