# Zellij Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate zchat from tmux/libtmux to Zellij, introduce global config (servers/runners), runner/agent separation, and build a WASM hub plugin.

**Architecture:** Four phases — (1) core agent lifecycle via Zellij + concept model, (2) WeeChat/layout/startup, (3) WASM plugin, (4) cleanup. Each phase delivers testable increments.

**Tech Stack:** Python 3.11+, Zellij ≥ 0.44.0, Rust/WASM (plugin), KDL (layouts/config), typer (CLI)

**Design Doc:** `docs/plans/2026-04-06-zellij-migration-design.md`

**Zellij Reference:** `.claude/skills/zellij/SKILL.md` — read this before any Zellij CLI work.

---

## Phase 1: Core — Agent Lifecycle + Concept Model

### Task 1: Global Config Schema

**Files:**
- Modify: `zchat/cli/config_cmd.py:20-61`
- Test: `tests/unit/test_config_cmd.py`

**Context:** Currently `config_cmd.py` only supports flat `[update]` section. We need nested `[servers.X]` and `[runners.X]` sections.

**Step 1: Write failing tests**

```python
# tests/unit/test_config_cmd.py — add these tests

def test_set_nested_server_config(tmp_path):
    config_path = tmp_path / "config.toml"
    config = load_global_config(config_path)
    set_config_value(config, "servers.local.host", "127.0.0.1")
    set_config_value(config, "servers.local.port", 6667)
    set_config_value(config, "servers.local.tls", False)
    save_global_config(config, config_path)

    reloaded = load_global_config(config_path)
    assert reloaded["servers"]["local"]["host"] == "127.0.0.1"
    assert reloaded["servers"]["local"]["port"] == 6667
    assert reloaded["servers"]["local"]["tls"] is False


def test_set_runner_config(tmp_path):
    config_path = tmp_path / "config.toml"
    config = load_global_config(config_path)
    set_config_value(config, "runners.claude-channel.command", "claude")
    set_config_value(
        config,
        "runners.claude-channel.args",
        ["--permission-mode", "bypassPermissions"],
    )
    save_global_config(config, config_path)

    reloaded = load_global_config(config_path)
    assert reloaded["runners"]["claude-channel"]["command"] == "claude"
    assert len(reloaded["runners"]["claude-channel"]["args"]) == 2


def test_defaults_include_servers_and_runners(tmp_path):
    config_path = tmp_path / "config.toml"
    config = load_global_config(config_path)
    assert "servers" in config or config.get("servers") is None  # empty is OK
    assert "runners" in config or config.get("runners") is None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_config_cmd.py -v -k "nested_server or runner_config or defaults_include"`
Expected: FAIL — `set_config_value` doesn't handle nested keys with 3+ segments or list values.

**Step 3: Update `config_cmd.py`**

Update `_DEFAULTS` (line 20) to include empty servers/runners sections. Update `set_config_value` (line 52) to handle deeply nested dotted keys and non-string values (lists, bools, ints). The current implementation only handles 2-level keys.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_config_cmd.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add zchat/cli/config_cmd.py tests/unit/test_config_cmd.py
git commit -m "feat: support nested global config (servers/runners)"
```

---

### Task 2: Project Config Simplification

**Files:**
- Modify: `zchat/cli/project.py:22-79`
- Test: `tests/unit/test_project.py`

**Context:** `create_project_config` currently generates `[irc]` + `[tmux]` + `[agents]` sections plus `tmuxp.yaml` and `bootstrap.sh`. New schema: `server = "local"` (reference), `default_runner`, `[zellij]`.

**Step 1: Write failing tests**

```python
# tests/unit/test_project.py — add/modify these tests

def test_create_project_config_new_schema(tmp_path):
    """New config uses server reference, default_runner, and [zellij] section."""
    create_project_config(
        name="testproj",
        server="local",
        port=6667,
        tls=False,
        password="",
        nick="alice",
        channels=["#general"],
        env_file="",
        default_type="claude-channel",
        base_dir=str(tmp_path),
    )
    config_path = tmp_path / "testproj" / "config.toml"
    assert config_path.exists()
    import tomllib
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)
    assert cfg["server"] == "local"
    assert cfg["default_runner"] == "claude-channel"
    assert "zellij" in cfg
    assert cfg["zellij"]["session"].startswith("zchat-")
    # Old sections should NOT exist
    assert "tmux" not in cfg
    assert "irc" not in cfg  # server details are in global config now


def test_create_project_generates_no_tmuxp_yaml(tmp_path):
    """No tmuxp.yaml should be generated."""
    create_project_config(
        name="testproj", server="local", port=6667, tls=False,
        password="", nick="alice", channels=["#general"],
        env_file="", default_type="claude-channel", base_dir=str(tmp_path),
    )
    assert not (tmp_path / "testproj" / "tmuxp.yaml").exists()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_project.py -v -k "new_schema or no_tmuxp"`
Expected: FAIL — current config still writes `[tmux]` and generates `tmuxp.yaml`.

**Step 3: Rewrite `create_project_config`**

In `project.py`, refactor:
- Line 16-19: rename `_generate_tmux_session_name` → `_generate_session_name`, output `zchat-{name}` (no UUID needed since session name = `zchat-{project_name}`)
- Line 22-79: rewrite config dict to new schema, remove tmuxp.yaml generation, remove bootstrap.sh generation
- Keep `mcp_server_cmd` field in new config

**Step 4: Run all project tests**

Run: `uv run pytest tests/unit/test_project.py -v`
Expected: ALL PASS (fix any other tests broken by schema change)

**Step 5: Commit**

```bash
git add zchat/cli/project.py tests/unit/test_project.py
git commit -m "feat: simplify project config — server refs, runners, zellij session"
```

---

### Task 3: Runner Module (replaces template_loader)

**Files:**
- Create: `zchat/cli/runner.py`
- Modify: `zchat/cli/template_loader.py:17-117` (keep as deprecated wrapper initially)
- Test: `tests/unit/test_runner.py`

**Context:** `template_loader.py` resolves template directories and renders `.env.example`. The new `runner.py` merges global config `[runners.X]` (command/args) with template directory files.

**Step 1: Write failing tests**

```python
# tests/unit/test_runner.py

import pytest
from zchat.cli.runner import resolve_runner, render_env, list_runners


def test_resolve_runner_merges_global_config_and_template(tmp_path):
    """Runner should merge command/args from global config with template files."""
    # Create a template directory
    tpl_dir = tmp_path / "templates" / "claude"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "start.sh").write_text("#!/bin/bash\nexec claude")
    (tpl_dir / ".env.example").write_text("AGENT_NAME={{agent_name}}")
    (tpl_dir / "template.toml").write_text('[template]\nname = "claude"')

    global_config = {
        "runners": {
            "claude-channel": {
                "command": "claude",
                "args": ["--permission-mode", "bypassPermissions"],
            }
        }
    }

    runner = resolve_runner(
        "claude-channel",
        global_config=global_config,
        user_template_dirs=[str(tmp_path / "templates")],
    )
    assert runner["command"] == "claude"
    assert runner["args"] == ["--permission-mode", "bypassPermissions"]
    assert runner["start_script"].endswith("start.sh")
    assert runner["env_template"].endswith(".env.example")


def test_render_env_from_runner(tmp_path):
    tpl_dir = tmp_path / "templates" / "claude"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / ".env.example").write_text(
        "AGENT_NAME={{agent_name}}\nIRC_SERVER={{irc_server}}"
    )

    env = render_env(
        template_dir=str(tpl_dir),
        context={"agent_name": "alice-bot", "irc_server": "127.0.0.1"},
    )
    assert env["AGENT_NAME"] == "alice-bot"
    assert env["IRC_SERVER"] == "127.0.0.1"


def test_resolve_runner_unknown_name_raises():
    with pytest.raises(KeyError):
        resolve_runner("nonexistent", global_config={"runners": {}})
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_runner.py -v`
Expected: FAIL — `zchat.cli.runner` doesn't exist yet.

**Step 3: Implement `runner.py`**

Create `zchat/cli/runner.py`:
- `resolve_runner(name, global_config, user_template_dirs=None)` — looks up `runners.{name}` in global config for command/args, resolves template directory (user > built-in) for start.sh/soul.md/.env.example
- `render_env(template_dir, context)` — reuse logic from `template_loader.render_env`
- `list_runners(global_config, user_template_dirs=None)` — list available runners

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_runner.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add zchat/cli/runner.py tests/unit/test_runner.py
git commit -m "feat: add runner module — merges global config with template assets"
```

---

### Task 4: Zellij CLI Wrapper

**Files:**
- Create: `zchat/cli/zellij.py`
- Test: `tests/unit/test_zellij_helpers.py`

**Context:** Replaces `tmux.py`. Thin wrapper around `subprocess.run(["zellij", ...])`. Read `.claude/skills/zellij/SKILL.md` Part 2 (CLI Scripting) for correct command syntax.

**Step 1: Write failing tests**

```python
# tests/unit/test_zellij_helpers.py

from unittest.mock import patch, MagicMock
import json
from zchat.cli.zellij import (
    ensure_session, new_tab, close_tab, list_tabs,
    send_command, send_keys, dump_screen,
    tab_exists, get_pane_id, kill_session,
)


@patch("zchat.cli.zellij._run")
def test_ensure_session_creates_background(mock_run):
    """Should call zellij attach --create-background."""
    mock_run.return_value = MagicMock(returncode=0)
    ensure_session("zchat-local")
    args = mock_run.call_args[0][0]
    assert "attach" in args
    assert "--create-background" in args
    assert "zchat-local" in args


@patch("zchat.cli.zellij._run")
def test_new_tab_returns_name(mock_run):
    """Should create tab with --name flag."""
    mock_run.return_value = MagicMock(returncode=0, stdout="")
    new_tab("zchat-local", "alice-agent0", command="bash -c 'echo hi'")
    args = mock_run.call_args[0][0]
    assert "new-tab" in args or "new-pane" in args
    assert "--name" in args


@patch("zchat.cli.zellij._run")
def test_send_command_uses_paste_then_enter(mock_run):
    """Should use paste + send-keys Enter pattern."""
    mock_run.return_value = MagicMock(returncode=0)
    send_command("zchat-local", "terminal_1", "cargo build")
    calls = [c[0][0] for c in mock_run.call_args_list]
    # First call should be paste
    assert any("paste" in c for c in calls)
    # Second call should be send-keys Enter
    assert any("send-keys" in c for c in calls)


@patch("zchat.cli.zellij._run")
def test_list_tabs_parses_json(mock_run):
    """Should parse list-tabs --json output."""
    fake_tabs = [{"name": "weechat", "active": True, "panes": [{"id": 1, "is_plugin": False}]}]
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(fake_tabs))
    tabs = list_tabs("zchat-local")
    assert len(tabs) == 1
    assert tabs[0]["name"] == "weechat"


@patch("zchat.cli.zellij._run")
def test_tab_exists_true(mock_run):
    fake_tabs = [{"name": "alice-agent0"}]
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(fake_tabs))
    assert tab_exists("zchat-local", "alice-agent0") is True


@patch("zchat.cli.zellij._run")
def test_tab_exists_false(mock_run):
    fake_tabs = [{"name": "weechat"}]
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(fake_tabs))
    assert tab_exists("zchat-local", "alice-agent0") is False


@patch("zchat.cli.zellij._run")
def test_get_pane_id_extracts_terminal_id(mock_run):
    fake_tabs = [{"name": "agent0", "panes": [{"id": 3, "is_plugin": False}]}]
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(fake_tabs))
    pane_id = get_pane_id("zchat-local", "agent0")
    assert pane_id == "terminal_3"


@patch("zchat.cli.zellij._run")
def test_dump_screen_reads_from_shm(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    with patch("builtins.open", MagicMock(return_value=MagicMock(
        __enter__=lambda s: MagicMock(read=lambda: "screen content"),
        __exit__=lambda *a: None,
    ))):
        # Just verify it calls dump-screen with correct flags
        dump_screen("zchat-local", "terminal_1", full=True)
    args = mock_run.call_args[0][0]
    assert "dump-screen" in args
    assert "--full" in args
    assert "--pane-id" in args
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_zellij_helpers.py -v`
Expected: FAIL — `zchat.cli.zellij` doesn't exist.

**Step 3: Implement `zellij.py`**

Create `zchat/cli/zellij.py` with all functions from design doc Section 1.3. Internal helper `_run(args, **kwargs)` wraps `subprocess.run(["zellij"] + args)`. All functions use `--session` flag to target the correct session.

Key implementation notes (from `.claude/skills/zellij/SKILL.md`):
- `ensure_session`: `zellij attach --create-background {name}`
- `new_tab`: `zellij --session {s} action new-tab --name {name}` with optional `-- {command}`
- `send_command`: `zellij --session {s} action paste --pane-id {id} "{text}"` then `send-keys --pane-id {id} "Enter"`
- `dump_screen`: write to `/dev/shm/zj-{session}-{pane}.txt`, read content, delete file
- `get_pane_id`: parse `list-tabs --json`, compose `terminal_{id}` or `plugin_{id}` from `is_plugin` + `id` fields

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_zellij_helpers.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add zchat/cli/zellij.py tests/unit/test_zellij_helpers.py
git commit -m "feat: add zellij.py CLI wrapper — replaces tmux.py"
```

---

### Task 5: Migrate agent_manager.py to Zellij

**Files:**
- Modify: `zchat/cli/agent_manager.py` (lines 13-15 imports, 37-55 init, 61-69 property, 188-216 spawn, 218-250 force_stop, 278-308 auto_confirm, 310-322 check_alive, 324-340 send)
- Modify: `zchat/cli/runner.py` (integrate with agent creation)
- Test: `tests/unit/test_agent_manager.py`

**Context:** This is the largest single task. Every libtmux call in agent_manager.py must be replaced with zellij.py equivalents. Also integrate runner module for agent creation.

**Step 1: Update existing tests to use zellij mocks**

In `tests/unit/test_agent_manager.py`, replace all tmux/libtmux mocks with zellij mocks:
- `@patch("zchat.cli.tmux.get_or_create_session")` → `@patch("zchat.cli.zellij.ensure_session")`
- `@patch("zchat.cli.tmux.find_window")` → `@patch("zchat.cli.zellij.tab_exists")`
- `@patch("zchat.cli.tmux.window_alive")` → `@patch("zchat.cli.zellij.tab_exists")`
- Mock objects returning `window.active_pane.capture_pane()` → mock `zellij.dump_screen()` returning strings

Add new test for runner integration:

```python
def test_create_agent_uses_runner(tmp_path, monkeypatch):
    """Agent creation should resolve runner from global config."""
    # Setup: mock global config with runner definition
    # Verify: runner.resolve_runner() is called with correct name
    # Verify: zellij.new_tab() is called with the runner's command
    pass  # Implement based on actual AgentManager.__init__ signature changes
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_agent_manager.py -v`
Expected: FAIL — agent_manager still imports libtmux.

**Step 3: Rewrite agent_manager.py**

Key changes:
- **Imports** (line 13-15): remove `import libtmux`, `from zchat.cli.tmux import ...`. Add `from zchat.cli import zellij` and `from zchat.cli.runner import resolve_runner, render_env`
- **`__init__`** (line 37-55): rename `tmux_session` param → `zellij_session`, remove `_tmux_session` attribute, store `_session_name: str`
- **`tmux_session` property** (line 61-69): replace with simple `session_name` property returning `_session_name`
- **`_spawn_tmux`** (line 188-216): rename to `_spawn_tab`, replace `self.tmux_session.new_window(...)` with `zellij.new_tab(self.session_name, name, cmd)`. Store `tab_name` in state (not `window_name`).
- **`_force_stop`** (line 218-250): replace `find_window` → `zellij.tab_exists`, `pane.send_keys(pre_stop)` → `zellij.send_command(session, pane_id, pre_stop)`, `window.kill()` → `zellij.close_tab(session, tab_name)`
- **`_auto_confirm_startup`** (line 278-308): replace `capture_pane()` polling with `zellij.subscribe_pane()` streaming. Parse NDJSON lines, detect confirmation prompts, send Enter via `zellij.send_keys()`. Keep `dump_screen` as fallback.
- **`_check_alive`** (line 310-322): replace `window_alive()` with `zellij.tab_exists(self.session_name, tab_name)`
- **`send`** (line 324-340): replace `find_window → pane.send_keys` with `zellij.send_command(self.session_name, pane_id, text)`

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_agent_manager.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add zchat/cli/agent_manager.py tests/unit/test_agent_manager.py
git commit -m "feat: migrate agent_manager from libtmux to zellij CLI"
```

---

### Task 6: Update app.py — Agent Commands + Shutdown

**Files:**
- Modify: `zchat/cli/app.py` (lines 58-78 tmux helpers, 736-759 focus/hide, 766-792 shutdown)
- Test: `tests/unit/test_agent_focus_hide.py`

**Context:** `app.py` has `_get_tmux_session`, `_tmux_switch`, and uses them in focus/hide/shutdown commands. All need Zellij equivalents.

**Step 1: Update focus/hide tests**

```python
# tests/unit/test_agent_focus_hide.py — update mocks to use zellij

@patch("zchat.cli.zellij.go_to_tab")
def test_focus_switches_to_agent_tab(mock_go_to_tab):
    """focus should call go-to-tab-name with agent tab name."""
    # ...invoke cmd_agent_focus...
    mock_go_to_tab.assert_called_with("zchat-local", "alice-agent0")

@patch("zchat.cli.zellij.go_to_tab")
def test_hide_switches_to_weechat(mock_go_to_tab):
    """hide should call go-to-tab-name with 'weechat'."""
    # ...invoke cmd_agent_hide...
    mock_go_to_tab.assert_called_with("zchat-local", "weechat")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_agent_focus_hide.py -v`
Expected: FAIL

**Step 3: Update `app.py`**

- Delete `_get_tmux_session` (line 58-66) and `_tmux_switch` (line 69-78)
- Add helper: `_zellij_go_to_tab(session, tab_name)` that calls `zellij.go_to_tab(session, tab_name)` — internally runs `zellij --session {s} action go-to-tab-name {tab}`
- Also add `go_to_tab` to `zellij.py` if not already there
- Update `cmd_agent_focus` (line 736-748): use new helper with `agent["tab_name"]`
- Update `cmd_agent_hide` (line 750-759): use new helper with `"weechat"`
- Update `cmd_shutdown` (line 766-792): replace `get_session(name).kill()` with `zellij.kill_session(name)`
- Update config reading: `cfg.get("tmux", {}).get("session")` → `cfg.get("zellij", {}).get("session")`

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_agent_focus_hide.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add zchat/cli/app.py tests/unit/test_agent_focus_hide.py
git commit -m "feat: migrate focus/hide/shutdown from tmux to zellij"
```

---

### Task 7: Phase 1 Integration Test

**Files:**
- Create: `tests/e2e/test_agent_lifecycle_zellij.py`

**Context:** Verify the full agent create→send→stop cycle works with real Zellij. Requires Zellij installed.

**Step 1: Write E2E test**

```python
# tests/e2e/test_agent_lifecycle_zellij.py

import pytest
import time
from zchat.cli import zellij

SESSION = "zchat-test-lifecycle"

@pytest.fixture
def zj_session():
    """Create a throwaway Zellij session for testing."""
    zellij.ensure_session(SESSION)
    yield SESSION
    zellij.kill_session(SESSION)

@pytest.mark.e2e
def test_tab_create_exists_close(zj_session):
    """Tab lifecycle: create, verify exists, close, verify gone."""
    zellij.new_tab(zj_session, "test-tab", command="sleep 300")
    time.sleep(1)
    assert zellij.tab_exists(zj_session, "test-tab")

    zellij.close_tab(zj_session, "test-tab")
    time.sleep(1)
    assert not zellij.tab_exists(zj_session, "test-tab")

@pytest.mark.e2e
def test_send_and_read(zj_session):
    """Send command to pane and read output."""
    zellij.new_tab(zj_session, "echo-tab")
    time.sleep(1)
    pane_id = zellij.get_pane_id(zj_session, "echo-tab")
    assert pane_id is not None

    zellij.send_command(zj_session, pane_id, "echo HELLO_ZELLIJ")
    time.sleep(2)
    screen = zellij.dump_screen(zj_session, pane_id)
    assert "HELLO_ZELLIJ" in screen

    zellij.close_tab(zj_session, "echo-tab")
```

**Step 2: Run E2E test**

Run: `uv run pytest tests/e2e/test_agent_lifecycle_zellij.py -v -m e2e`
Expected: ALL PASS (requires Zellij running)

**Step 3: Commit**

```bash
git add tests/e2e/test_agent_lifecycle_zellij.py
git commit -m "test: add E2E tests for zellij tab lifecycle"
```

---

## Phase 2: WeeChat + KDL Layout + Startup

### Task 8: KDL Layout Generator

**Files:**
- Create: `zchat/cli/layout.py`
- Test: `tests/unit/test_layout.py`

**Context:** Generates KDL layout files for Zellij from project config + agent state.

**Step 1: Write failing tests**

```python
# tests/unit/test_layout.py

from zchat.cli.layout import generate_layout, write_layout


def test_generate_layout_with_weechat_only():
    config = {"default_channels": ["#general"]}
    state = {"agents": {}}
    weechat_cmd = 'weechat -r "/server add test 127.0.0.1/6667"'

    kdl = generate_layout(config, state, weechat_cmd=weechat_cmd)
    assert "layout {" in kdl
    assert 'tab name="weechat"' in kdl
    assert "weechat" in kdl


def test_generate_layout_with_agents():
    config = {"default_channels": ["#general"]}
    state = {
        "agents": {
            "alice-agent0": {
                "tab_name": "alice-agent0",
                "workspace": "/tmp/ws",
                "status": "running",
            }
        }
    }
    kdl = generate_layout(config, state, weechat_cmd="weechat")
    assert 'tab name="alice-agent0"' in kdl
    assert 'tab name="weechat"' in kdl


def test_write_layout_creates_file(tmp_path):
    config = {"default_channels": ["#general"]}
    state = {"agents": {}}
    path = write_layout(tmp_path, config, state, weechat_cmd="weechat")
    assert path.exists()
    assert path.name == "layout.kdl"
    content = path.read_text()
    assert "layout {" in content
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_layout.py -v`
Expected: FAIL — module doesn't exist.

**Step 3: Implement `layout.py`**

KDL generation as string building (no KDL library needed — the format is simple enough):

```python
def generate_layout(config: dict, state: dict, weechat_cmd: str = "") -> str:
    """Generate KDL layout string."""
    lines = ["layout {"]
    # WeeChat tab (always first)
    lines.append('    tab name="weechat" {')
    lines.append(f'        pane command="bash" {{')
    lines.append(f'            args "-c" "{_escape_kdl(weechat_cmd)}"')
    lines.append( '        }')
    lines.append( '    }')
    # Agent tabs (from state)
    for name, agent in state.get("agents", {}).items():
        if agent.get("status") == "running":
            ws = agent.get("workspace", "")
            lines.append(f'    tab name="{name}" {{')
            lines.append(f'        pane command="bash" {{')
            lines.append(f'            args "-c" "cd {ws} && source .zchat-env && bash start.sh"')
            lines.append( '        }')
            lines.append( '    }')
    lines.append("}")
    return "\n".join(lines)
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_layout.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add zchat/cli/layout.py tests/unit/test_layout.py
git commit -m "feat: add KDL layout generator for Zellij sessions"
```

---

### Task 9: Migrate irc_manager.py

**Files:**
- Modify: `zchat/cli/irc_manager.py` (lines 10-12 imports, 30-43 init/property, 191-272 start_weechat, 274-283 _update_tmuxp_weechat, 285-300 stop_weechat, 345-349 helpers)
- Test: `tests/unit/test_irc_manager.py` (if exists, update; else create)

**Step 1: Write/update tests**

```python
# tests/unit/test_irc_manager.py

@patch("zchat.cli.zellij.new_tab")
@patch("zchat.cli.zellij.get_pane_id", return_value="terminal_1")
def test_start_weechat_creates_zellij_tab(mock_pane, mock_new_tab):
    # Verify new_tab called with "weechat" name and correct command
    pass

@patch("zchat.cli.zellij.send_command")
@patch("zchat.cli.zellij.tab_exists", return_value=True)
def test_stop_weechat_sends_quit(mock_exists, mock_send):
    # Verify send_command called with "/quit"
    pass
```

**Step 2: Run tests, verify fail**

**Step 3: Update `irc_manager.py`**

- Remove imports: `import libtmux`, `from zchat.cli.tmux import ...`
- Add: `from zchat.cli import zellij`
- Remove `_tmux_session` attribute and `tmux_session` property
- Add `_session_name: str` attribute
- `start_weechat`: remove tmuxp load path (lines 204-213), remove `_update_tmuxp_weechat` call. Use `zellij.new_tab(self._session_name, "weechat", weechat_cmd)`. Store `weechat_tab` + `weechat_pane_id` in state.
- Delete `_update_tmuxp_weechat` entirely (lines 274-283)
- `stop_weechat`: use `zellij.send_command(session, pane_id, "/quit")` then `zellij.close_tab` as fallback
- Delete `_pane_alive` / `_window_alive` helper wrappers (lines 345-349)

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_irc_manager.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add zchat/cli/irc_manager.py tests/unit/test_irc_manager.py
git commit -m "feat: migrate irc_manager from libtmux to zellij"
```

---

### Task 10: One-Command Startup + project use

**Files:**
- Modify: `zchat/cli/app.py` (default command, `cmd_project_use`)
- Test: `tests/unit/test_app_startup.py`

**Context:** `zchat` (no args) should start Zellij session. `zchat project use X` should switch/attach.

**Step 1: Write tests**

```python
# tests/unit/test_app_startup.py

@patch("os.execvp")
@patch("zchat.cli.zellij.session_exists", return_value=False)
@patch("zchat.cli.layout.write_layout")
def test_default_command_starts_new_session(mock_layout, mock_exists, mock_exec):
    mock_layout.return_value = Path("/tmp/layout.kdl")
    # invoke default command
    # verify os.execvp called with zellij --new-session-with-layout
    pass

@patch("os.execvp")
@patch("zchat.cli.zellij.session_exists", return_value=True)
def test_default_command_attaches_existing(mock_exists, mock_exec):
    # verify os.execvp called with zellij attach
    pass

@patch("os.environ", {"ZELLIJ": "1"})
@patch("zchat.cli.zellij.switch_session")
def test_default_command_switches_when_inside_zellij(mock_switch):
    # verify switch_session called instead of execvp
    pass
```

**Step 2: Run tests, verify fail**

**Step 3: Implement startup logic**

Add `switch_session` and `session_exists` to `zellij.py`. Implement default command in `app.py` per design Section 2.5. Update `cmd_project_use` per design Section 2.3.

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_app_startup.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add zchat/cli/app.py zchat/cli/zellij.py tests/unit/test_app_startup.py
git commit -m "feat: zchat one-command startup + project use via Zellij"
```

---

### Task 11: Migrate claude.sh, start.sh, stop.sh

**Files:**
- Modify: `claude.sh` (rewrite tmux → zellij)
- Modify: `start.sh` (lines 8, 30, 43-44)
- Modify: `stop.sh` (lines 7, 10-11)

**Step 1: Rewrite shell scripts**

`start.sh`:
- Line 8: `SESSION="zchat-${PROJECT}"` → keep (session name format matches)
- Line 30: `ZCHAT_TMUX_SESSION=$SESSION` → `ZCHAT_ZELLIJ_SESSION=$SESSION`
- Line 43-44: `tmux -CC attach` / `tmux attach` → `zellij attach "$SESSION"` (or `--new-session-with-layout`)

`stop.sh`:
- Line 7: `ZCHAT_TMUX_SESSION=$SESSION` → `ZCHAT_ZELLIJ_SESSION=$SESSION`
- Line 11: `tmux kill-session -t "$SESSION"` → `zellij kill-session "$SESSION"`

`claude.sh`:
- Replace all `tmux` commands with Zellij equivalents
- Remove iTerm2 `tmux -CC` integration (Zellij doesn't support this)
- `tmux new-session` → `zellij --new-session-with-layout` or `zellij attach --create-background`
- `tmux attach` → `zellij attach`
- `tmux has-session` → `zellij list-sessions | grep`
- `tmux switch-client` → `zellij action switch-session` (inside Zellij only)

**Step 2: Verify scripts are syntactically correct**

Run: `bash -n start.sh && bash -n stop.sh && bash -n claude.sh && echo "OK"`
Expected: OK

**Step 3: Commit**

```bash
git add claude.sh start.sh stop.sh
git commit -m "feat: migrate shell scripts from tmux to zellij"
```

---

### Task 12: Phase 2 E2E Test

**Files:**
- Create: `tests/e2e/test_startup_zellij.py`

**Step 1: Write E2E test for full startup flow**

```python
@pytest.mark.e2e
def test_full_startup_creates_session_with_weechat(cli, project, ergo_server):
    """zchat (no args) should create Zellij session with weechat tab."""
    # This test needs to run in a subprocess since zchat does os.execvp
    result = cli("--project", project, "irc", "start")
    assert result.returncode == 0

    # Verify weechat tab exists
    from zchat.cli import zellij
    session = f"zchat-{project}"
    assert zellij.tab_exists(session, "weechat")

    # Cleanup
    cli("--project", project, "shutdown")
```

**Step 2: Run and verify**

Run: `uv run pytest tests/e2e/test_startup_zellij.py -v -m e2e`

**Step 3: Commit**

```bash
git add tests/e2e/test_startup_zellij.py
git commit -m "test: add E2E test for Zellij startup flow"
```

---

## Phase 3: WASM Plugin

### Task 13: Scaffold zchat-hub Plugin

**Files:**
- Create: `zchat-hub-plugin/Cargo.toml`
- Create: `zchat-hub-plugin/.cargo/config.toml`
- Create: `zchat-hub-plugin/src/lib.rs`

**Context:** Read `.claude/skills/zellij/SKILL.md` Part 3 and `references/plugin-patterns.md` before starting.

**Step 1: Create project structure**

```toml
# zchat-hub-plugin/Cargo.toml
[package]
name = "zchat-hub"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]

[dependencies]
zellij-tile = "0.42"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

```toml
# zchat-hub-plugin/.cargo/config.toml
[build]
target = "wasm32-wasi"
```

**Step 2: Implement minimal plugin skeleton**

```rust
// zchat-hub-plugin/src/lib.rs
use zellij_tile::prelude::*;
use std::collections::BTreeMap;

#[derive(Default)]
struct ZchatHub {
    sessions: Vec<SessionInfo>,
    tabs: Vec<TabInfo>,
    selected_index: usize,
    mode: HubMode,
}

#[derive(Default, PartialEq)]
enum HubMode {
    #[default]
    ProjectList,
    AgentList,
    CreateAgent,
}

impl ZellijPlugin for ZchatHub {
    fn load(&mut self, _configuration: BTreeMap<String, String>) {
        request_permission(&[
            PermissionType::ReadApplicationState,
            PermissionType::ChangeApplicationState,
            PermissionType::RunCommands,
        ]);
        subscribe(&[
            EventType::SessionUpdate,
            EventType::TabUpdate,
            EventType::Key,
            EventType::RunCommandResult,
        ]);
    }

    fn update(&mut self, event: Event) -> bool {
        match event {
            Event::SessionUpdate(sessions, _) => {
                self.sessions = sessions.into_iter()
                    .filter(|s| s.name.starts_with("zchat-"))
                    .collect();
                true
            }
            Event::TabUpdate(tabs) => {
                self.tabs = tabs;
                true
            }
            Event::Key(key) => self.handle_key(key),
            Event::RunCommandResult(exit_code, stdout, stderr, context) => {
                self.handle_command_result(exit_code, stdout, stderr, context)
            }
            _ => false,
        }
    }

    fn render(&mut self, rows: usize, cols: usize) {
        match self.mode {
            HubMode::ProjectList => self.render_project_list(rows, cols),
            HubMode::AgentList => self.render_agent_list(rows, cols),
            HubMode::CreateAgent => self.render_create_agent(rows, cols),
        }
    }
}

register_plugin!(ZchatHub);
```

**Step 3: Build**

Run: `cd zchat-hub-plugin && rustup target add wasm32-wasi && cargo build --release`
Expected: Compiles successfully to `target/wasm32-wasi/release/zchat_hub.wasm`

**Step 4: Commit**

```bash
git add zchat-hub-plugin/
git commit -m "feat: scaffold zchat-hub Zellij WASM plugin"
```

---

### Task 14: Implement Plugin Features

**Files:**
- Modify: `zchat-hub-plugin/src/lib.rs`

**Context:** Implement full feature set: project switching, agent list (from TabUpdate), create/stop agent (via run_command + zchat CLI).

**Step 1: Implement `handle_key`**

Key mapping:
- `Up/k`: move selection up
- `Down/j`: move selection down
- `Enter`: in ProjectList → switch session; in AgentList → focus agent tab
- `c`: create agent (switch to CreateAgent mode)
- `d`: stop selected agent
- `Tab`: toggle between ProjectList and AgentList
- `Esc/q`: close plugin

**Step 2: Implement `render_project_list`**

Using `Text` + `print_text_with_coordinates`:
- Title: "zchat Hub"
- List all `zchat-*` sessions with agent count (from tabs, excluding "weechat")
- `*` marker for current session
- Cursor on selected

**Step 3: Implement `render_agent_list`**

- Show tabs from current session (excluding "weechat" and system tabs)
- Tab exists = running (green), tab exited = offline (dim)
- Help bar: `[c]reate [d]elete [Enter] focus [Tab] projects [q]uit`

**Step 4: Implement agent create/stop**

```rust
fn create_agent(&self, name: &str) {
    let project = self.current_project_name();
    run_command(
        &["zchat", "agent", "create", name, "--project", &project],
        BTreeMap::from([("op".into(), "create_agent".into())]),
    );
}

fn stop_agent(&self, name: &str) {
    let project = self.current_project_name();
    run_command(
        &["zchat", "agent", "stop", name, "--project", &project],
        BTreeMap::from([("op".into(), "stop_agent".into())]),
    );
}
```

**Step 5: Build and test manually**

```bash
cd zchat-hub-plugin && cargo build --release
zellij plugin -f -- file:./target/wasm32-wasi/release/zchat_hub.wasm
```

**Step 6: Commit**

```bash
git add zchat-hub-plugin/src/lib.rs
git commit -m "feat: implement zchat-hub plugin — project switch, agent management"
```

---

### Task 15: Plugin Distribution + Keybinding

**Files:**
- Create: `zchat/cli/data/config.kdl` (zchat's default Zellij config)
- Modify: `zchat/cli/layout.py` (embed plugin pane in layout)
- Modify: `zchat/cli/app.py` (add plugin install to setup flow)

**Step 1: Create default config.kdl**

```kdl
// zchat/cli/data/config.kdl
keybinds {
    shared_except "locked" {
        bind "Ctrl k" {
            LaunchOrFocusPlugin "file:~/.zchat/plugins/zchat-hub.wasm" {
                floating true
                move_to_focused_tab true
            }
        }
    }
}
```

**Step 2: Add plugin install logic**

In `app.py` or a new setup command: copy `zchat-hub.wasm` to `~/.zchat/plugins/`. The .wasm binary is distributed with the Python package (via `package_data` in `pyproject.toml`).

**Step 3: Update layout generation**

In `layout.py`, when generating layout, point Zellij to use zchat's config.kdl via `zellij --config {config_path} --new-session-with-layout {layout_path}`.

**Step 4: Build plugin + test keybinding**

```bash
cd zchat-hub-plugin && cargo build --release
cp target/wasm32-wasi/release/zchat_hub.wasm ~/.zchat/plugins/
# Start zchat, press Ctrl-K, verify hub appears
```

**Step 5: Commit**

```bash
git add zchat/cli/data/config.kdl zchat/cli/layout.py zchat/cli/app.py
git commit -m "feat: integrate zchat-hub plugin with keybinding and auto-install"
```

---

## Phase 4: Cleanup + Release

### Task 16: Remove tmux Dependencies

**Files:**
- Delete: `zchat/cli/tmux.py`
- Modify: `pyproject.toml` (lines 8, 9, 10)
- Modify: `zchat/cli/doctor.py` (lines 78-79)
- Modify: `install.sh` (lines 33, 58, 131-134)
- Modify: `.github/workflows/test.yml` (line 15)

**Step 1: Remove deps**

`pyproject.toml`: remove `libtmux`, `tmuxp`. Check if `pyyaml` is used elsewhere — if only for tmuxp YAML, remove it too.

`doctor.py`: replace tmux/tmuxp checks with `("zellij", True, "brew install zellij")`.

`install.sh`: replace `tmux` → `zellij` in checks and brew install.

`.github/workflows/test.yml`: `brew install tmux` → `brew install zellij`.

**Step 2: Delete tmux.py**

```bash
git rm zchat/cli/tmux.py
```

**Step 3: Verify no remaining tmux imports**

Run: `grep -r "tmux\|libtmux\|tmuxp" zchat/ --include="*.py" | grep -v "# legacy\|comment\|__pycache__"`
Expected: No results (or only migration code comments)

**Step 4: Run full unit test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git rm zchat/cli/tmux.py
git add pyproject.toml zchat/cli/doctor.py install.sh .github/workflows/test.yml
git commit -m "chore: remove tmux/libtmux/tmuxp dependencies"
```

---

### Task 17: Config & State Migration

**Files:**
- Create: `zchat/cli/migrate.py`
- Test: `tests/unit/test_migrate.py`

**Step 1: Write tests**

```python
# tests/unit/test_migrate.py

def test_migrate_config_tmux_to_zellij(tmp_path):
    old_config = tmp_path / "config.toml"
    old_config.write_text("""
[irc]
server = "127.0.0.1"
port = 6667
tls = false

[agents]
default_type = "claude"
default_channels = ["#general"]

[tmux]
session = "zchat-abc12345-local"
""")
    from zchat.cli.migrate import migrate_config_if_needed
    migrate_config_if_needed(tmp_path)

    import tomllib
    with open(old_config, "rb") as f:
        cfg = tomllib.load(f)
    assert "zellij" in cfg
    assert cfg["zellij"]["session"] == "zchat-local"  # simplified
    assert "tmux" not in cfg
    assert "default_runner" in cfg
    assert (tmp_path / "config.toml.bak").exists()


def test_migrate_state_json(tmp_path):
    state = tmp_path / "state.json"
    state.write_text('{"agents": {"a0": {"window_name": "a0", "pane_id": "%5"}}}')
    from zchat.cli.migrate import migrate_state_if_needed
    migrate_state_if_needed(tmp_path)

    import json
    data = json.loads(state.read_text())
    assert "tab_name" in data["agents"]["a0"]
    assert "window_name" not in data["agents"]["a0"]
    assert "pane_id" not in data["agents"]["a0"]
```

**Step 2: Implement migration**

**Step 3: Run tests, commit**

```bash
git add zchat/cli/migrate.py tests/unit/test_migrate.py
git commit -m "feat: add config and state migration from tmux to zellij"
```

---

### Task 18: Test Infrastructure Update

**Files:**
- Rewrite: `tests/shared/tmux_helpers.py` → `tests/shared/zellij_helpers.py`
- Delete: `tests/unit/test_tmux_helpers.py`
- Modify: `tests/e2e/conftest.py`
- Modify: `tests/pre_release/conftest.py`
- Modify: `pytest.ini`

**Step 1: Create `zellij_helpers.py`**

Replace `send_keys`, `capture_pane`, `wait_for_content` with Zellij equivalents using `zchat.cli.zellij`.

**Step 2: Update conftest fixtures**

- `tmux_session` → `zellij_session` (create throwaway session)
- `tmux_send` → `zellij_send` (send to pane)
- `weechat_window` → `weechat_tab`

**Step 3: Update pytest.ini marker**

`e2e: end-to-end tests requiring ergo + tmux` → `e2e: end-to-end tests requiring ergo + zellij`

**Step 4: Delete old tmux test**

```bash
git rm tests/unit/test_tmux_helpers.py
```

**Step 5: Run full test suite**

Run: `uv run pytest tests/unit/ -v && uv run pytest tests/e2e/ -v -m e2e`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add tests/ pytest.ini
git commit -m "test: migrate test infrastructure from tmux to zellij"
```

---

### Task 19: Update walkthrough.sh + Pre-Release Tests

**Files:**
- Modify: `tests/pre_release/walkthrough.sh`
- Modify: `tests/pre_release/walkthrough-steps.sh`
- Modify: `tests/pre_release/conftest.py`

**Step 1: Update all tmux commands in walkthrough scripts**

Replace `tmux` commands with `zellij` equivalents throughout. Update expected output patterns.

**Step 2: Run walkthrough**

Run: `./tests/pre_release/walkthrough.sh`
Expected: Completes successfully, produces `.cast` file

**Step 3: Commit**

```bash
git add tests/pre_release/
git commit -m "test: update pre-release walkthrough for zellij"
```

---

### Task 20: Final Cleanup + Template→Runner Rename

**Files:**
- Delete: `zchat/cli/template_loader.py` (if no longer imported anywhere)
- Modify: `zchat/cli/app.py` (rename `zchat template *` → `zchat runner *`)
- Modify: `README.md`

**Step 1: Rename CLI commands**

In `app.py`, rename the template subcommand group to `runner`. Update help text.

**Step 2: Verify no remaining tmux references**

Run: `grep -r "tmux\|libtmux\|tmuxp" . --include="*.py" --include="*.sh" --include="*.yml" --include="*.toml" --include="*.md" | grep -v node_modules | grep -v .git | grep -v __pycache__ | grep -v "design.md\|plan.md"`

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v && uv run pytest tests/e2e/ -v -m e2e`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: final cleanup — remove template_loader, rename to runner, update docs"
```

---

### Task 21: Version Bump + Release Prep

**Files:**
- Modify: `pyproject.toml` (version bump)
- Modify: `docs/releasing.md`

**Step 1: Bump version**

Dev version bump per project convention (e.g., `0.4.0.dev1`).

**Step 2: Update releasing docs**

Note that Homebrew formula now depends on `zellij` instead of `tmux`.

**Step 3: Final verification**

Run: `uv run pytest tests/unit/ -v && uv run pytest tests/e2e/ -v -m e2e`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add pyproject.toml docs/releasing.md
git commit -m "chore: bump version for zellij migration release"
```

---

## Task Dependency Graph

```
Phase 1 (sequential):
  Task 1 (global config) → Task 2 (project config) → Task 3 (runner)
  Task 4 (zellij.py) → Task 5 (agent_manager) → Task 6 (app.py focus/hide/shutdown)
  Task 3 + Task 6 → Task 7 (Phase 1 E2E)

Phase 2 (after Phase 1):
  Task 8 (layout.py) → Task 9 (irc_manager) → Task 10 (startup) → Task 11 (shell scripts) → Task 12 (Phase 2 E2E)

Phase 3 (after Phase 2):
  Task 13 (plugin scaffold) → Task 14 (plugin features) → Task 15 (distribution)

Phase 4 (after Phase 3):
  Task 16 (remove tmux) → Task 17 (migration) → Task 18 (test infra) → Task 19 (walkthrough) → Task 20 (cleanup) → Task 21 (release)
```

**Parallelizable within Phase 1:** Tasks 1-3 (config/runner) and Task 4 (zellij.py) have no dependencies between them and can run in parallel.
