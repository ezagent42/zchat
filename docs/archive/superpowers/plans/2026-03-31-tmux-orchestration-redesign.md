# Tmux Orchestration Redesign — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fragile sleep-based tmux orchestration with tmuxp declarative layout, SessionStart hook readiness detection, and persistent agent workspaces using windows instead of panes.

**Architecture:** Three coordinated changes: (1) tmux.py + agent_manager switch from pane to window model with persistent workspaces, (2) project.py + irc_manager use tmuxp YAML for session creation, (3) start.sh adds SessionStart hook for ready markers and agent_manager polls for readiness.

**Tech Stack:** Python (libtmux, tmuxp, pyyaml), bash (start.sh, bootstrap.sh), Claude Code hooks (SessionStart)

**Spec:** `docs/superpowers/specs/2026-03-31-tmux-orchestration-redesign.md`

---

## Chunk 1: Window model + persistent workspaces

### Task 1: Add window helpers to tmux.py

**Files:**
- Modify: `zchat/cli/tmux.py`
- Test: `tests/unit/test_tmux_helpers.py`

- [ ] **Step 1: Write failing tests for find_window and window_alive**

In `tests/unit/test_tmux_helpers.py`, add:

```python
def test_find_window_returns_window(tmux_env):
    from zchat.cli.tmux import get_session, find_window
    session = get_session(tmux_env)
    window = session.active_window
    found = find_window(session, window.window_name)
    assert found is not None
    assert found.window_name == window.window_name


def test_find_window_returns_none_for_missing(tmux_env):
    from zchat.cli.tmux import get_session, find_window
    session = get_session(tmux_env)
    assert find_window(session, "nonexistent-window-xyz") is None


def test_window_alive(tmux_env):
    from zchat.cli.tmux import get_session, window_alive
    session = get_session(tmux_env)
    window = session.active_window
    assert window_alive(session, window.window_name) is True
    assert window_alive(session, "nonexistent-window-xyz") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_tmux_helpers.py::test_find_window_returns_window tests/unit/test_tmux_helpers.py::test_find_window_returns_none_for_missing tests/unit/test_tmux_helpers.py::test_window_alive -v`
Expected: FAIL — `find_window` and `window_alive` not defined.

- [ ] **Step 3: Implement find_window and window_alive**

In `zchat/cli/tmux.py`, add after `pane_alive`:

```python
from libtmux import Window


def find_window(session: Session, window_name: str) -> Window | None:
    """Find a window by name within a session. Returns None if not found."""
    for window in session.windows:
        if window.window_name == window_name:
            return window
    return None


def window_alive(session: Session, window_name: str) -> bool:
    """Check if a window still exists in the session."""
    return find_window(session, window_name) is not None
```

Also add `Window` to the imports at the top:
```python
from libtmux import Pane, Session, Window
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_tmux_helpers.py -v`
Expected: All PASS (8 tests: 5 existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add zchat/cli/tmux.py tests/unit/test_tmux_helpers.py
git commit -m "feat(tmux): add find_window and window_alive helpers"
```

---

### Task 2: Persistent agent workspace

**Files:**
- Modify: `zchat/cli/agent_manager.py`
- Test: `tests/unit/test_agent_manager.py`

- [ ] **Step 1: Write failing test for persistent workspace path**

In `tests/unit/test_agent_manager.py`, update `_make_manager` and add test:

```python
def _make_manager(state_file="/tmp/test-agents.json", env_file="", project_dir=""):
    return AgentManager(
        irc_server="localhost", irc_port=6667, irc_tls=False,
        irc_password="",
        username="alice", default_channels=["#general"],
        env_file=env_file,
        default_type="claude",
        state_file=state_file,
        project_dir=project_dir,
    )


def test_create_workspace_persistent(tmp_path):
    """Workspace should be under project_dir/agents/ when project_dir is set."""
    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    ws = mgr._create_workspace("alice-helper")
    assert ws == str(tmp_path / "agents" / "alice-helper")
    assert os.path.isdir(ws)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_agent_manager.py::test_create_workspace_persistent -v`
Expected: FAIL — workspace still uses `/tmp/`.

- [ ] **Step 3: Implement persistent workspace**

In `zchat/cli/agent_manager.py`, replace `_create_workspace`:

```python
def _create_workspace(self, name: str) -> str:
    if self.project_dir:
        workspace = os.path.join(self.project_dir, "agents", name)
    else:
        safe = name.replace(AGENT_SEPARATOR, "_")
        workspace = os.path.join(tempfile.gettempdir(), f"zchat-{safe}")
    os.makedirs(workspace, exist_ok=True)
    return workspace
```

- [ ] **Step 4: Update _cleanup_workspace to only delete ready marker**

Replace `_cleanup_workspace`:

```python
def _cleanup_workspace(self, name: str):
    """Delete ready marker on stop. Preserve workspace for restart."""
    if self.project_dir:
        ready_file = os.path.join(self.project_dir, "agents", f"{name}.ready")
        if os.path.isfile(ready_file):
            os.remove(ready_file)
    else:
        # Legacy: clean up /tmp workspaces
        agent = self._agents.get(name)
        if agent:
            ws = agent.get("workspace", "")
            if ws.startswith(tempfile.gettempdir()):
                shutil.rmtree(ws, ignore_errors=True)
```

- [ ] **Step 5: Write test for cleanup only removes ready marker**

```python
def test_cleanup_workspace_only_removes_ready_marker(tmp_path):
    """Stop should delete .ready marker but preserve workspace directory."""
    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    # Create workspace and ready marker
    ws = tmp_path / "agents" / "alice-helper"
    ws.mkdir(parents=True)
    ready = tmp_path / "agents" / "alice-helper.ready"
    ready.touch()
    mgr._agents["alice-helper"] = {"workspace": str(ws), "status": "running"}
    mgr._cleanup_workspace("alice-helper")
    assert ws.is_dir(), "workspace should be preserved"
    assert not ready.exists(), "ready marker should be deleted"
```

- [ ] **Step 6: Run all agent manager tests**

Run: `uv run pytest tests/unit/test_agent_manager.py -v`
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add zchat/cli/agent_manager.py tests/unit/test_agent_manager.py
git commit -m "feat(agent): persistent workspaces under project_dir/agents/"
```

---

### Task 3: Switch agent_manager from pane to window model

**Files:**
- Modify: `zchat/cli/agent_manager.py`
- Test: `tests/unit/test_agent_manager.py`

- [ ] **Step 1: Update _spawn_tmux to use session.new_window**

Replace `_spawn_tmux` method:

```python
def _spawn_tmux(self, name: str, workspace: str, agent_type: str,
                channels: list[str]) -> str:
    context = self._build_env_context(name, workspace, channels)
    env = render_env(agent_type, context)

    # Overlay project-level env_file (lower priority than template env)
    if self.env_file and os.path.isfile(self.env_file):
        project_env = _parse_env_file(self.env_file)
        merged = dict(project_env)
        merged.update(env)
        env = merged

    start_script = get_start_script(agent_type)

    # Write env to workspace
    env_file_path = os.path.join(workspace, ".zchat-env")
    with open(env_file_path, "w") as f:
        for k, v in env.items():
            f.write(f"export {k}={shlex.quote(v)}\n")

    cmd = f"cd '{workspace}' && source .zchat-env && bash '{start_script}'"

    # Create dedicated window (not pane) for this agent
    window = self.tmux_session.new_window(
        window_name=name, window_shell=cmd, attach=False,
    )
    window_name = window.window_name
    return window_name
```

- [ ] **Step 2: Update create() to store window_name instead of pane_id**

In `create()`, replace `pane_id` with `window_name`:

```python
def create(self, name: str, workspace: str | None = None,
           channels: list[str] | None = None,
           agent_type: str | None = None) -> dict:
    """Create and launch a new agent. Returns agent info dict."""
    name = self.scoped(name)
    if name in self._agents and self._agents[name].get("status") == "running":
        raise ValueError(f"{name} already exists and is running")

    agent_type = agent_type or self.default_type
    channels = channels or list(self.default_channels)
    agent_workspace = workspace or self._create_workspace(name)

    window_name = self._spawn_tmux(name, agent_workspace, agent_type, channels)

    self._agents[name] = {
        "type": agent_type,
        "workspace": agent_workspace,
        "window_name": window_name,
        "status": "starting",
        "created_at": time.time(),
        "channels": channels,
    }
    self._save_state()
    return self._agents[name]
```

- [ ] **Step 3: Update _force_stop to kill window**

Replace `_force_stop`:

```python
def _force_stop(self, name: str):
    from zchat.cli.tmux import find_window
    agent = self._agents.get(name)
    if not agent or not agent.get("window_name"):
        return
    window = find_window(self.tmux_session, agent["window_name"])
    if not window:
        return

    agent_type = agent.get("type", self.default_type)
    try:
        tpl = load_template(agent_type)
        pre_stop = tpl.get("hooks", {}).get("pre_stop", "")
    except Exception:
        pre_stop = ""

    if pre_stop:
        # Send to the window's first pane
        pane = window.active_pane
        if pane:
            pane.send_keys(pre_stop, enter=True)
        # Poll for up to 10 seconds
        from zchat.cli.tmux import window_alive
        for _ in range(20):
            time.sleep(0.5)
            if not window_alive(self.tmux_session, agent["window_name"]):
                return
    # Kill window as fallback
    try:
        window.kill()
    except Exception:
        pass
```

- [ ] **Step 4: Update _check_alive to use window_name**

Replace `_check_alive`:

```python
def _check_alive(self, name: str) -> str:
    from zchat.cli.tmux import window_alive
    agent = self._agents.get(name)
    if not agent:
        return "offline"
    # Support both new (window_name) and legacy (pane_id) state
    wname = agent.get("window_name")
    if wname:
        return "running" if window_alive(self.tmux_session, wname) else "offline"
    # Legacy: pane_id
    pid = agent.get("pane_id")
    if pid:
        return "running" if pane_alive(self.tmux_session, pid) else "offline"
    return "offline"
```

- [ ] **Step 5: Update send() to use window**

Replace `send`:

```python
def send(self, name: str, text: str):
    """Send text to agent's tmux window."""
    from zchat.cli.tmux import find_window
    name = self.scoped(name)
    agent = self._agents.get(name)
    if not agent:
        raise ValueError(f"Unknown agent: {name}")
    if self._check_alive(name) != "running":
        raise ValueError(f"{name} is not running")
    window = find_window(self.tmux_session, agent["window_name"])
    if window and window.active_pane:
        window.active_pane.send_keys(text, enter=True)
```

- [ ] **Step 6: Update _build_env_context to add ZCHAT_PROJECT_DIR**

In `_build_env_context`, add `zchat_project_dir` to the context:

```python
    context = {
        "agent_name": name,
        "irc_server": self.irc_server,
        "irc_port": str(self.irc_port),
        "irc_channels": channels_str,
        "irc_tls": str(self.irc_tls).lower(),
        "irc_password": self.irc_password,
        "workspace": workspace,
        "zchat_project_dir": self.project_dir,
        "irc_sasl_user": "",
        "irc_sasl_pass": "",
        "auth_token_file": "",
    }
```

- [ ] **Step 7: Update imports — remove unused pane imports**

At top of `agent_manager.py`, change:
```python
from zchat.cli.tmux import get_or_create_session, find_pane, pane_alive
```
to:
```python
from zchat.cli.tmux import get_or_create_session, pane_alive
```

(`find_pane` is no longer used directly; `pane_alive` kept for legacy `_check_alive` fallback.)

- [ ] **Step 8: Update test_agent_state_persistence**

In `tests/unit/test_agent_manager.py`, update the state test:

```python
def test_agent_state_persistence(tmp_path):
    state_file = str(tmp_path / "agents.json")
    mgr = _make_manager(state_file=state_file)
    mgr._agents["alice-helper"] = {
        "type": "claude",
        "workspace": "/tmp/x", "window_name": "alice-helper", "status": "running",
        "created_at": 0, "channels": ["#general"],
    }
    mgr._save_state()
    mgr2 = _make_manager(state_file=state_file)
    assert "alice-helper" in mgr2._agents
    assert mgr2._agents["alice-helper"]["window_name"] == "alice-helper"
```

- [ ] **Step 9: Update test_build_env_context**

```python
def test_build_env_context():
    """_build_env_context renders all required placeholders."""
    mgr = _make_manager(project_dir="/tmp/test-project")
    ctx = mgr._build_env_context("alice-bot", "/tmp/ws", ["#general", "#dev"])
    assert ctx["agent_name"] == "alice-bot"
    assert ctx["irc_server"] == "localhost"
    assert ctx["irc_port"] == "6667"
    assert ctx["irc_channels"] == "general,dev"
    assert ctx["irc_tls"] == "false"
    assert ctx["workspace"] == "/tmp/ws"
    assert ctx["zchat_project_dir"] == "/tmp/test-project"
```

- [ ] **Step 10: Run all unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS.

- [ ] **Step 11: Commit**

```bash
git add zchat/cli/agent_manager.py tests/unit/test_agent_manager.py
git commit -m "refactor(agent): switch from pane to window model

Each agent gets its own tmux window instead of a pane in a shared window.
State uses window_name instead of pane_id (legacy fallback preserved)."
```

---

### Task 4: Update app.py for window model

**Files:**
- Modify: `zchat/cli/app.py`

- [ ] **Step 1: Update cmd_agent_create output**

In `cmd_agent_create`, change `pane` to `window`:

```python
@agent_app.command("create")
def cmd_agent_create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    workspace: Optional[str] = typer.Option(None, help="Custom workspace path"),
    channels: Optional[str] = typer.Option(None, help="Comma-separated channels to join"),
    agent_type: Optional[str] = typer.Option(None, "--type", "-t", help="Template type (default: from config)"),
):
    """Create and launch a new agent."""
    mgr = _get_agent_manager(ctx)
    ch = [c.strip() for c in channels.split(",")] if channels else None
    info = mgr.create(name, workspace=workspace, channels=ch, agent_type=agent_type)
    scoped = mgr.scoped(name)
    typer.echo(f"Created {scoped} (type: {info['type']})")
    typer.echo(f"  window: {info['window_name']}")
    typer.echo(f"  workspace: {info['workspace']}")
```

- [ ] **Step 2: Update cmd_agent_list output**

In `cmd_agent_list`, change `pane` to `window`:

```python
        window = info.get("window_name", info.get("pane_id", "—"))
        # ... rest stays the same, just replace pane variable reference
        typer.echo(f"  {name}\t{agent_type}\t{status}\t{uptime}\t{window}\t{ch}\t{ws}")
```

- [ ] **Step 3: Update cmd_agent_status output**

In `cmd_agent_status`, change `pane` to `window`:

```python
    typer.echo(f"  window:    {info.get('window_name', info.get('pane_id', '—'))}")
```

- [ ] **Step 4: Update cmd_agent_send**

In `cmd_agent_send`, the `send()` method now uses window internally, but the output line references `pane_id` — update it:

```python
    mgr.send(name, text)
    typer.echo(f"Sent to {scoped}")
```

- [ ] **Step 5: Run unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add zchat/cli/app.py
git commit -m "refactor(cli): update agent commands for window model"
```

---

## Chunk 2: tmuxp declarative layout

### Task 5: Add tmuxp dependency and generate YAML on project create

**Files:**
- Modify: `pyproject.toml`
- Modify: `zchat/cli/project.py`
- Test: `tests/unit/test_project.py`

- [ ] **Step 1: Add tmuxp to pyproject.toml**

In `pyproject.toml`, add to dependencies:

```toml
    "pyyaml>=6.0",
    "tmuxp>=1.30.0",
```

- [ ] **Step 2: Install new dependency**

Run: `uv sync`

- [ ] **Step 3: Write failing test for tmuxp.yaml generation**

In `tests/unit/test_project.py`, add:

```python
import yaml

def test_create_project_generates_tmuxp_yaml(tmp_path, monkeypatch):
    """project create should generate tmuxp.yaml and bootstrap.sh."""
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("test-tmuxp", server="127.0.0.1", port=6667,
                          tls=False, password="", nick="", channels="#general")
    pdir = tmp_path / "projects" / "test-tmuxp"
    tmuxp_path = pdir / "tmuxp.yaml"
    bootstrap_path = pdir / "bootstrap.sh"
    assert tmuxp_path.exists()
    assert bootstrap_path.exists()
    # Verify YAML structure
    with open(tmuxp_path) as f:
        cfg = yaml.safe_load(f)
    assert cfg["session_name"].startswith("zchat-")
    assert cfg["before_script"] == str(bootstrap_path)
    assert str(pdir) in cfg["start_directory"]
    # Verify bootstrap.sh is executable
    assert os.access(str(bootstrap_path), os.X_OK)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_project.py::test_create_project_generates_tmuxp_yaml -v`
Expected: FAIL — `tmuxp.yaml` not created.

- [ ] **Step 5: Update create_project_config to generate tmuxp.yaml and bootstrap.sh**

In `zchat/cli/project.py`, add at the end of `create_project_config()`:

```python
    # Generate tmuxp.yaml
    import yaml
    tmuxp_config = {
        "session_name": tmux_session,
        "start_directory": pdir,
        "before_script": os.path.join(pdir, "bootstrap.sh"),
        "windows": [
            {"window_name": "main", "panes": ["blank"]},
        ],
    }
    with open(os.path.join(pdir, "tmuxp.yaml"), "w") as f:
        yaml.dump(tmuxp_config, f, default_flow_style=False)

    # Generate bootstrap.sh
    bootstrap_content = f'''#!/bin/bash
set -euo pipefail
PROJECT_DIR="{pdir}"
mkdir -p "$PROJECT_DIR/agents"
# Clean ready markers for agents not currently running
for f in "$PROJECT_DIR/agents"/*.ready; do
    [ -f "$f" ] || continue
    agent=$(basename "$f" .ready)
    if ! grep -q "\\"$agent\\".*\\"running\\"" "$PROJECT_DIR/state.json" 2>/dev/null; then
        rm -f "$f"
    fi
done
'''
    bootstrap_path = os.path.join(pdir, "bootstrap.sh")
    with open(bootstrap_path, "w") as f:
        f.write(bootstrap_content)
    os.chmod(bootstrap_path, 0o755)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_project.py -v`
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml zchat/cli/project.py tests/unit/test_project.py
git commit -m "feat(project): generate tmuxp.yaml and bootstrap.sh on create"
```

---

### Task 6: Update irc_manager to use tmuxp load + window model

**Files:**
- Modify: `zchat/cli/irc_manager.py`

- [ ] **Step 1: Update start_weechat to use session.new_window and tmuxp load**

Replace `start_weechat` method. The key changes: (1) use `tmuxp load -d` for initial session creation from YAML, (2) WeeChat gets its own window, (3) store `window_name` instead of `pane_id`:

```python
def start_weechat(self, nick_override: str | None = None):
    """Start WeeChat in tmux, auto-connect to IRC."""
    existing = self._state.get("irc", {}).get("weechat_window")
    if existing and self._window_alive(existing):
        print(f"WeeChat already running (window {existing}).")
        return

    # Load tmuxp session if YAML exists
    project_dir = os.path.dirname(self._state_file)
    tmuxp_path = os.path.join(project_dir, "tmuxp.yaml")
    if os.path.isfile(tmuxp_path):
        import subprocess as sp
        # Update YAML with WeeChat window before loading
        self._update_tmuxp_weechat(tmuxp_path, nick_override)
        sp.run(["tmuxp", "load", "-d", tmuxp_path], capture_output=True)
        # Refresh session reference after tmuxp creates it
        self._tmux_session = None  # force re-fetch

    server = self.irc_config.get("server", "127.0.0.1")
    port = self.irc_config.get("port", 6667)
    tls = self.irc_config.get("tls", False)
    nick = nick_override or self.config.get("agents", {}).get("username") or os.environ.get("USER", "user")
    channels = self.config.get("agents", {}).get("default_channels", ["#general"])
    tls_flag = "" if tls else " -notls"

    # SASL config
    sasl_cmds = ""
    from zchat.cli.auth import get_credentials
    creds = get_credentials()
    if creds:
        sasl_user, sasl_pass = creds
        nick = sasl_user
        sasl_cmds = (
            f"; /set irc.server.wc-local.sasl_mechanism PLAIN"
            f"; /set irc.server.wc-local.sasl_username {sasl_user}"
            f"; /set irc.server.wc-local.sasl_password {sasl_pass}"
        )

    # Source env file if configured
    env_file = self.config.get("agents", {}).get("env_file", "")
    source_env = f"[ -f '{env_file}' ] && set -a && source '{env_file}' && set +a; " if env_file else ""

    autojoin = ",".join(channels)
    plugin_path = self._find_weechat_plugin()
    load_plugin = f"; /script load {plugin_path}" if plugin_path else ""

    cmd = (
        f"{source_env}weechat -r '"
        f"/server add wc-local {server}/{port}{tls_flag} -nicks={nick}"
        f"; /set irc.server.wc-local.autojoin \"{autojoin}\""
        f"{sasl_cmds}"
        f"; /connect wc-local{load_plugin}'"
    )

    # Check if weechat window already exists (from tmuxp load)
    from zchat.cli.tmux import find_window
    weechat_window = find_window(self.tmux_session, "weechat")
    if weechat_window:
        # tmuxp created the window, send command to its pane
        pane = weechat_window.active_pane
        if pane:
            pane.send_keys(cmd, enter=True)
    else:
        # Create new window
        weechat_window = self.tmux_session.new_window(
            window_name="weechat", window_shell=cmd, attach=False,
        )

    self._state.setdefault("irc", {})["weechat_window"] = "weechat"
    self._save_state()
    print(f"WeeChat started (window weechat, nick {nick}).")

def _update_tmuxp_weechat(self, tmuxp_path: str, nick_override: str | None = None):
    """Update tmuxp.yaml to include WeeChat window."""
    import yaml
    with open(tmuxp_path) as f:
        cfg = yaml.safe_load(f)
    # Replace 'main' placeholder with weechat window
    cfg["windows"] = [
        {"window_name": "weechat", "panes": ["blank"], "focus": True},
    ]
    with open(tmuxp_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False)
```

- [ ] **Step 2: Update stop_weechat to kill window**

```python
def stop_weechat(self):
    """Stop WeeChat by sending /quit."""
    from zchat.cli.tmux import find_window
    window_name = self._state.get("irc", {}).get("weechat_window")
    if not window_name:
        # Legacy: try pane_id
        window_name = self._state.get("irc", {}).get("weechat_pane_id")
    if window_name and self._window_alive(window_name):
        window = find_window(self.tmux_session, window_name)
        if window and window.active_pane:
            window.active_pane.send_keys("/quit", enter=True)
        self._state.get("irc", {}).pop("weechat_window", None)
        self._state.get("irc", {}).pop("weechat_pane_id", None)
        self._save_state()
        print("WeeChat stopped.")
    else:
        print("WeeChat not running.")
```

- [ ] **Step 3: Update status() and _pane_alive references**

Add `_window_alive` method and update `status()`:

```python
def _window_alive(self, window_name: str) -> bool:
    from zchat.cli.tmux import window_alive
    return window_alive(self.tmux_session, window_name)

def status(self) -> dict:
    """Return IRC status info."""
    ergo_running = self._is_ergo_running()
    window_name = self._state.get("irc", {}).get("weechat_window")
    weechat_running = window_name and self._window_alive(window_name)
    return {
        "daemon": {
            "running": ergo_running,
            "pid": self._state.get("irc", {}).get("daemon_pid"),
            "server": self.irc_config.get("server"),
            "port": self.irc_config.get("port"),
        },
        "weechat": {
            "running": weechat_running,
            "window": window_name if weechat_running else None,
            "nick": self.config.get("agents", {}).get("username"),
        },
    }
```

- [ ] **Step 4: Remove unused _auth_config references**

The `_auth_config` field read from `config.get("auth", {})` (line 22) — since `[auth]` was removed from config.toml in PR #26, this should default to `{}`. The `_inject_auth_script` and SASL config in `start_weechat` should use `get_credentials()` directly (already done in the rewritten `start_weechat`). Remove line 22:

```python
# Remove: self._auth_config = config.get("auth", {})
```

And update `daemon_start` line 83:
```python
# Change: if self._auth_config.get("provider") == "oidc":
# To: check credentials directly
from zchat.cli.auth import get_credentials
if get_credentials():
    self._inject_auth_script(ergo_data_dir, ergo_conf)
```

- [ ] **Step 5: Run unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add zchat/cli/irc_manager.py
git commit -m "refactor(irc): use tmuxp load + window model for WeeChat

WeeChat gets its own tmux window. irc start uses tmuxp load -d to
create the session from YAML, then attaches."
```

---

## Chunk 3: Readiness detection + start.sh + E2E

### Task 7: Update start.sh with SessionStart hook

**Files:**
- Modify: `zchat/cli/templates/claude/start.sh`
- Modify: `zchat/cli/templates/claude/.env.example`

- [ ] **Step 1: Add ZCHAT_PROJECT_DIR to .env.example**

In `zchat/cli/templates/claude/.env.example`, add:

```
ZCHAT_PROJECT_DIR={{zchat_project_dir}}
```

- [ ] **Step 2: Rewrite start.sh with SessionStart hook**

Replace the settings.local.json section in `start.sh` to build it with `jq`, including the `SessionStart` hook:

```bash
# --- Claude settings with SessionStart hook ---
mkdir -p .claude
READY_PATH="${ZCHAT_PROJECT_DIR}/agents/${AGENT_NAME}.ready"

# Build settings.local.json with jq for correct JSON
jq -n \
  --arg ready_cmd "touch $READY_PATH" \
  '{
    hooks: {
      SessionStart: [{
        matcher: "startup",
        hooks: [{ type: "command", command: $ready_cmd }]
      }]
    },
    permissions: {
      allow: [
        "mcp__zchat-channel__reply",
        "mcp__zchat-channel__join_channel"
      ]
    },
    enabledPlugins: {
      "zchat@ezagent42": true
    }
  }' > .claude/settings.local.json
```

The rest of `start.sh` (MCP json, plugin symlink, exec claude) stays the same.

- [ ] **Step 3: Commit**

```bash
git add zchat/cli/templates/claude/start.sh zchat/cli/templates/claude/.env.example
git commit -m "feat(template): add SessionStart hook for ready marker

start.sh now writes a SessionStart hook that touches .ready marker
when Claude fully starts. Uses jq to build settings.local.json with
literal expanded paths."
```

---

### Task 8: Implement readiness detection in agent_manager

**Files:**
- Modify: `zchat/cli/agent_manager.py`
- Test: `tests/unit/test_agent_manager.py`

- [ ] **Step 1: Write test for _wait_for_ready**

```python
def test_wait_for_ready_detects_marker(tmp_path):
    """_wait_for_ready should return True when .ready file appears."""
    import threading
    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    # Create ready file after 0.5s in a thread
    def touch_ready():
        import time; time.sleep(0.5)
        (agents_dir / "alice-helper.ready").touch()
    t = threading.Thread(target=touch_ready, daemon=True)
    t.start()
    result = mgr._wait_for_ready("alice-helper", timeout=5)
    assert result is True


def test_wait_for_ready_timeout(tmp_path):
    """_wait_for_ready should return False on timeout."""
    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    (tmp_path / "agents").mkdir()
    result = mgr._wait_for_ready("alice-helper", timeout=1)
    assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_agent_manager.py::test_wait_for_ready_detects_marker tests/unit/test_agent_manager.py::test_wait_for_ready_timeout -v`
Expected: FAIL — `_wait_for_ready` not defined.

- [ ] **Step 3: Implement _wait_for_ready**

In `zchat/cli/agent_manager.py`, add method:

```python
def _wait_for_ready(self, name: str, timeout: int = 60) -> bool:
    """Poll for .agents/<name>.ready file. Returns True if found within timeout."""
    if not self.project_dir:
        return True  # no readiness check without project_dir
    ready_path = os.path.join(self.project_dir, "agents", f"{name}.ready")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.isfile(ready_path):
            return True
        time.sleep(0.5)
    return False
```

- [ ] **Step 4: Implement _auto_confirm_startup**

Add method:

```python
import threading

def _auto_confirm_startup(self, window_name: str, timeout: int = 60):
    """Background thread: poll capture-pane for confirmation prompts, send Enter."""
    from zchat.cli.tmux import find_window

    def _poll():
        deadline = time.time() + timeout
        confirm_patterns = ["I trust this folder", "local development", "Enter to confirm"]
        confirmed = set()  # track already-confirmed patterns to avoid duplicate Enter
        while time.time() < deadline:
            window = find_window(self.tmux_session, window_name)
            if not window or not window.active_pane:
                time.sleep(0.5)
                continue
            try:
                lines = window.active_pane.capture_pane()
                content = "\n".join(lines)
                sent = False
                for pattern in confirm_patterns:
                    if pattern in content and pattern not in confirmed:
                        window.active_pane.send_keys("", enter=True)
                        confirmed.add(pattern)
                        sent = True
                        time.sleep(1)  # wait for UI to update after Enter
                        break
                if not sent:
                    time.sleep(0.5)
            except Exception:
                time.sleep(0.5)

    thread = threading.Thread(target=_poll, daemon=True)
    thread.start()
```

- [ ] **Step 5: Wire readiness into _spawn_tmux**

Update `_spawn_tmux` to call both `_auto_confirm_startup` and `_wait_for_ready`:

After the `session.new_window()` call, replace the old Popen block:

```python
    # Start background confirmation polling
    self._auto_confirm_startup(window_name)
    return window_name
```

Update `create()` to wait for ready after spawn:

```python
    window_name = self._spawn_tmux(name, agent_workspace, agent_type, channels)

    self._agents[name] = {
        "type": agent_type,
        "workspace": agent_workspace,
        "window_name": window_name,
        "status": "starting",
        "created_at": time.time(),
        "channels": channels,
    }
    self._save_state()

    # Wait for ready marker (SessionStart hook)
    if self._wait_for_ready(name, timeout=60):
        self._agents[name]["status"] = "running"
    else:
        self._agents[name]["status"] = "error"
    self._save_state()
    return self._agents[name]
```

- [ ] **Step 6: Run all unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add zchat/cli/agent_manager.py tests/unit/test_agent_manager.py
git commit -m "feat(agent): readiness detection via SessionStart hook + capture-pane polling

Two-phase startup: background thread polls capture-pane for confirmation
prompts (folder trust + dev channel), sends Enter. Then polls for .ready
marker written by Claude's SessionStart hook."
```

---

### Task 9: Update shutdown to kill session

**Files:**
- Modify: `zchat/cli/app.py`

- [ ] **Step 1: Update cmd_shutdown**

Add session kill after stopping all components:

```python
@app.command("shutdown")
def cmd_shutdown(ctx: typer.Context):
    """Stop all agents + WeeChat + ergo + tmux session."""
    try:
        mgr = _get_agent_manager(ctx)
        agents = mgr.list_agents()
        for name in list(agents.keys()):
            if agents[name]["status"] != "offline":
                mgr.stop(name, force=True)
                typer.echo(f"Stopped {name}")
    except (SystemExit, Exception):
        pass
    try:
        irc = _get_irc_manager(ctx)
        irc.stop_weechat()
        irc.daemon_stop()
    except (SystemExit, Exception):
        pass
    # Kill tmux session
    try:
        session_name = _get_tmux_session(ctx)
        from zchat.cli.tmux import get_session
        session = get_session(session_name)
        session.kill()
    except (KeyError, SystemExit, Exception):
        pass
    typer.echo("Shutdown complete.")
```

- [ ] **Step 2: Commit**

```bash
git add zchat/cli/app.py
git commit -m "feat(shutdown): kill tmux session on shutdown"
```

---

### Task 10: Update E2E test fixtures

**Files:**
- Modify: `tests/e2e/conftest.py`

- [ ] **Step 1: Update e2e_context config.toml to include tmux session and default_type**

In `e2e_context` fixture, update the config.toml generation:

```python
    with open(os.path.join(project_dir, "config.toml"), "w") as f:
        f.write(f'[irc]\nserver = "127.0.0.1"\nport = {e2e_port}\ntls = false\npassword = ""\n\n')
        f.write('[agents]\ndefault_channels = ["#general"]\nusername = "alice"\n')
        f.write(f'default_type = "claude"\n')
        f.write(f'env_file = "{env_file_val}"\n')
        f.write(f'mcp_server_cmd = ["uv", "run", "--project", "{channel_server_dir}", "zchat-channel"]\n\n')
        f.write(f'[tmux]\nsession = "{tmux_session}"\n')
```

- [ ] **Step 2: Update weechat_pane fixture to use new_window**

Rename to `weechat_window` and use `session.new_window`:

```python
@pytest.fixture(scope="session")
def weechat_window(ergo_server, e2e_context, tmux_session):
    """Start WeeChat in its own tmux window."""
    from zchat.cli.tmux import get_session

    port = ergo_server["port"]
    weechat_dir = os.path.join(e2e_context["home"], "weechat")
    os.makedirs(weechat_dir, exist_ok=True)

    session = get_session(tmux_session)
    cmd = (
        f"weechat --dir {weechat_dir} -r '/server add wc-local 127.0.0.1/{port} -notls -nicks=alice; "
        f"/set irc.server.wc-local.autojoin \"#general\"; /connect wc-local'"
    )
    window = session.new_window(
        window_name="weechat", window_shell=cmd, attach=False,
    )
    time.sleep(5)  # Wait for WeeChat to connect
    yield window.window_name
    if window.active_pane:
        window.active_pane.send_keys("/quit", enter=True)
```

- [ ] **Step 3: Create agents directory in e2e_context**

Add `agents/` dir creation:

```python
    os.makedirs(os.path.join(project_dir, "agents"), exist_ok=True)
```

- [ ] **Step 4: Update test_e2e.py fixture references**

In `tests/e2e/test_e2e.py`, update any references from `weechat_pane` to `weechat_window`. Check if tests reference `pane:` in output parsing — update to `window:`.

- [ ] **Step 5: Run E2E tests**

Run: `uv run pytest tests/e2e/ -v -m e2e`
Expected: More tests pass than before (especially `test_second_agent`).

- [ ] **Step 6: Commit**

```bash
git add tests/e2e/conftest.py tests/e2e/test_e2e.py
git commit -m "test(e2e): update fixtures for window model and persistent workspaces"
```

---

### Task 11: Final verification

- [ ] **Step 1: Run all unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS.

- [ ] **Step 2: Run E2E tests**

Run: `uv run pytest tests/e2e/ -v -m e2e`
Expected: All PASS (or at least `test_second_agent` no longer flaky).

- [ ] **Step 3: Verify SessionStart hook works**

Manual test:
1. `zchat project create test-hook`
2. `zchat irc start`
3. `zchat agent create agent0`
4. Check: `ls ~/.zchat/projects/test-hook/agents/alice-agent0.ready`
   Expected: File exists.

- [ ] **Step 4: Commit any remaining changes**

```bash
git add -A
git commit -m "chore: final adjustments after integration testing"
```
