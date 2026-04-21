# zchat Monorepo Split Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the zchat monorepo into 4 independent packages with clean boundaries, configurable claude launch, and no hardcoded cross-module paths.

**Architecture:** Extract `zchat.protocol` into standalone `zchat-protocol` package. Remove `channel_server_dir` coupling from CLI — agent launch reads claude command/args from `config.toml`. Rename `weechat-channel-server` → `zchat-channel-server`. `weechat-zchat-plugin` stays as-is (already decoupled).

**Tech Stack:** Python 3.11+, hatchling, typer, libtmux, mcp[cli], irc

---

## Chunk 1: Extract zchat-protocol and Decouple CLI

### File Structure After Split

```
zchat-protocol/              # NEW standalone package
  zchat_protocol/
    __init__.py               # PROTOCOL_VERSION
    naming.py                 # scoped_name, AGENT_SEPARATOR
    sys_messages.py           # make_sys_message, encode/decode, etc.
  pyproject.toml
  tests/
    test_naming.py
    test_sys_messages.py

zchat/                        # CLI package (MODIFIED)
  zchat/
    cli/
      __init__.py
      __main__.py
      app.py                  # MODIFIED: remove channel_server_dir, add claude config
      agent_manager.py        # MODIFIED: remove _write_mcp_json, configurable launch
      irc_manager.py          # MODIFIED: remove hardcoded env_file path
      project.py              # MODIFIED: add env_file + claude_args to config.toml
      tmux.py                 # unchanged
  pyproject.toml              # MODIFIED: depend on zchat-protocol
  tests/
    test_agent_manager.py     # MODIFIED: remove channel_server_dir
    test_project.py

zchat-channel-server/         # RENAMED from weechat-channel-server
  server.py                   # MODIFIED: import from zchat_protocol
  message.py                  # unchanged
  .claude-plugin/
    plugin.json
  .mcp.json                   # MODIFIED: server name
  commands/                   # unchanged
  pyproject.toml              # MODIFIED: depend on zchat-protocol, rename
  tests/
    test_channel_server_irc.py

weechat-zchat-plugin/         # unchanged (already standalone)
  zchat.py
  tests/
    test_weechat_plugin.py
```

### Task 1: Create `zchat-protocol` package

**Files:**
- Create: `zchat-protocol/zchat_protocol/__init__.py`
- Create: `zchat-protocol/zchat_protocol/naming.py`
- Create: `zchat-protocol/zchat_protocol/sys_messages.py`
- Create: `zchat-protocol/pyproject.toml`
- Create: `zchat-protocol/tests/test_naming.py`
- Create: `zchat-protocol/tests/test_sys_messages.py`

- [ ] **Step 1: Create package structure**

```
mkdir -p zchat-protocol/zchat_protocol zchat-protocol/tests
```

- [ ] **Step 2: Write `zchat-protocol/pyproject.toml`**

```toml
[project]
name = "zchat-protocol"
version = "0.1.0"
description = "Protocol definitions for zchat multi-agent collaboration"
requires-python = ">=3.11"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[dependency-groups]
dev = [
    "pytest>=9.0.2",
]
```

- [ ] **Step 3: Move protocol files**

Copy `zchat/protocol/__init__.py` → `zchat-protocol/zchat_protocol/__init__.py`
Copy `zchat/protocol/naming.py` → `zchat-protocol/zchat_protocol/naming.py`
Copy `zchat/protocol/sys_messages.py` → `zchat-protocol/zchat_protocol/sys_messages.py`

The content stays identical except the module docstring in `__init__.py`:

```python
"""zchat protocol specification — authoritative definitions for naming, system messages, and commands."""

PROTOCOL_VERSION = "0.1"
```

- [ ] **Step 4: Write tests**

`zchat-protocol/tests/test_naming.py`:
```python
from zchat_protocol.naming import scoped_name, AGENT_SEPARATOR


def test_separator_is_dash():
    assert AGENT_SEPARATOR == "-"


def test_scoped_name_adds_prefix():
    assert scoped_name("helper", "alice") == "alice-helper"


def test_scoped_name_no_double_prefix():
    assert scoped_name("alice-helper", "alice") == "alice-helper"


def test_scoped_name_different_prefix():
    assert scoped_name("bob-helper", "alice") == "bob-helper"
```

`zchat-protocol/tests/test_sys_messages.py`:
```python
from zchat_protocol.sys_messages import (
    is_sys_message, make_sys_message,
    encode_sys_for_irc, decode_sys_from_irc,
    IRC_SYS_PREFIX,
)


def test_sys_prefix():
    assert IRC_SYS_PREFIX == "__zchat_sys:"


def test_make_sys_message_fields():
    msg = make_sys_message("alice-agent0", "sys.stop_request", {"reason": "test"})
    assert msg["nick"] == "alice-agent0"
    assert msg["type"] == "sys.stop_request"
    assert msg["body"]["reason"] == "test"
    assert "id" in msg
    assert "ts" in msg


def test_is_sys_message():
    assert is_sys_message({"type": "sys.stop_request"})
    assert not is_sys_message({"type": "msg"})


def test_irc_roundtrip():
    msg = make_sys_message("alice-agent0", "sys.stop_request", {"reason": "test"})
    encoded = encode_sys_for_irc(msg)
    assert encoded.startswith("__zchat_sys:")
    decoded = decode_sys_from_irc(encoded)
    assert decoded["type"] == "sys.stop_request"
    assert decoded["body"]["reason"] == "test"


def test_decode_non_sys():
    assert decode_sys_from_irc("hello world") is None
    assert decode_sys_from_irc("{json-like}") is None
```

- [ ] **Step 5: Run tests**

Run: `cd zchat-protocol && uv run pytest tests/ -v`
Expected: All 9 tests pass.

- [ ] **Step 6: Commit**

```bash
git add zchat-protocol/
git commit -m "feat: extract zchat-protocol as standalone package"
```

### Task 2: Add `env_file` and `claude_args` to project config

**Files:**
- Modify: `zchat/cli/project.py:14-30` (create_project_config)
- Modify: `zchat/cli/project.py:69-83` (load_project_config)
- Modify: `zchat/cli/app.py:136-151` (cmd_project_create)
- Modify: `tests/unit/test_project.py`

- [ ] **Step 1: Write failing test for new config fields**

Add to `tests/unit/test_project.py` (use `monkeypatch.setattr` to match existing test pattern — `ZCHAT_DIR` is evaluated at import time so `setenv` won't work):

```python
def test_config_has_agent_launch_fields(tmp_path, monkeypatch):
    """config.toml should support env_file and claude_args."""
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("test", server="127.0.0.1", port=6667, tls=False,
                          password="", nick="alice", channels="#general",
                          env_file="/path/to/env", claude_args=["--permission-mode", "bypassPermissions"])
    cfg = load_project_config("test")
    assert cfg["agents"]["env_file"] == "/path/to/env"
    assert cfg["agents"]["claude_args"] == ["--permission-mode", "bypassPermissions"]


def test_config_defaults_without_agent_launch_fields(tmp_path, monkeypatch):
    """env_file defaults to empty, claude_args has sensible defaults."""
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("test2", server="127.0.0.1", port=6667, tls=False,
                          password="", nick="alice", channels="#general")
    cfg = load_project_config("test2")
    assert cfg["agents"]["env_file"] == ""
    assert isinstance(cfg["agents"]["claude_args"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/h2oslabs/Workspace/zchat/.claude/worktrees/split-repo && uv run pytest tests/unit/test_project.py::test_config_has_agent_launch_fields -v`
Expected: FAIL — `create_project_config()` doesn't accept `env_file` or `claude_args`.

- [ ] **Step 3: Update `project.py` — `create_project_config()`**

Modify `zchat/cli/project.py`:

```python
def create_project_config(name: str, server: str, port: int, tls: bool,
                          password: str, nick: str, channels: str,
                          env_file: str = "", claude_args: list[str] | None = None):
    """Create project directory and write config.toml."""
    pdir = project_dir(name)
    os.makedirs(pdir, exist_ok=True)
    channels_list = [ch.strip() for ch in channels.split(",") if ch.strip()]
    channels_toml = ", ".join(f'"{ch}"' for ch in channels_list)
    if claude_args is None:
        claude_args = [
            "--permission-mode", "bypassPermissions",
            "--dangerously-load-development-channels", "server:zchat-channel",
        ]
    args_toml = ", ".join(f'"{a}"' for a in claude_args)
    config_content = f'''[irc]
server = "{server}"
port = {port}
tls = {"true" if tls else "false"}
password = "{password}"

[agents]
default_channels = [{channels_toml}]
username = "{nick}"
env_file = "{env_file}"
claude_args = [{args_toml}]
'''
    with open(os.path.join(pdir, "config.toml"), "w") as f:
        f.write(config_content)
```

- [ ] **Step 4: Update `project.py` — `load_project_config()` defaults**

Add defaults for new fields in `load_project_config()`:

```python
    agents.setdefault("env_file", "")
    agents.setdefault("claude_args", [
        "--permission-mode", "bypassPermissions",
        "--dangerously-load-development-channels", "server:zchat-channel",
    ])
```

- [ ] **Step 5: Update `app.py` — interactive prompt in `cmd_project_create`**

Add after the channels prompt (line 147):

```python
    env_file = typer.prompt("Environment file (proxy, API keys — leave empty if not needed)",
                            default="", show_default=False)
```

Pass to `create_project_config`:

```python
    create_project_config(name, server=server, port=port, tls=tls,
                          password=password, nick=nick, channels=channels,
                          env_file=env_file)
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/unit/test_project.py -v`
Expected: All tests pass including the two new ones.

- [ ] **Step 7: Commit**

```bash
git add zchat/cli/project.py zchat/cli/app.py tests/unit/test_project.py
git commit -m "feat: add env_file and claude_args to project config"
```

### Task 3: Remove `channel_server_dir` and `_write_mcp_json` from AgentManager

This is the core decoupling. AgentManager will:
- Read `env_file` and `claude_args` from config
- No longer generate `.mcp.json` (plugin system handles it)
- No longer know where channel-server lives on disk

**Important: IRC env vars (IRC_SERVER, IRC_PORT, IRC_CHANNELS, IRC_TLS, etc.)**
Previously `_write_mcp_json()` injected these into the MCP server's env. After removal,
the channel-server plugin receives them via Claude Code's plugin system — the `.mcp.json`
inside the plugin itself (not per-workspace) configures the MCP server. IRC connection
parameters are still passed as env vars but now set in the tmux pane environment by
`_spawn_tmux()`, and the plugin reads them at startup.

**Proxy note:** The old code set `no_proxy`/`NO_PROXY` in `.mcp.json` env block. After
this change, proxy bypass must be configured in the user's `env_file` or shell profile.

**Files:**
- Modify: `zchat/cli/agent_manager.py` (remove `channel_server_dir`, `_write_mcp_json`, refactor `_spawn_tmux`)
- Modify: `zchat/cli/app.py:51-64` (`_get_agent_manager` — remove `channel_server_dir`)
- Modify: `zchat/cli/app.py:184-198` (`cmd_project_remove` — remove `channel_server_dir`)
- Modify: `tests/unit/test_agent_manager.py`

- [ ] **Step 1: Write failing tests for new AgentManager signature**

Replace `tests/unit/test_agent_manager.py`:

```python
import os
import json
import tempfile

from zchat.cli.agent_manager import AgentManager


def _make_manager(state_file="/tmp/test-agents.json", env_file="", claude_args=None):
    return AgentManager(
        irc_server="localhost", irc_port=6667, irc_tls=False,
        username="alice", default_channels=["#general"],
        env_file=env_file,
        claude_args=claude_args or ["--permission-mode", "bypassPermissions"],
        state_file=state_file,
    )


def test_scope_agent_name():
    mgr = _make_manager()
    assert mgr.scoped("helper") == "alice-helper"
    assert mgr.scoped("alice-helper") == "alice-helper"


def test_create_workspace_no_mcp_json():
    """Workspace should NOT contain .mcp.json anymore (plugin system handles it)."""
    mgr = _make_manager(state_file="/tmp/test-agents-ws2.json")
    ws = mgr._create_workspace("alice-helper", ["#general"])
    assert os.path.isdir(ws)
    assert not os.path.exists(os.path.join(ws, ".mcp.json"))
    import shutil
    shutil.rmtree(ws)


def test_agent_state_persistence(tmp_path):
    state_file = str(tmp_path / "agents.json")
    mgr = _make_manager(state_file=state_file)
    mgr._agents["alice-helper"] = {
        "workspace": "/tmp/x", "pane_id": "%42", "status": "running",
        "created_at": 0, "channels": ["#general"],
    }
    mgr._save_state()
    mgr2 = _make_manager(state_file=state_file)
    assert "alice-helper" in mgr2._agents
    assert mgr2._agents["alice-helper"]["pane_id"] == "%42"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_agent_manager.py -v`
Expected: FAIL — `AgentManager.__init__()` still requires `channel_server_dir`.

- [ ] **Step 3: Rewrite `AgentManager.__init__` and remove `_write_mcp_json`**

Replace `zchat/cli/agent_manager.py`:

```python
"""Agent lifecycle management: create workspace, spawn tmux, track state."""

import json
import os
import shutil
import subprocess
import tempfile
import time

import libtmux

from zchat.cli.tmux import get_session, find_pane, pane_alive
from zchat_protocol.naming import scoped_name, AGENT_SEPARATOR


DEFAULT_STATE_FILE = os.path.expanduser("~/.local/state/zchat/agents.json")


class AgentManager:
    def __init__(self, irc_server: str, irc_port: int, irc_tls: bool,
                 username: str, default_channels: list[str],
                 env_file: str = "",
                 claude_args: list[str] | None = None,
                 tmux_session: str = "zchat",
                 state_file: str = DEFAULT_STATE_FILE):
        self.irc_server = irc_server
        self.irc_port = irc_port
        self.irc_tls = irc_tls
        self.username = username
        self.default_channels = default_channels
        self.env_file = env_file
        self.claude_args = claude_args or [
            "--permission-mode", "bypassPermissions",
            "--dangerously-load-development-channels", "server:zchat-channel",
        ]
        self._tmux_session_name = tmux_session
        self._tmux_session: libtmux.Session | None = None
        self._state_file = state_file
        self._agents: dict[str, dict] = {}
        self._load_state()

    @property
    def tmux_session(self) -> libtmux.Session:
        if self._tmux_session is None:
            self._tmux_session = get_session(self._tmux_session_name)
        return self._tmux_session

    def scoped(self, name: str) -> str:
        return scoped_name(name, self.username)

    def create(self, name: str, workspace: str | None = None, channels: list[str] | None = None) -> dict:
        """Create and launch a new agent. Returns agent info dict."""
        name = self.scoped(name)
        if name in self._agents and self._agents[name].get("status") == "running":
            raise ValueError(f"{name} already exists and is running")

        channels = channels or list(self.default_channels)
        agent_workspace = self._create_workspace(name, channels) if not workspace else workspace

        pane_id = self._spawn_tmux(name, agent_workspace)

        self._agents[name] = {
            "workspace": agent_workspace,
            "pane_id": pane_id,
            "status": "starting",
            "created_at": time.time(),
            "channels": channels,
        }
        self._save_state()
        return self._agents[name]

    def stop(self, name: str, force: bool = False):
        """Stop an agent."""
        name = self.scoped(name)
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        if agent["status"] == "offline":
            raise ValueError(f"{name} is already offline")
        self._force_stop(name)
        agent["status"] = "offline"
        self._cleanup_workspace(name)
        self._save_state()

    def restart(self, name: str):
        """Stop then re-create with same config."""
        name = self.scoped(name)
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        channels = list(agent.get("channels", self.default_channels))
        self.stop(name)
        base_name = name.split(AGENT_SEPARATOR, 1)[-1] if AGENT_SEPARATOR in name else name
        self.create(base_name, channels=channels)

    def list_agents(self) -> dict[str, dict]:
        """Return all agents with refreshed status."""
        for name, info in self._agents.items():
            if info.get("status") != "offline":
                info["status"] = self._check_alive(name)
        self._save_state()
        return dict(self._agents)

    def get_status(self, name: str) -> dict:
        name = self.scoped(name)
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        if agent["status"] != "offline":
            agent["status"] = self._check_alive(name)
        return agent

    def _create_workspace(self, name: str, channels: list[str]) -> str:
        safe = name.replace(AGENT_SEPARATOR, "_")
        workspace = os.path.join(tempfile.gettempdir(), f"zchat-{safe}")
        os.makedirs(workspace, exist_ok=True)
        return workspace

    def _spawn_tmux(self, name: str, workspace: str) -> str:
        source_env = ""
        if self.env_file:
            source_env = f"[ -f '{self.env_file}' ] && set -a && source '{self.env_file}' && set +a; "
        args_str = " ".join(self.claude_args)
        channels_str = ",".join(ch.lstrip("#") for ch in self.default_channels)
        cmd = (
            f"{source_env}"
            f"cd '{workspace}' && "
            f"AGENT_NAME='{name}' "
            f"IRC_SERVER='{self.irc_server}' "
            f"IRC_PORT='{self.irc_port}' "
            f"IRC_CHANNELS='{channels_str}' "
            f"IRC_TLS='{'true' if self.irc_tls else 'false'}' "
            f"claude {args_str}"
        )
        window = self.tmux_session.active_window
        pane = window.split(attach=False, direction=libtmux.constants.PaneDirection.Below, shell=cmd)
        pane_id = pane.pane_id
        pane.cmd("select-pane", "-T", f"agent: {name}")
        # Auto-confirm development channels prompt after 3s
        subprocess.Popen(
            ["bash", "-c", f"sleep 3 && tmux send-keys -t {pane_id} Enter"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return pane_id

    def _force_stop(self, name: str):
        agent = self._agents.get(name)
        if agent and agent.get("pane_id"):
            pane = find_pane(self.tmux_session, agent["pane_id"])
            if pane:
                pane.send_keys("/exit", enter=True)

    def _cleanup_workspace(self, name: str):
        agent = self._agents.get(name)
        if agent:
            ws = agent.get("workspace", "")
            if ws.startswith(tempfile.gettempdir()):
                shutil.rmtree(ws, ignore_errors=True)

    def _check_alive(self, name: str) -> str:
        agent = self._agents.get(name)
        if not agent or not agent.get("pane_id"):
            return "offline"
        if pane_alive(self.tmux_session, agent["pane_id"]):
            return "running"
        return "offline"

    def send(self, name: str, text: str):
        """Send text to agent's tmux pane."""
        name = self.scoped(name)
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        if self._check_alive(name) != "running":
            raise ValueError(f"{name} is not running")
        pane = find_pane(self.tmux_session, agent["pane_id"])
        if pane:
            pane.send_keys(text, enter=True)

    def _load_state(self):
        if os.path.isfile(self._state_file):
            try:
                with open(self._state_file) as f:
                    data = json.load(f)
                self._agents = data.get("agents", {})
            except (json.JSONDecodeError, OSError):
                self._agents = {}

    def _save_state(self):
        os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
        existing = {}
        if os.path.isfile(self._state_file):
            try:
                with open(self._state_file) as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        existing["agents"] = self._agents
        with open(self._state_file, "w") as f:
            json.dump(existing, f, indent=2)
```

- [ ] **Step 4: Update `app.py` — `_get_agent_manager()`**

Replace `_get_agent_manager` (lines 51-64):

```python
def _get_agent_manager(ctx: typer.Context) -> AgentManager:
    cfg = _get_config(ctx)
    project_name = ctx.obj["project"]
    return AgentManager(
        irc_server=cfg["irc"]["server"],
        irc_port=cfg["irc"]["port"],
        irc_tls=cfg["irc"].get("tls", False),
        username=cfg["agents"]["username"],
        default_channels=cfg["agents"]["default_channels"],
        env_file=cfg["agents"].get("env_file", ""),
        claude_args=cfg["agents"].get("claude_args"),
        tmux_session=ctx.obj.get("tmux_session", "zchat"),
        state_file=state_file_path(project_name),
    )
```

- [ ] **Step 5: Update `app.py` — `cmd_project_remove()`**

Replace the AgentManager construction in `cmd_project_remove` (lines 185-191):

```python
        mgr = AgentManager(
            irc_server=cfg["irc"]["server"], irc_port=cfg["irc"]["port"],
            irc_tls=cfg["irc"].get("tls", False),
            username=cfg["agents"]["username"],
            default_channels=cfg["agents"]["default_channels"],
            state_file=state_file_path(name),
        )
```

Remove the `script_dir` line (184) entirely.

- [ ] **Step 6: Remove `channel_server_dir` from `app.py` imports context**

Delete line 54 (`script_dir = ...`) from the old `_get_agent_manager`. Already handled in step 4.

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/unit/test_agent_manager.py tests/unit/test_project.py -v`
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add zchat/cli/agent_manager.py zchat/cli/app.py tests/unit/test_agent_manager.py
git commit -m "refactor: remove channel_server_dir coupling from AgentManager

Claude launch command now reads from config.toml (env_file, claude_args).
_write_mcp_json removed — plugin system handles MCP server registration."
```

### Task 4: Update irc_manager.py — remove hardcoded env_file path

**Files:**
- Modify: `zchat/cli/irc_manager.py:125-159` (start_weechat)
- Modify: `zchat/cli/app.py:41-48` (_get_irc_manager)

- [ ] **Step 1: Update `IrcManager` to accept `env_file`**

The constructor already takes `config` dict. Add reading `env_file` from config:

In `start_weechat()`, replace lines 139-142:

```python
        # Source env file if configured
        env_file = self.config.get("agents", {}).get("env_file", "")
        source_env = f"[ -f '{env_file}' ] && set -a && source '{env_file}' && set +a; " if env_file else ""
```

This replaces the hardcoded `script_dir` + `claude.local.env` path computation.

- [ ] **Step 2: Update weechat plugin path resolution**

Replace lines 146-149 (plugin path):

```python
        # Load zchat plugin — look in well-known locations
        plugin_path = self._find_weechat_plugin()
        load_plugin = f"; /script load {plugin_path}" if plugin_path else ""
```

Add method to `IrcManager`:

```python
    def _find_weechat_plugin(self) -> str | None:
        """Find zchat.py WeeChat plugin. Checks config, then common locations."""
        # Check config
        plugin_path = self.config.get("weechat", {}).get("plugin_path", "")
        if plugin_path and os.path.isfile(plugin_path):
            return plugin_path
        # Check common WeeChat locations
        candidates = [
            os.path.expanduser("~/.config/weechat/python/autoload/zchat.py"),  # XDG (WeeChat 4.x)
            os.path.expanduser("~/.weechat/python/autoload/zchat.py"),         # Legacy
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
        return None
```

- [ ] **Step 3: Run unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add zchat/cli/irc_manager.py
git commit -m "refactor: irc_manager reads env_file from config, no hardcoded paths"
```

### Task 5: Update imports to use `zchat_protocol`

**Files:**
- Modify: `zchat/cli/agent_manager.py:13` (already done in Task 3)
- Modify: `weechat-channel-server/server.py:12-16`
- Modify: `tests/unit/test_channel_server_irc.py:4-7`
- Modify: `tests/unit/test_weechat_plugin.py:4-11`
- Modify: `tests/unit/test_protocol.py`
- Modify: `pyproject.toml` (add zchat-protocol dependency)
- Modify: `weechat-channel-server/pyproject.toml` (add zchat-protocol dependency)

- [ ] **Step 1: Update root `pyproject.toml`**

Add `zchat-protocol` as dependency:

```toml
dependencies = [
    "libtmux>=0.55,<0.56",
    "typer[all]>=0.9.0",
    "zchat-protocol",
]
```

And add source for local development:

```toml
[tool.uv.sources]
zchat-protocol = { path = "zchat-protocol", editable = true }
```

- [ ] **Step 2: Update `weechat-channel-server/pyproject.toml`**

Add `zchat-protocol` dependency:

```toml
dependencies = [
    "mcp[cli]>=1.2.0",
    "irc>=20.0",
    "zchat-protocol",
]

[tool.uv.sources]
zchat-protocol = { path = "../zchat-protocol", editable = true }
```

- [ ] **Step 2.5: Install new dependency**

Run: `uv sync` from the repo root to install `zchat-protocol` as an editable dependency.
Also: `cd weechat-channel-server && uv sync` for the channel-server package.

- [ ] **Step 3: Update `server.py` imports**

In `weechat-channel-server/server.py`:
- Remove line 12 (`sys.path.insert(0, ...)`). Keep `import sys` and `import os` — they are still used elsewhere in the file.
- Replace lines 13-16 with:

```python
from zchat_protocol.sys_messages import (
    is_sys_message, make_sys_message,
    encode_sys_for_irc, decode_sys_from_irc,
)
```

- [ ] **Step 4: Update test imports**

`tests/unit/test_protocol.py` — change `zchat.protocol.naming` → `zchat_protocol.naming`:

```python
def test_scoped_name_adds_prefix():
    from zchat_protocol.naming import scoped_name
    assert scoped_name("helper", "alice") == "alice-helper"
```

`tests/unit/test_weechat_plugin.py` — change imports:

```python
from zchat_protocol.naming import scoped_name, AGENT_SEPARATOR
from zchat_protocol.sys_messages import (
    IRC_SYS_PREFIX, encode_sys_for_irc, decode_sys_from_irc, make_sys_message,
)
```

`tests/unit/test_channel_server_irc.py` — change imports:

```python
from zchat_protocol.sys_messages import encode_sys_for_irc, decode_sys_from_irc, make_sys_message
```

Remove `sys.path.insert` lines from `tests/unit/test_channel_server_irc.py`.

- [ ] **Step 5: Update `tests/conftest.py`**

Remove the `sys.path.insert` for weechat-channel-server (no longer needed for protocol imports). Keep the `agent_name` fixture:

```python
"""Shared test fixtures for zchat tests."""
import pytest


@pytest.fixture
def agent_name():
    """Default agent name for tests (scoped to creator per issue #2)."""
    return "alice-agent0"
```

Note: `test_channel_server_irc.py` still needs the channel-server on path for `from message import ...` and `from server import ...`. Add a local `sys.path.insert` in that test file only:

```python
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../weechat-channel-server"))
```

- [ ] **Step 6: Remove old protocol package from zchat**

Delete `zchat/protocol/` directory entirely. The CLI now imports from `zchat_protocol` (the new standalone package).

```bash
rm -rf zchat/protocol/
```

- [ ] **Step 7: Run all unit tests**

Run: `uv run pytest tests/unit/ -v && cd zchat-protocol && uv run pytest tests/ -v`
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git rm -r zchat/protocol/
git add pyproject.toml weechat-channel-server/pyproject.toml weechat-channel-server/server.py
git add tests/conftest.py tests/unit/test_protocol.py tests/unit/test_weechat_plugin.py
git add tests/unit/test_channel_server_irc.py
git commit -m "refactor: all modules import from zchat-protocol package

Remove zchat/protocol/ — replaced by standalone zchat-protocol package.
Remove sys.path hacks from server.py and tests."
```

---

## Chunk 2: Rename and Final Cleanup

### Task 6: Rename `weechat-channel-server` → `zchat-channel-server`

**Files:**
- Rename: `weechat-channel-server/` → `zchat-channel-server/`
- Modify: `zchat-channel-server/pyproject.toml` (package name)
- Modify: `zchat-channel-server/.mcp.json` (server key name: `weechat-channel` → `zchat-channel`)
- Modify: `zchat-channel-server/.claude-plugin/plugin.json`
- Modify: `zchat-channel-server/server.py` (lines 3, 194, 219, 295 — docstring, CHANNEL_INSTRUCTIONS source, Server name, server_name)
- Modify: `zchat-channel-server/message.py:2` (docstring)
- Modify: `zchat-channel-server/README.md` (all references)
- Modify: `zchat-channel-server/commands/reply.md:4` (`mcp__weechat-channel__reply` → `mcp__zchat-channel__reply`)
- Modify: `zchat-channel-server/commands/dm.md:4` (same)
- Modify: `zchat-channel-server/commands/broadcast.md:4` (same)
- Modify: `zchat-channel-server/commands/join.md:4` (`mcp__weechat-channel__join_channel` → `mcp__zchat-channel__join_channel`)
- Modify: `.claude/settings.local.json` (`mcp__weechat-channel__reply` → `mcp__zchat-channel__reply`)
- Modify: `start.sh:28` (`weechat-channel-server` → `zchat-channel-server`)
- Modify: `tests/unit/test_channel_server_irc.py` (path reference)
- Modify: `CLAUDE.md`

- [ ] **Step 1: Rename directory**

```bash
git mv weechat-channel-server zchat-channel-server
```

- [ ] **Step 2: Update `pyproject.toml`**

In `zchat-channel-server/pyproject.toml`:

```toml
[project]
name = "zchat-channel-server"
version = "0.2.0"
description = "Claude Code Channel MCP server bridging IRC and Claude Code"
```

Update scripts entry:
```toml
[project.scripts]
zchat-channel = "server:main"
```

Update sources path:
```toml
[tool.uv.sources]
zchat-protocol = { path = "../zchat-protocol", editable = true }
```

- [ ] **Step 3: Update `.mcp.json`**

```json
{
  "mcpServers": {
    "zchat-channel": {
      "command": "uv",
      "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}", "zchat-channel"]
    }
  }
}
```

- [ ] **Step 4: Update `server.py` references**

Line 3 docstring: `zchat-channel-server: Claude Code Channel MCP Server`
Line 194 in CHANNEL_INSTRUCTIONS: `source="weechat-channel"` → `source="zchat-channel"`
Line 219: `server = Server("zchat-channel", instructions=CHANNEL_INSTRUCTIONS)`
Line 295: `server_name=f"zchat-channel-{AGENT_NAME}",`

- [ ] **Step 4.5: Update `message.py` docstring**

Line 2: `Message utilities for weechat-channel-server.` → `Message utilities for zchat-channel-server.`

- [ ] **Step 4.6: Update `commands/*.md` tool references**

In all 4 files under `zchat-channel-server/commands/`:
- `reply.md:4`: `mcp__weechat-channel__reply` → `mcp__zchat-channel__reply`
- `dm.md:4`: `mcp__weechat-channel__reply` → `mcp__zchat-channel__reply`
- `broadcast.md:4`: `mcp__weechat-channel__reply` → `mcp__zchat-channel__reply`
- `join.md:4`: `mcp__weechat-channel__join_channel` → `mcp__zchat-channel__join_channel`

- [ ] **Step 4.7: Update `.claude/settings.local.json`**

```json
{
  "remote": {
    "defaultEnvironmentId": "env_018daiwEauC9WvRtcZD7A6to"
  },
  "permissions": {
    "allow": [
      "mcp__zchat-channel__reply"
    ]
  }
}
```

- [ ] **Step 4.8: Update `start.sh`**

Line 28: `weechat-channel-server` → `zchat-channel-server`

- [ ] **Step 4.9: Update `README.md`**

Replace all `weechat-channel-server` and `weechat-channel` references in `zchat-channel-server/README.md`.

- [ ] **Step 5: Update `plugin.json`**

```json
{
  "name": "zchat",
  "description": "IRC channel for Claude Code — reply, join, dm, broadcast via slash commands",
  "version": "0.2.0",
  "keywords": ["irc", "channel", "zchat"]
}
```

- [ ] **Step 6: Update test path reference**

In `tests/unit/test_channel_server_irc.py`, update:

```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../zchat-channel-server"))
```

- [ ] **Step 7: Update default `claude_args` everywhere**

The default `claude_args` in `project.py` and `agent_manager.py` already reference `server:zchat-channel`. Verify they match the new `.mcp.json` server key `"zchat-channel"`.

The `--dangerously-load-development-channels server:zchat-channel` flag: the `server:` prefix refers to the MCP server name in `.mcp.json`. Since we renamed from `weechat-channel` → `zchat-channel` in `.mcp.json`, the default args are correct.

- [ ] **Step 8: Update CLAUDE.md**

Replace all `weechat-channel-server` references with `zchat-channel-server`.
Replace `server:weechat-channel` with `server:zchat-channel`.

- [ ] **Step 9: Run all unit tests**

Run: `uv run pytest tests/unit/ -v && cd zchat-protocol && uv run pytest tests/ -v`
Expected: All pass.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: rename weechat-channel-server → zchat-channel-server"
```

### Task 7: Clean up — remove stale references and verify E2E

**Files:**
- Verify: all `weechat-channel-server` references gone
- Verify: no `sys.path.insert` hacks remain (except test_channel_server_irc for local imports)
- Verify: no `channel_server_dir` references remain

- [ ] **Step 1: Grep for stale references**

```bash
# Broad search — catches both "weechat-channel-server" and bare "weechat-channel"
grep -r "weechat-channel" --include="*.py" --include="*.toml" --include="*.md" --include="*.json" --include="*.sh" . | grep -v "docs/superpowers/"
grep -r "channel_server_dir" --include="*.py" .
grep -r "mcp__weechat" --include="*.py" --include="*.md" --include="*.json" .
```

Expected: No matches (docs/superpowers/plans/ and docs/superpowers/specs/ are historical and excluded).

- [ ] **Step 2: Run full unit test suite**

Run: `uv run pytest tests/unit/ -v && cd zchat-protocol && uv run pytest tests/ -v`
Expected: All pass.

- [ ] **Step 3: Run E2E tests**

Run: `pytest tests/e2e/ -v -m e2e`
Expected: All pass (requires ergo + tmux running).

Note: E2E tests exercise the full CLI → agent → IRC flow. They validate that:
- `config.toml` with `claude_args` actually launches claude correctly
- The renamed `zchat-channel` plugin loads via `--dangerously-load-development-channels`
- Agent join/stop/mention flows still work end-to-end

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "chore: clean up stale references after repo split"
```

---

## Summary of Breaking Changes

| Before | After |
|--------|-------|
| `from zchat.protocol.naming import ...` | `from zchat_protocol.naming import ...` |
| `from zchat.protocol.sys_messages import ...` | `from zchat_protocol.sys_messages import ...` |
| `AgentManager(channel_server_dir=...)` | `AgentManager(env_file=..., claude_args=...)` |
| `weechat-channel-server/` | `zchat-channel-server/` |
| `server:weechat-channel` (MCP server name) | `server:zchat-channel` |
| `mcp__weechat-channel__reply` (tool permission) | `mcp__zchat-channel__reply` |
| `mcp__weechat-channel__join_channel` | `mcp__zchat-channel__join_channel` |
| `source="weechat-channel"` (CHANNEL_INSTRUCTIONS) | `source="zchat-channel"` |
| `weechat-channel` (console script entry point) | `zchat-channel` |
| Hardcoded `claude.local.env` path | `env_file` in `config.toml` |
| Hardcoded claude launch flags | `claude_args` in `config.toml` |
| `_write_mcp_json()` generates `.mcp.json` | Plugin system handles MCP registration |
| IRC env vars in `.mcp.json` env block | IRC env vars exported in tmux pane |
| `no_proxy`/`NO_PROXY` set automatically | Must be in user's `env_file` or shell profile |

## Post-Split: Future Repo Extraction

After this plan completes, each directory is independently packageable:

```
zchat-protocol/       → github.com/ezagent42/zchat-protocol
zchat/                → github.com/ezagent42/zchat (CLI)
zchat-channel-server/ → github.com/ezagent42/zchat-channel-server (Claude plugin)
weechat-zchat-plugin/ → github.com/ezagent42/weechat-zchat-plugin
```

The actual git repo splitting (via `git filter-branch` or `git subtree split`) is a separate operation not covered by this plan.
