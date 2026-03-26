# wc-agent CLI Redesign Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure wc-agent from flat argparse CLI to Typer-based project/irc/agent subgroups with multi-project support.

**Architecture:** Typer app with three subgroups (project, irc, agent) + shutdown top-level command. Project system stores config/state in `~/.wc-agent/projects/<name>/`. AgentManager refactored to use project-relative state. server.py uses direct AgentManager import instead of CLI subprocess.

**Tech Stack:** Python 3.11+, Typer >=0.9, tomllib (stdlib), ergo IRC server

**Spec:** `docs/superpowers/specs/2026-03-26-wc-agent-cli-redesign.md`

---

## File Structure

### New files
```
wc-agent/project.py          # Project CRUD + resolution logic
wc-agent/irc_manager.py      # IRC daemon + WeeChat pane management
wc-agent/pyproject.toml      # Typer dependency + entry point
docs/e2e-manual-test.md      # Manual test guide
tests/unit/test_project.py   # Project system tests
tests/unit/test_irc_manager.py # IRC manager tests
```

### Rewrite
```
wc-agent/cli.py              # Full rewrite: argparse → Typer
```

### Modify
```
wc-agent/config.py           # Load from project dir
wc-agent/agent_manager.py    # Nested state schema, from_env(), send()
weechat-channel-server/server.py  # Direct AgentManager import
start.sh                     # New command format
stop.sh                      # New command format
tests/e2e/e2e-test.sh        # New command format
tests/e2e/e2e-test-manual.sh # Simplify
tests/e2e/helpers.sh          # Update wc_agent helper
```

### Delete
```
weechat-claude.toml           # Replaced by per-project config
```

---

## Chunk 1: Project System + Config

### Task 1: Create project.py — project CRUD and resolution

**Files:**
- Create: `wc-agent/project.py`
- Create: `tests/unit/test_project.py`

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_project.py
import os, sys, json, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from wc_agent.project import (
    WC_AGENT_DIR, project_dir, create_project_config,
    list_projects, get_default_project, set_default_project,
    resolve_project, load_project_config, remove_project,
)

def test_create_project_config(tmp_path, monkeypatch):
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
    create_project_config("test-proj", server="10.0.0.1", port=6667,
                          tls=False, password="", nick="alice", channels="#general")
    cfg_path = tmp_path / "projects" / "test-proj" / "config.toml"
    assert cfg_path.exists()
    import tomllib
    with open(cfg_path, "rb") as f:
        cfg = tomllib.load(f)
    assert cfg["irc"]["server"] == "10.0.0.1"
    assert cfg["agents"]["username"] == "alice"

def test_list_projects(tmp_path, monkeypatch):
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
    (tmp_path / "projects" / "a").mkdir(parents=True)
    (tmp_path / "projects" / "b").mkdir(parents=True)
    assert set(list_projects()) == {"a", "b"}

def test_default_project(tmp_path, monkeypatch):
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
    assert get_default_project() is None
    set_default_project("my-proj")
    assert get_default_project() == "my-proj"

def test_resolve_project_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
    assert resolve_project(explicit="my-proj") == "my-proj"

def test_resolve_project_from_cwd(tmp_path, monkeypatch):
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
    marker = tmp_path / ".wc-agent"
    marker.write_text("cwd-proj")
    monkeypatch.chdir(tmp_path)
    assert resolve_project() == "cwd-proj"

def test_resolve_project_from_default(tmp_path, monkeypatch):
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
    set_default_project("default-proj")
    assert resolve_project() == "default-proj"

def test_remove_project(tmp_path, monkeypatch):
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
    create_project_config("to-remove", server="localhost", port=6667,
                          tls=False, password="", nick="x", channels="#g")
    remove_project("to-remove")
    assert not (tmp_path / "projects" / "to-remove").exists()

def test_load_project_config(tmp_path, monkeypatch):
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
    create_project_config("cfg-test", server="10.0.0.1", port=6697,
                          tls=True, password="pw", nick="bob", channels="#dev,#general")
    cfg = load_project_config("cfg-test")
    assert cfg["irc"]["server"] == "10.0.0.1"
    assert cfg["irc"]["tls"] is True
    assert cfg["agents"]["username"] == "bob"
```

- [ ] **Step 2: Implement project.py**

```python
# wc-agent/project.py
"""Project management: create, list, use, remove, resolve."""
import os
import shutil
import tomllib

WC_AGENT_DIR = os.path.expanduser("~/.wc-agent")


def project_dir(name: str) -> str:
    return os.path.join(WC_AGENT_DIR, "projects", name)


def create_project_config(name: str, server: str, port: int, tls: bool,
                          password: str, nick: str, channels: str):
    """Create project directory and write config.toml."""
    pdir = project_dir(name)
    os.makedirs(pdir, exist_ok=True)
    channels_list = [ch.strip() for ch in channels.split(",") if ch.strip()]
    # Write TOML manually (no toml writer in stdlib)
    channels_toml = ", ".join(f'"{ch}"' for ch in channels_list)
    config_content = f'''[irc]
server = "{server}"
port = {port}
tls = {"true" if tls else "false"}
password = "{password}"

[agents]
default_channels = [{channels_toml}]
username = "{nick}"
'''
    with open(os.path.join(pdir, "config.toml"), "w") as f:
        f.write(config_content)


def list_projects() -> list[str]:
    projects_dir = os.path.join(WC_AGENT_DIR, "projects")
    if not os.path.isdir(projects_dir):
        return []
    return [d for d in os.listdir(projects_dir)
            if os.path.isdir(os.path.join(projects_dir, d))]


def get_default_project() -> str | None:
    default_file = os.path.join(WC_AGENT_DIR, "default")
    if os.path.isfile(default_file):
        return open(default_file).read().strip() or None
    return None


def set_default_project(name: str):
    os.makedirs(WC_AGENT_DIR, exist_ok=True)
    with open(os.path.join(WC_AGENT_DIR, "default"), "w") as f:
        f.write(name)


def resolve_project(explicit: str | None = None) -> str | None:
    """Resolve project: explicit > .wc-agent file > default."""
    if explicit:
        return explicit
    # Walk up from cwd
    path = os.getcwd()
    while path != "/":
        marker = os.path.join(path, ".wc-agent")
        if os.path.isfile(marker):
            return open(marker).read().strip() or None
        path = os.path.dirname(path)
    return get_default_project()


def load_project_config(name: str) -> dict:
    """Load and validate project config.toml."""
    config_path = os.path.join(project_dir(name), "config.toml")
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)
    # Defaults
    irc = cfg.setdefault("irc", {})
    irc.setdefault("server", "127.0.0.1")
    irc.setdefault("port", 6667)
    irc.setdefault("tls", False)
    irc.setdefault("password", "")
    agents = cfg.setdefault("agents", {})
    agents.setdefault("default_channels", ["#general"])
    if not agents.get("username"):
        agents["username"] = os.environ.get("USER", "user")
    return cfg


def remove_project(name: str):
    """Remove project directory."""
    pdir = project_dir(name)
    if os.path.isdir(pdir):
        shutil.rmtree(pdir)
```

- [ ] **Step 3: Run tests**
Run: `cd weechat-channel-server && uv run --with pytest python -m pytest ../tests/unit/test_project.py -v`

- [ ] **Step 4: Commit**
```bash
git add wc-agent/project.py tests/unit/test_project.py
git commit -m "feat: add project system — create, list, use, resolve, remove"
```

---

### Task 2: Create irc_manager.py — IRC daemon + WeeChat pane management

**Files:**
- Create: `wc-agent/irc_manager.py`

- [ ] **Step 1: Implement irc_manager.py**

```python
# wc-agent/irc_manager.py
"""IRC daemon (ergo) and WeeChat pane management."""
import json
import os
import subprocess
import time


class IrcManager:
    """Manage ergo IRC daemon and WeeChat tmux pane."""

    def __init__(self, config: dict, state_file: str, tmux_session: str = "weechat-claude"):
        self.config = config
        self._state_file = state_file
        self.tmux_session = tmux_session
        self._state: dict = {}
        self._load_state()

    @property
    def irc_config(self) -> dict:
        return self.config.get("irc", {})

    def daemon_start(self):
        """Start local ergo IRC server."""
        server = self.irc_config.get("server", "127.0.0.1")
        if server not in ("127.0.0.1", "localhost", "::1"):
            print(f"IRC server is remote ({server}), no local daemon needed.")
            return

        if self._is_ergo_running():
            pid = self._state.get("irc", {}).get("daemon_pid")
            print(f"ergo already running (pid {pid or 'unknown'}).")
            return

        ergo_data_dir = os.environ.get("ERGO_DATA_DIR",
                                        os.path.expanduser("~/.local/share/ergo"))
        os.makedirs(ergo_data_dir, exist_ok=True)

        # Find ergo.yaml — check project dir first, then script dir
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ergo_conf = os.path.join(script_dir, "ergo.yaml")
        if not os.path.isfile(ergo_conf):
            print("Error: ergo.yaml not found.")
            return

        proc = subprocess.Popen(
            ["ergo", "run", "--conf", ergo_conf],
            cwd=ergo_data_dir,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1)
        if proc.poll() is None:
            self._state.setdefault("irc", {})["daemon_pid"] = proc.pid
            self._save_state()
            port = self.irc_config.get("port", 6667)
            print(f"ergo running (pid {proc.pid}, port {port}).")
        else:
            print("Error: ergo failed to start.")

    def daemon_stop(self):
        """Stop local ergo IRC server."""
        subprocess.run(["pkill", "-x", "ergo"], capture_output=True)
        if "irc" in self._state:
            self._state["irc"].pop("daemon_pid", None)
            self._save_state()
        print("ergo stopped.")

    def start_weechat(self, nick_override: str | None = None):
        """Start WeeChat in tmux, auto-connect to IRC."""
        existing = self._state.get("irc", {}).get("weechat_pane_id")
        if existing and self._pane_alive(existing):
            print(f"WeeChat already running (pane {existing}).")
            return

        # Ensure tmux session exists
        subprocess.run(["tmux", "has-session", "-t", self.tmux_session],
                       capture_output=True)
        if subprocess.run(["tmux", "has-session", "-t", self.tmux_session],
                          capture_output=True).returncode != 0:
            subprocess.run(["tmux", "new-session", "-d", "-s", self.tmux_session,
                            "-x", "220", "-y", "60"])

        server = self.irc_config.get("server", "127.0.0.1")
        port = self.irc_config.get("port", 6667)
        tls = self.irc_config.get("tls", False)
        nick = nick_override or self.config.get("agents", {}).get("username") or os.environ.get("USER", "user")
        channels = self.config.get("agents", {}).get("default_channels", ["#general"])
        channels_str = "; ".join(f"/join {ch}" for ch in channels)
        tls_flag = "" if tls else " -notls"

        # Source proxy env if available
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_file = os.path.join(script_dir, "claude.local.env")
        source_env = f"[ -f '{env_file}' ] && set -a && source '{env_file}' && set +a; " if os.path.isfile(env_file) else ""

        cmd = f"{source_env}weechat -r '/server add wc-local {server}/{port}{tls_flag} -nicks={nick}; /connect wc-local; {channels_str}'"

        result = subprocess.run(
            ["tmux", "split-window", "-v", "-P", "-F", "#{pane_id}",
             "-t", self.tmux_session, cmd],
            capture_output=True, text=True,
        )
        pane_id = result.stdout.strip()
        self._state.setdefault("irc", {})["weechat_pane_id"] = pane_id
        self._save_state()
        print(f"WeeChat started (pane {pane_id}, nick {nick}).")

    def stop_weechat(self):
        """Stop WeeChat by sending /quit."""
        pane = self._state.get("irc", {}).get("weechat_pane_id")
        if pane and self._pane_alive(pane):
            subprocess.run(["tmux", "send-keys", "-t", pane, "/quit", "Enter"],
                           capture_output=True)
            self._state.get("irc", {}).pop("weechat_pane_id", None)
            self._save_state()
            print("WeeChat stopped.")
        else:
            print("WeeChat not running.")

    def status(self) -> dict:
        """Return IRC status info."""
        ergo_running = self._is_ergo_running()
        pane = self._state.get("irc", {}).get("weechat_pane_id")
        weechat_running = pane and self._pane_alive(pane)
        return {
            "daemon": {
                "running": ergo_running,
                "pid": self._state.get("irc", {}).get("daemon_pid"),
                "server": self.irc_config.get("server"),
                "port": self.irc_config.get("port"),
            },
            "weechat": {
                "running": weechat_running,
                "pane_id": pane if weechat_running else None,
                "nick": self.config.get("agents", {}).get("username"),
            },
        }

    def _is_ergo_running(self) -> bool:
        return subprocess.run(["pgrep", "-x", "ergo"],
                              capture_output=True).returncode == 0

    def _pane_alive(self, pane_id: str) -> bool:
        result = subprocess.run(["tmux", "list-panes", "-F", "#{pane_id}"],
                                capture_output=True, text=True)
        return pane_id in result.stdout

    def _load_state(self):
        if os.path.isfile(self._state_file):
            try:
                with open(self._state_file) as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._state = {}

    def _save_state(self):
        os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
        with open(self._state_file, "w") as f:
            json.dump(self._state, f, indent=2)
```

- [ ] **Step 2: Commit**
```bash
git add wc-agent/irc_manager.py
git commit -m "feat: add IrcManager for ergo daemon and WeeChat pane management"
```

---

### Task 3: Refactor agent_manager.py — nested state, from_env(), send()

**Files:**
- Modify: `wc-agent/agent_manager.py`

- [ ] **Step 1: Add send() method and from_env() classmethod, update state to use nested schema**

Key changes:
1. `_load_state` reads from `data.get("agents", {})`
2. `_save_state` reads existing state file first, updates only `"agents"` key
3. Add `send(name, text)` method — tmux send-keys
4. Add `from_env()` classmethod — construct from environment variables
5. Add `WC_PROJECT_DIR` to `.mcp.json` env in `_write_mcp_json()`

- [ ] **Step 2: Update existing tests**
Run: `cd weechat-channel-server && uv run --with pytest python -m pytest ../tests/unit/test_agent_manager.py -v`

- [ ] **Step 3: Commit**
```bash
git add wc-agent/agent_manager.py
git commit -m "refactor: AgentManager nested state schema, from_env(), send()"
```

---

## Chunk 2: Typer CLI + Rewiring

### Task 4: Add pyproject.toml for wc-agent

**Files:**
- Create: `wc-agent/pyproject.toml`

```toml
[project]
name = "wc-agent"
version = "0.1.0"
description = "Claude Code agent lifecycle management CLI"
requires-python = ">=3.11"
dependencies = ["typer[all]>=0.9.0"]

[project.scripts]
wc-agent = "wc_agent.cli:app"
```

- [ ] **Step 1: Create file and install deps**
```bash
cd wc-agent && uv sync
```

- [ ] **Step 2: Commit**
```bash
git add wc-agent/pyproject.toml
git commit -m "feat: add wc-agent pyproject.toml with Typer dependency"
```

---

### Task 5: Rewrite cli.py with Typer

**Files:**
- Rewrite: `wc-agent/cli.py`

Full rewrite from argparse to Typer with project/irc/agent subgroups. Uses `project.py` for project resolution, `IrcManager` for IRC commands, `AgentManager` for agent commands.

Key structure:
```python
import typer
app = typer.Typer(name="wc-agent")
project_app = typer.Typer()
irc_app = typer.Typer()
irc_daemon_app = typer.Typer()
agent_app = typer.Typer()

app.add_typer(project_app, name="project")
app.add_typer(irc_app, name="irc")
irc_app.add_typer(irc_daemon_app, name="daemon")
app.add_typer(agent_app, name="agent")

@app.callback()
def main(ctx, project, tmux_session): ...

@app.command("shutdown")
def shutdown(ctx): ...

# project commands: create, list, use, remove, show
# irc daemon: start, stop
# irc: start, stop, status
# agent: create, stop, list, status, send, restart
```

- [ ] **Step 1: Implement full cli.py**
- [ ] **Step 2: Test manually**: `uv run --project wc-agent python -m wc_agent.cli --help`
- [ ] **Step 3: Commit**
```bash
git add wc-agent/cli.py
git commit -m "feat: rewrite CLI with Typer — project/irc/agent subgroups"
```

---

### Task 6: Update server.py — direct AgentManager import

**Files:**
- Modify: `weechat-channel-server/server.py`

Replace `_handle_create_agent` subprocess call with direct `AgentManager.from_env()` import.

- [ ] **Step 1: Rewrite _handle_create_agent**

```python
async def _handle_create_agent(arguments: dict) -> list[TextContent]:
    """Create a new agent using AgentManager directly."""
    name = arguments["name"]
    username = AGENT_NAME.split("-")[0] if "-" in AGENT_NAME else AGENT_NAME
    from wc_protocol.naming import scoped_name
    scoped = scoped_name(name, username)

    try:
        from wc_agent.agent_manager import AgentManager
        mgr = AgentManager.from_env()
        info = mgr.create(scoped)
        output = f"Created {scoped} (pane: {info.get('pane_id', '?')})"
        print(f"[channel-server] {output}", file=sys.stderr)
        return [TextContent(type="text", text=output)]
    except Exception as e:
        return [TextContent(type="text", text=f"Failed to create agent {name}: {e}")]
```

- [ ] **Step 2: Remove old subprocess-based _handle_create_agent**
- [ ] **Step 3: Update test** — remove `test_create_agent_tool_cli_path` from test_channel_server_irc.py
- [ ] **Step 4: Commit**
```bash
git add weechat-channel-server/server.py tests/unit/test_channel_server_irc.py
git commit -m "refactor: server.py uses direct AgentManager import for create_agent"
```

---

## Chunk 3: Scripts + E2E + Docs

### Task 7: Update start.sh and stop.sh

**Files:**
- Modify: `start.sh`, `stop.sh`

- [ ] **Step 1: Rewrite start.sh** to use new CLI commands:
```bash
wc-agent --project "$PROJECT" irc daemon start
wc-agent --project "$PROJECT" irc start
wc-agent --project "$PROJECT" agent create agent0 --workspace "$WORKSPACE"
```

- [ ] **Step 2: Rewrite stop.sh** to use `wc-agent shutdown`

- [ ] **Step 3: Delete weechat-claude.toml**
```bash
rm weechat-claude.toml
```

- [ ] **Step 4: Commit**
```bash
git add start.sh stop.sh
git rm weechat-claude.toml
git commit -m "refactor: start.sh/stop.sh use new CLI, delete weechat-claude.toml"
```

---

### Task 8: Update E2E tests

**Files:**
- Modify: `tests/e2e/helpers.sh`, `tests/e2e/e2e-test.sh`, `tests/e2e/e2e-test-manual.sh`

Key changes:
- `helpers.sh`: Create test project in setup (`wc-agent project create ...`), update `wc_agent()` helper
- `e2e-test.sh`: Phase 0 creates project + starts daemon, Phase 1 uses `irc start` + `agent create`, all agent commands get `agent` prefix
- `e2e-test-manual.sh`: Same changes + simplify

- [ ] **Step 1: Update helpers.sh**
- [ ] **Step 2: Update e2e-test.sh**
- [ ] **Step 3: Update e2e-test-manual.sh**
- [ ] **Step 4: Commit**
```bash
git add tests/e2e/
git commit -m "refactor: e2e tests use new CLI command format"
```

---

### Task 9: Create manual test guide + update CLAUDE.md

**Files:**
- Create: `docs/e2e-manual-test.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Create docs/e2e-manual-test.md** — copy from spec's manual test guide section
- [ ] **Step 2: Update CLAUDE.md** — update commands section to reflect new CLI
- [ ] **Step 3: Commit**
```bash
git add docs/e2e-manual-test.md CLAUDE.md
git commit -m "docs: add manual test guide, update CLAUDE.md for new CLI"
```

---

### Task 10: Run full test suite + E2E

- [ ] **Step 1: Run unit tests**
```bash
cd weechat-channel-server && uv run --with pytest python -m pytest ../tests/unit/ -v
```

- [ ] **Step 2: Run E2E test**
```bash
bash tests/e2e/e2e-test.sh
```

- [ ] **Step 3: Fix any failures and commit**
