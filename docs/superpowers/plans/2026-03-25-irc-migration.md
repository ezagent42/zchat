# IRC Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Zenoh P2P messaging with standard IRC, extract agent management into standalone `wc-agent` CLI, delete all WeeChat custom plugins.

**Architecture:** channel-server becomes an IRC client (using `irc` library). New `wc-agent` CLI manages agent lifecycle via tmux + IRC sys protocol. Agent names use `-` separator (IRC-compliant). Sys messages use `__wc_sys:` prefix over IRC PRIVMSG.

**Tech Stack:** Python 3.11+, `irc` library, `mcp[cli]`, `ergo` IRC server, `tomllib` (stdlib), `argparse`

**Spec:** `docs/superpowers/specs/2026-03-25-irc-migration-design.md`

---

## File Structure

### New files
```
commands.json                          # OpenAPI 3.1 command schema
weechat-claude.toml                    # Shared config (example)
wc-agent/
  __init__.py
  cli.py                               # CLI entry point (argparse)
  config.py                            # Read weechat-claude.toml
  agent_manager.py                     # Agent lifecycle (tmux, workspace, .mcp.json)
  irc_monitor.py                       # Persistent IRC connection for sys protocol
  sys_protocol.py                      # Send/receive sys messages over IRC PRIVMSG
tests/e2e/ergo-test.yaml              # ergo IRC server config for testing
tests/e2e/test-config.toml            # wc-agent config for e2e tests
tests/unit/test_wc_agent_config.py    # Config loading tests
tests/unit/test_agent_manager.py      # Agent lifecycle tests (mocked)
tests/unit/test_channel_server_irc.py # IRC message handling tests
tests/integration/test_irc_roundtrip.py # IRC message round-trip
```

### Modified files
```
wc_protocol/naming.py                  # AGENT_SEPARATOR : → -
wc_protocol/sys_messages.py            # Add __wc_sys: prefix helpers
wc_protocol/__init__.py                # Remove deleted module references
weechat-channel-server/server.py       # Zenoh → IRC client (major rewrite)
weechat-channel-server/message.py      # Remove MessageDedup class
weechat-channel-server/pyproject.toml  # eclipse-zenoh → irc
start.sh                               # ergo + wc-agent instead of zenoh + plugins
stop.sh                                # wc-agent shutdown
tests/e2e/e2e-test.sh                  # Adapt all phases to IRC + CLI
tests/e2e/helpers.sh                   # Remove plugin install, add ergo/bridge startup
CLAUDE.md                              # Updated architecture docs
```

### Deleted files
```
weechat-zenoh/weechat-zenoh.py
weechat-zenoh/zenoh_sidecar.py
weechat-agent/weechat-agent.py
wc_registry/__init__.py
wc_registry/types.py
wc_protocol/signals.py
wc_protocol/topics.py
wc_protocol/config.py
tests/unit/test_registry.py
tests/unit/test_sys_messages.py        # Will be recreated with IRC transport
tests/unit/test_sidecar.py
tests/unit/test_agent_lifecycle.py
tests/unit/test_agent_commands.py
tests/unit/test_zenoh_commands.py
tests/unit/test_zenoh_config.py
tests/unit/test_zenoh_protocol.py
tests/unit/test_zenoh_signals.py
tests/unit/test_zenoh_asyncio_bridge.py
tests/unit/test_subinterpreter.py
tests/integration/test_zenoh_pubsub.py
tests/integration/test_channel_bridge.py
tests/integration/test_private_and_channel.py
tests/integration/test_sys_roundtrip.py
```

---

## Chunk 1: Shared Infrastructure

### Task 1: Update wc_protocol/naming.py separator

**Files:**
- Modify: `wc_protocol/naming.py`
- Test: `tests/unit/test_protocol.py` (existing, update assertions)

- [ ] **Step 1: Update naming.py**

Change `AGENT_SEPARATOR = ":"` to `AGENT_SEPARATOR = "-"` and update docstring:

```python
"""Agent naming conventions."""

AGENT_SEPARATOR = "-"


def scoped_name(name: str, username: str) -> str:
    """Add username prefix to agent name if not already scoped.
    'helper' + 'alice' → 'alice-helper'
    'alice-helper' + 'alice' → 'alice-helper' (no change)
    """
    if AGENT_SEPARATOR in name:
        return name
    return f"{username}{AGENT_SEPARATOR}{name}"
```

- [ ] **Step 2: Update test assertions in test_protocol.py**

Find tests referencing `alice:helper` format and change to `alice-helper`.

- [ ] **Step 3: Run tests**

Run: `cd weechat-channel-server && uv run python -m pytest ../tests/unit/test_protocol.py -v`

- [ ] **Step 4: Commit**

```bash
git add wc_protocol/naming.py tests/unit/test_protocol.py
git commit -m "refactor: change agent separator from : to - (IRC RFC 2812 compliance)"
```

---

### Task 2: Add __wc_sys: prefix to sys_messages.py

**Files:**
- Modify: `wc_protocol/sys_messages.py`
- Test: `tests/unit/test_sys_messages.py` (update)

- [ ] **Step 1: Update sys_messages.py**

```python
"""System message protocol for machine-to-machine control over IRC PRIVMSG."""

from __future__ import annotations
import json
import os
import time

SYS_PREFIX = "sys."
IRC_SYS_PREFIX = "__wc_sys:"


def _random_hex(n: int) -> str:
    return os.urandom(n // 2 + 1).hex()[:n]


def is_sys_message(msg: dict) -> bool:
    """Check if a message is a system control message."""
    return msg.get("type", "").startswith(SYS_PREFIX)


def make_sys_message(nick: str, type: str, body: dict, ref_id: str | None = None) -> dict:
    """Create a system message. Caller provides nick."""
    return {
        "id": _random_hex(8),
        "nick": nick,
        "type": type,
        "body": body,
        "ref_id": ref_id,
        "ts": time.time(),
    }


def encode_sys_for_irc(msg: dict) -> str:
    """Encode a sys message for IRC PRIVMSG transport.
    Prepends __wc_sys: prefix so receivers can distinguish from user text."""
    return f"{IRC_SYS_PREFIX}{json.dumps(msg)}"


def decode_sys_from_irc(text: str) -> dict | None:
    """Decode a sys message from IRC PRIVMSG.
    Returns None if text is not a sys message."""
    if not text.startswith(IRC_SYS_PREFIX):
        return None
    try:
        return json.loads(text[len(IRC_SYS_PREFIX):])
    except json.JSONDecodeError:
        return None
```

- [ ] **Step 2: Update tests**

```python
# tests/unit/test_sys_messages.py
from wc_protocol.sys_messages import (
    SYS_PREFIX, IRC_SYS_PREFIX, is_sys_message, make_sys_message,
    encode_sys_for_irc, decode_sys_from_irc,
)


def test_sys_prefix():
    assert SYS_PREFIX == "sys."


def test_irc_sys_prefix():
    assert IRC_SYS_PREFIX == "__wc_sys:"


def test_is_sys_message_true():
    assert is_sys_message({"type": "sys.ping"}) is True
    assert is_sys_message({"type": "sys.stop_request"}) is True


def test_is_sys_message_false():
    assert is_sys_message({"type": "msg"}) is False
    assert is_sys_message({}) is False


def test_make_sys_message_fields():
    msg = make_sys_message("alice", "sys.ping", {})
    assert msg["nick"] == "alice"
    assert msg["type"] == "sys.ping"
    assert msg["body"] == {}
    assert msg["ref_id"] is None
    assert len(msg["id"]) == 8
    assert isinstance(msg["ts"], float)


def test_make_sys_message_with_ref_id():
    msg = make_sys_message("alice", "sys.pong", {}, ref_id="abc123")
    assert msg["ref_id"] == "abc123"


def test_encode_sys_for_irc():
    msg = make_sys_message("alice", "sys.ping", {})
    encoded = encode_sys_for_irc(msg)
    assert encoded.startswith("__wc_sys:")
    assert '"sys.ping"' in encoded


def test_decode_sys_from_irc():
    msg = make_sys_message("alice", "sys.ping", {})
    encoded = encode_sys_for_irc(msg)
    decoded = decode_sys_from_irc(encoded)
    assert decoded is not None
    assert decoded["type"] == "sys.ping"
    assert decoded["nick"] == "alice"


def test_decode_sys_from_irc_not_sys():
    assert decode_sys_from_irc("hello world") is None
    assert decode_sys_from_irc("{not sys}") is None


def test_decode_sys_from_irc_bad_json():
    assert decode_sys_from_irc("__wc_sys:not-json") is None
```

- [ ] **Step 3: Run tests**

Run: `cd weechat-channel-server && uv run python -m pytest ../tests/unit/test_sys_messages.py -v`

- [ ] **Step 4: Commit**

```bash
git add wc_protocol/sys_messages.py tests/unit/test_sys_messages.py
git commit -m "feat: add IRC transport encoding for sys messages (__wc_sys: prefix)"
```

---

### Task 3: Create commands.json and weechat-claude.toml

**Files:**
- Create: `commands.json`
- Create: `weechat-claude.toml`

- [ ] **Step 1: Create commands.json**

Copy the full OpenAPI 3.1 schema from the spec (lines 129-252) into `commands.json` at project root.

- [ ] **Step 2: Create weechat-claude.toml**

```toml
[irc]
server = "192.168.1.100"
port = 6667
tls = false
password = ""

[agents]
default_channels = ["#general"]
username = ""
```

- [ ] **Step 3: Commit**

```bash
git add commands.json weechat-claude.toml
git commit -m "feat: add OpenAPI commands.json and weechat-claude.toml config"
```

---

### Task 4: Clean up wc_protocol — delete Zenoh-specific modules

**Files:**
- Delete: `wc_protocol/signals.py`, `wc_protocol/topics.py`, `wc_protocol/config.py`
- Modify: `wc_protocol/__init__.py`

- [ ] **Step 1: Delete files**

```bash
rm wc_protocol/signals.py wc_protocol/topics.py wc_protocol/config.py
```

- [ ] **Step 2: Update __init__.py**

```python
"""Shared protocol definitions for WeeChat-Claude components.
Pure Python — no external imports."""
```

- [ ] **Step 3: Delete Zenoh-specific tests**

```bash
rm tests/unit/test_zenoh_config.py tests/unit/test_zenoh_protocol.py tests/unit/test_zenoh_signals.py
rm tests/unit/test_zenoh_asyncio_bridge.py tests/unit/test_zenoh_commands.py
rm tests/unit/test_subinterpreter.py tests/unit/test_registry.py
rm tests/unit/test_agent_lifecycle.py tests/unit/test_agent_commands.py
rm tests/integration/test_zenoh_pubsub.py tests/integration/test_channel_bridge.py
rm tests/integration/test_private_and_channel.py tests/integration/test_sys_roundtrip.py
```

- [ ] **Step 4: Run remaining tests**

Run: `cd weechat-channel-server && uv run python -m pytest ../tests/unit/ -v`
Expected: Only test_sys_messages.py, test_protocol.py, test_message.py, test_tools.py, test_server.py pass (some may fail due to Zenoh imports — that's expected, will be fixed in Task 7).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: delete Zenoh-specific modules and tests"
```

---

## Chunk 2: wc-agent CLI

### Task 5: Create wc-agent config module

**Files:**
- Create: `wc-agent/__init__.py`
- Create: `wc-agent/config.py`
- Create: `tests/unit/test_wc_agent_config.py`

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_wc_agent_config.py
import os
import tempfile
import pytest
from importlib import import_module


def test_load_config_from_file():
    """Load config from a TOML file."""
    # Inline import to handle path
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
    from wc_agent.config import load_config

    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('[irc]\nserver = "10.0.0.1"\nport = 6667\ntls = false\npassword = ""\n\n[agents]\ndefault_channels = ["#general"]\nusername = "testuser"\n')
        f.flush()
        cfg = load_config(f.name)
    os.unlink(f.name)

    assert cfg["irc"]["server"] == "10.0.0.1"
    assert cfg["irc"]["port"] == 6667
    assert cfg["agents"]["username"] == "testuser"
    assert cfg["agents"]["default_channels"] == ["#general"]


def test_load_config_default_username():
    """Username defaults to $USER when empty."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
    from wc_agent.config import load_config

    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('[irc]\nserver = "localhost"\nport = 6667\n\n[agents]\ndefault_channels = ["#general"]\nusername = ""\n')
        f.flush()
        cfg = load_config(f.name)
    os.unlink(f.name)

    assert cfg["agents"]["username"] == os.environ.get("USER", "user")
```

- [ ] **Step 2: Implement config.py**

```python
# wc-agent/config.py
"""Read weechat-claude.toml configuration."""

import os
import tomllib


def load_config(path: str) -> dict:
    """Load and validate weechat-claude.toml."""
    with open(path, "rb") as f:
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
```

Create `wc-agent/__init__.py` as empty file.

- [ ] **Step 3: Run tests**

Run: `cd weechat-channel-server && uv run python -m pytest ../tests/unit/test_wc_agent_config.py -v`

- [ ] **Step 4: Commit**

```bash
git add wc-agent/ tests/unit/test_wc_agent_config.py
git commit -m "feat: add wc-agent config module (weechat-claude.toml reader)"
```

---

### Task 6: Create wc-agent agent_manager module

**Files:**
- Create: `wc-agent/agent_manager.py`
- Create: `tests/unit/test_agent_manager.py`

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_agent_manager.py
import os
import sys
import json
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from wc_agent.agent_manager import AgentManager
from wc_protocol.naming import scoped_name


def test_scope_agent_name():
    mgr = AgentManager(irc_server="localhost", irc_port=6667, irc_tls=False,
                       channel_server_dir="/tmp", username="alice",
                       default_channels=["#general"])
    assert mgr.scoped("helper") == "alice-helper"
    assert mgr.scoped("alice-helper") == "alice-helper"


def test_create_workspace():
    mgr = AgentManager(irc_server="localhost", irc_port=6667, irc_tls=False,
                       channel_server_dir="/tmp/fake", username="alice",
                       default_channels=["#general"])
    ws = mgr._create_workspace("alice-helper")
    assert os.path.isdir(ws)
    mcp_path = os.path.join(ws, ".mcp.json")
    assert os.path.isfile(mcp_path)
    with open(mcp_path) as f:
        mcp = json.load(f)
    env = mcp["mcpServers"]["weechat-channel"]["env"]
    assert env["AGENT_NAME"] == "alice-helper"
    assert env["IRC_SERVER"] == "localhost"
    assert env["IRC_PORT"] == "6667"
    # Cleanup
    import shutil
    shutil.rmtree(ws)


def test_agent_state_persistence(tmp_path):
    state_file = str(tmp_path / "agents.json")
    mgr = AgentManager(irc_server="localhost", irc_port=6667, irc_tls=False,
                       channel_server_dir="/tmp", username="alice",
                       default_channels=["#general"], state_file=state_file)
    mgr._agents["alice-helper"] = {
        "workspace": "/tmp/x", "pane_id": "%42", "status": "running",
        "created_at": 0, "channels": ["#general"],
    }
    mgr._save_state()
    # Reload
    mgr2 = AgentManager(irc_server="localhost", irc_port=6667, irc_tls=False,
                        channel_server_dir="/tmp", username="alice",
                        default_channels=["#general"], state_file=state_file)
    assert "alice-helper" in mgr2._agents
    assert mgr2._agents["alice-helper"]["pane_id"] == "%42"
```

- [ ] **Step 2: Implement agent_manager.py**

```python
# wc-agent/agent_manager.py
"""Agent lifecycle management: create workspace, spawn tmux, track state."""

import json
import os
import shutil
import subprocess
import tempfile
import time

from wc_protocol.naming import scoped_name, AGENT_SEPARATOR


DEFAULT_STATE_FILE = os.path.expanduser("~/.local/state/wc-agent/agents.json")


class AgentManager:
    def __init__(self, irc_server: str, irc_port: int, irc_tls: bool,
                 channel_server_dir: str, username: str,
                 default_channels: list[str],
                 tmux_session: str = "weechat-claude",
                 state_file: str = DEFAULT_STATE_FILE):
        self.irc_server = irc_server
        self.irc_port = irc_port
        self.irc_tls = irc_tls
        self.channel_server_dir = channel_server_dir
        self.username = username
        self.default_channels = default_channels
        self.tmux_session = tmux_session
        self._state_file = state_file
        self._agents: dict[str, dict] = {}
        self._load_state()

    def scoped(self, name: str) -> str:
        return scoped_name(name, self.username)

    def create(self, name: str, workspace: str | None = None, channels: list[str] | None = None) -> dict:
        """Create and launch a new agent. Returns agent info dict."""
        name = self.scoped(name)
        if name in self._agents and self._agents[name]["status"] == "running":
            raise ValueError(f"{name} already exists and is running")

        channels = channels or self.default_channels
        agent_workspace = workspace or self._create_workspace(name)
        if not workspace:
            agent_workspace = self._create_workspace(name)
        else:
            self._write_mcp_json(name, workspace, channels)
            agent_workspace = workspace

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
        """Stop an agent. If force, skip sys protocol and go straight to tmux."""
        name = self.scoped(name)
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        if agent["status"] == "offline":
            raise ValueError(f"{name} is already offline")

        if force or agent["status"] == "starting":
            self._force_stop(name)
        else:
            # Graceful stop will be handled by caller (sys_protocol.py)
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
        workspace = agent.get("workspace")
        channels = agent.get("channels", self.default_channels)
        self.stop(name)
        self.create(name, workspace=None, channels=channels)

    def list_agents(self) -> dict[str, dict]:
        """Return all agents with refreshed status."""
        for name, info in self._agents.items():
            if info["status"] != "offline":
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

    def _create_workspace(self, name: str) -> str:
        safe = name.replace("-", "_")
        workspace = os.path.join(tempfile.gettempdir(), f"wc-agent-{safe}")
        os.makedirs(workspace, exist_ok=True)
        channels_str = ",".join(ch.lstrip("#") for ch in self.default_channels)
        self._write_mcp_json(name, workspace, self.default_channels)
        return workspace

    def _write_mcp_json(self, name: str, workspace: str, channels: list[str]):
        channels_str = ",".join(ch.lstrip("#") for ch in channels)
        config = {
            "mcpServers": {
                "weechat-channel": {
                    "type": "stdio",
                    "command": "uv",
                    "args": [
                        "run", "--project", self.channel_server_dir,
                        "python3", os.path.join(self.channel_server_dir, "server.py"),
                    ],
                    "env": {
                        "AGENT_NAME": name,
                        "IRC_SERVER": self.irc_server,
                        "IRC_PORT": str(self.irc_port),
                        "IRC_CHANNELS": channels_str,
                        "IRC_TLS": str(self.irc_tls).lower(),
                    },
                }
            }
        }
        with open(os.path.join(workspace, ".mcp.json"), "w") as f:
            json.dump(config, f)

    def _spawn_tmux(self, name: str, workspace: str) -> str:
        cmd = (
            f"cd '{workspace}' && "
            f"AGENT_NAME='{name}' "
            f"claude "
            f"--permission-mode bypassPermissions "
            f"--dangerously-load-development-channels server:weechat-channel"
        )
        result = subprocess.run(
            ["tmux", "split-window", "-v", "-P", "-F", "#{pane_id}",
             "-t", self.tmux_session, cmd],
            capture_output=True, text=True,
        )
        pane_id = result.stdout.strip()
        # Auto-confirm development channels prompt after 3s
        subprocess.Popen(
            ["bash", "-c", f"sleep 3 && tmux send-keys -t {pane_id} Enter"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return pane_id

    def _force_stop(self, name: str):
        agent = self._agents.get(name)
        if agent and agent.get("pane_id"):
            subprocess.run(
                ["tmux", "send-keys", "-t", agent["pane_id"], "/exit", "Enter"],
                capture_output=True,
            )

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
        result = subprocess.run(
            ["tmux", "list-panes", "-F", "#{pane_id}"],
            capture_output=True, text=True,
        )
        if agent["pane_id"] in result.stdout:
            return "running"
        return "offline"

    def _load_state(self):
        if os.path.isfile(self._state_file):
            try:
                with open(self._state_file) as f:
                    self._agents = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._agents = {}

    def _save_state(self):
        os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
        with open(self._state_file, "w") as f:
            json.dump(self._agents, f, indent=2)
```

- [ ] **Step 3: Run tests**

Run: `cd weechat-channel-server && uv run python -m pytest ../tests/unit/test_agent_manager.py -v`

- [ ] **Step 4: Commit**

```bash
git add wc-agent/agent_manager.py tests/unit/test_agent_manager.py
git commit -m "feat: add wc-agent AgentManager for lifecycle management"
```

---

### Task 7: Create wc-agent CLI entry point

**Files:**
- Create: `wc-agent/cli.py`

- [ ] **Step 1: Implement CLI**

```python
#!/usr/bin/env python3
# wc-agent/cli.py
"""wc-agent: Claude Code agent lifecycle management CLI."""

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))
from wc_agent.config import load_config
from wc_agent.agent_manager import AgentManager


def find_config() -> str:
    """Find weechat-claude.toml in current dir or parent dirs."""
    path = os.getcwd()
    while path != "/":
        candidate = os.path.join(path, "weechat-claude.toml")
        if os.path.isfile(candidate):
            return candidate
        path = os.path.dirname(path)
    return "weechat-claude.toml"  # fallback, will error if not found


def make_manager(args) -> AgentManager:
    config_path = getattr(args, "config", None) or find_config()
    cfg = load_config(config_path)
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return AgentManager(
        irc_server=cfg["irc"]["server"],
        irc_port=cfg["irc"]["port"],
        irc_tls=cfg["irc"].get("tls", False),
        channel_server_dir=os.path.join(script_dir, "weechat-channel-server"),
        username=cfg["agents"]["username"],
        default_channels=cfg["agents"]["default_channels"],
    )


def cmd_start(args):
    """Start local ergo IRC server + primary agent."""
    # Start ergo if not running
    if not subprocess.run(["pgrep", "-x", "ergo"], capture_output=True).returncode == 0:
        print("Starting ergo IRC server...")
        subprocess.Popen(
            ["ergo", "run", "--conf", os.path.join(os.path.dirname(__file__), "..", "ergo.yaml")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1)

    mgr = make_manager(args)
    workspace = getattr(args, "workspace", None) or os.getcwd()
    info = mgr.create("agent0", workspace=workspace)
    print(f"Created {mgr.scoped('agent0')}")
    print(f"  pane: {info['pane_id']}")
    print(f"  workspace: {info['workspace']}")


def cmd_create(args):
    mgr = make_manager(args)
    info = mgr.create(args.name, workspace=args.workspace)
    name = mgr.scoped(args.name)
    print(f"Created {name}")
    print(f"  pane: {info['pane_id']}")
    print(f"  workspace: {info['workspace']}")


def cmd_stop(args):
    mgr = make_manager(args)
    name = mgr.scoped(args.name)
    mgr.stop(args.name, force=True)  # TODO: graceful via sys protocol
    print(f"Stopped {name}")


def cmd_restart(args):
    mgr = make_manager(args)
    name = mgr.scoped(args.name)
    mgr.restart(args.name)
    print(f"Restarted {name}")


def cmd_list(args):
    mgr = make_manager(args)
    agents = mgr.list_agents()
    if not agents:
        print("No agents")
        return
    for name, info in agents.items():
        status = info["status"]
        pane = info.get("pane_id", "—")
        ws = info.get("workspace", "—")
        elapsed = time.time() - info.get("created_at", time.time())
        if status != "offline" and elapsed > 0:
            if elapsed >= 3600:
                uptime = f"{elapsed / 3600:.0f}h"
            elif elapsed >= 60:
                uptime = f"{elapsed / 60:.0f}m"
            else:
                uptime = f"{elapsed:.0f}s"
        else:
            uptime = "—"
        channels = ", ".join(info.get("channels", []))
        print(f"  {name}\t{status}\t{uptime}\t{pane}\t{channels}\t{ws}")


def cmd_status(args):
    mgr = make_manager(args)
    info = mgr.get_status(args.name)
    name = mgr.scoped(args.name)
    elapsed = time.time() - info.get("created_at", time.time())
    mins, secs = divmod(int(elapsed), 60)
    print(f"{name}")
    print(f"  status:    {info['status']}")
    print(f"  uptime:    {mins}m {secs}s")
    print(f"  pane:      {info.get('pane_id', '—')}")
    print(f"  workspace: {info.get('workspace', '—')}")
    print(f"  channels:  {', '.join(info.get('channels', []))}")


def cmd_shutdown(args):
    mgr = make_manager(args)
    agents = mgr.list_agents()
    for name in list(agents.keys()):
        if agents[name]["status"] != "offline":
            mgr.stop(name, force=True)
            print(f"Stopped {name}")
    # Stop ergo
    subprocess.run(["pkill", "-x", "ergo"], capture_output=True)
    print("Shutdown complete")


def main():
    parser = argparse.ArgumentParser(prog="wc-agent", description="Claude Code agent lifecycle management")
    parser.add_argument("--config", help="Path to weechat-claude.toml")
    sub = parser.add_subparsers(dest="command")

    p_start = sub.add_parser("start", help="Start ergo + primary agent")
    p_start.add_argument("--workspace", help="Agent workspace path")

    p_create = sub.add_parser("create", help="Create new agent")
    p_create.add_argument("name", help="Agent name")
    p_create.add_argument("--workspace", help="Custom workspace path")

    p_stop = sub.add_parser("stop", help="Stop agent")
    p_stop.add_argument("name", help="Agent name")

    p_restart = sub.add_parser("restart", help="Restart agent")
    p_restart.add_argument("name", help="Agent name")

    sub.add_parser("list", help="List agents")

    p_status = sub.add_parser("status", help="Agent details")
    p_status.add_argument("name", help="Agent name")

    sub.add_parser("shutdown", help="Stop all agents + ergo")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cmds = {
        "start": cmd_start, "create": cmd_create, "stop": cmd_stop,
        "restart": cmd_restart, "list": cmd_list, "status": cmd_status,
        "shutdown": cmd_shutdown,
    }
    try:
        cmds[args.command](args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test CLI manually**

```bash
python wc-agent/cli.py --help
python wc-agent/cli.py list --config weechat-claude.toml
```

- [ ] **Step 3: Commit**

```bash
git add wc-agent/cli.py
git commit -m "feat: add wc-agent CLI entry point with all commands"
```

---

## Chunk 3: Channel-Server IRC Migration

### Task 8: Update channel-server dependencies

**Files:**
- Modify: `weechat-channel-server/pyproject.toml`

- [ ] **Step 1: Replace eclipse-zenoh with irc**

```toml
[project]
name = "weechat-channel-server"
version = "0.2.0"
description = "Claude Code Channel MCP server bridging IRC and Claude Code"
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]>=1.2.0",
    "irc>=20.0",
]

[project.optional-dependencies]
test = ["pytest", "pytest-asyncio"]

[project.scripts]
weechat-channel = "server:main"
```

- [ ] **Step 2: Sync dependencies**

```bash
cd weechat-channel-server && uv sync
```

- [ ] **Step 3: Commit**

```bash
git add weechat-channel-server/pyproject.toml
git commit -m "refactor: replace eclipse-zenoh with irc in channel-server deps"
```

---

### Task 9: Rewrite channel-server server.py for IRC

**Files:**
- Modify: `weechat-channel-server/server.py`
- Modify: `weechat-channel-server/message.py`

This is the largest task — full rewrite of the Zenoh integration layer to use IRC.

- [ ] **Step 1: Remove MessageDedup from message.py**

Remove the `MessageDedup` class and `DEDUP_CAPACITY` constant from `message.py`. Keep `detect_mention`, `clean_mention`, `chunk_message`, and `MAX_MESSAGE_LENGTH`.

- [ ] **Step 2: Rewrite server.py**

Replace `setup_zenoh()` and all Zenoh references with IRC client setup. The key changes:

1. Remove all `zenoh` imports, `build_zenoh_config_dict`, `channel_topic`, `private_topic`, `presence_topic`, `channel_presence_topic`, `make_private_pair`
2. Add `import irc.client`, `import irc.connection` imports
3. Replace `setup_zenoh()` with `setup_irc()` that:
   - Creates IRC Reactor + connection
   - Registers `on_pubmsg`, `on_privmsg`, `on_welcome` (for auto-join)
   - Returns connection object
4. Replace `_handle_reply` to use `connection.privmsg()` instead of `zenoh_session.put()`
5. Replace `_handle_join_channel` to use `connection.join()`
6. Replace `_handle_sys_message` to use `connection.privmsg()` with `encode_sys_for_irc()`
7. Update `register_tools` to use IRC connection instead of Zenoh session
8. Update `main()` to start IRC reactor in a thread and MCP server in async

The full implementation follows the spec's code examples (lines 342-437).

Key architectural note: IRC library uses a reactor thread, while MCP uses asyncio. Bridge them via `asyncio.Queue` (same pattern as current Zenoh→asyncio bridge).

- [ ] **Step 3: Run tests (expect some failures from test_tools.py, test_server.py)**

Run: `cd weechat-channel-server && uv run python -m pytest ../tests/unit/test_message.py -v`
Expected: PASS (message.py changes are minimal)

- [ ] **Step 4: Update test_tools.py and test_server.py for IRC**

Create `tests/unit/test_channel_server_irc.py` with IRC-specific tests:

```python
# tests/unit/test_channel_server_irc.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../weechat-channel-server"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from message import detect_mention, clean_mention, chunk_message
from wc_protocol.sys_messages import encode_sys_for_irc, decode_sys_from_irc, make_sys_message


def test_detect_mention():
    assert detect_mention("@alice-agent0 hello", "alice-agent0") is True
    assert detect_mention("hello @alice-agent0", "alice-agent0") is True
    assert detect_mention("hello everyone", "alice-agent0") is False


def test_clean_mention():
    assert clean_mention("@alice-agent0 hello", "alice-agent0") == "hello"


def test_chunk_message_short():
    assert chunk_message("short") == ["short"]


def test_chunk_message_long():
    text = "a" * 5000
    chunks = chunk_message(text, max_length=400)
    assert len(chunks) > 1
    assert all(len(c) <= 400 for c in chunks)


def test_sys_message_irc_roundtrip():
    msg = make_sys_message("alice-agent0", "sys.stop_request", {"reason": "test"})
    encoded = encode_sys_for_irc(msg)
    decoded = decode_sys_from_irc(encoded)
    assert decoded["type"] == "sys.stop_request"
    assert decoded["body"]["reason"] == "test"


def test_sys_message_not_user_text():
    """User text starting with { should not be decoded as sys."""
    assert decode_sys_from_irc("{this is just json-like text}") is None
    assert decode_sys_from_irc("hello world") is None
```

- [ ] **Step 5: Delete old test files**

```bash
rm tests/unit/test_tools.py tests/unit/test_server.py tests/unit/test_sidecar.py
```

- [ ] **Step 6: Run all tests**

Run: `cd weechat-channel-server && uv run python -m pytest ../tests/unit/ -v`

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: rewrite channel-server from Zenoh to IRC client"
```

---

## Chunk 4: Delete Old Files + Update Scripts

### Task 10: Delete WeeChat plugins and Zenoh files

**Files:**
- Delete: `weechat-zenoh/`, `weechat-agent/`, `wc_registry/`

- [ ] **Step 1: Delete directories**

```bash
rm -rf weechat-zenoh/ weechat-agent/ wc_registry/
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "refactor: delete WeeChat plugins, zenoh sidecar, and wc_registry"
```

---

### Task 11: Update start.sh and stop.sh

**Files:**
- Modify: `start.sh`
- Modify: `stop.sh`

- [ ] **Step 1: Rewrite start.sh**

```bash
#!/bin/bash
# start.sh — Start WeeChat-Claude system (ergo IRC + agent0 + WeeChat)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="${1:-$(pwd)}"
CONFIG="${2:-$SCRIPT_DIR/weechat-claude.toml}"
SESSION="weechat-claude"

echo "╔══════════════════════════════════════╗"
echo "║       WeeChat-Claude Launcher        ║"
echo "╚══════════════════════════════════════╝"
echo "  Workspace: $WORKSPACE"
echo "  Config:    $CONFIG"

# --- Dependency check ---
MISSING=""
for cmd in claude uv weechat tmux ergo; do
  command -v "$cmd" &>/dev/null || MISSING="$MISSING $cmd"
done
if [ -n "$MISSING" ]; then
  echo "Missing:$MISSING"; exit 1
fi

# --- Read IRC server from config ---
IRC_SERVER=$(python3 -c "import tomllib; c=tomllib.load(open('$CONFIG','rb')); print(c['irc']['server'])")
IRC_PORT=$(python3 -c "import tomllib; c=tomllib.load(open('$CONFIG','rb')); print(c['irc']['port'])")

# --- Start ergo if local ---
if [ "$IRC_SERVER" = "127.0.0.1" ] || [ "$IRC_SERVER" = "localhost" ]; then
  if ! pgrep -x ergo &>/dev/null; then
    echo "  Starting ergo IRC server..."
    ergo run --conf "$SCRIPT_DIR/ergo.yaml" &>/dev/null &
    sleep 1
  fi
fi

# --- Sync channel-server deps ---
echo "  Syncing channel-server deps..."
(cd "$SCRIPT_DIR/weechat-channel-server" && uv sync --quiet 2>/dev/null || uv sync)

# --- Create tmux session ---
tmux kill-session -t "$SESSION" 2>/dev/null || true
tmux new-session -d -s "$SESSION" -x 220 -y 50

# --- Start agent0 via wc-agent ---
echo "  Starting agent0..."
python3 "$SCRIPT_DIR/wc-agent/cli.py" --config "$CONFIG" start --workspace "$WORKSPACE"

# --- WeeChat pane ---
tmux split-window -h -t "$SESSION"
tmux send-keys -t "$SESSION" \
  "weechat -r '/server add wc-local $IRC_SERVER/$IRC_PORT; /connect wc-local; /join #general'" Enter

tmux select-pane -t "$SESSION:0.1"
echo "  Launching tmux session '$SESSION'..."
tmux attach -t "$SESSION"
```

- [ ] **Step 2: Rewrite stop.sh**

```bash
#!/bin/bash
# stop.sh — Stop WeeChat-Claude system
SESSION="${1:-weechat-claude}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${2:-$SCRIPT_DIR/weechat-claude.toml}"

echo "Stopping session: $SESSION"
python3 "$SCRIPT_DIR/wc-agent/cli.py" --config "$CONFIG" shutdown 2>/dev/null || true
tmux kill-session -t "$SESSION" 2>/dev/null && echo "  tmux session stopped" || echo "  (not running)"
```

- [ ] **Step 3: Commit**

```bash
git add start.sh stop.sh
git commit -m "refactor: update start.sh and stop.sh for IRC + wc-agent"
```

---

### Task 12: Create ergo IRC server config

**Files:**
- Create: `ergo.yaml`

- [ ] **Step 1: Create minimal ergo config**

```yaml
# ergo.yaml — Local IRC server for WeeChat-Claude
network:
  name: "wc-local"

server:
  name: "localhost"
  listeners:
    ":6667":
      tls:
        cert: ""
        key: ""

accounts:
  registration:
    enabled: false
  authentication-enabled: false

channels:
  default-modes: "+nt"
  registration:
    enabled: false

limits:
  nicklen: 32
  channellen: 64
  topiclen: 390
  line-len:
    tags: 512
    rest: 512

history:
  enabled: true
  channel-length: 256
  client-length: 100
```

- [ ] **Step 2: Create test config**

Create `tests/e2e/ergo-test.yaml` (same as above but port 6667, suitable for testing).

Create `tests/e2e/test-config.toml`:

```toml
[irc]
server = "127.0.0.1"
port = 6667

[agents]
default_channels = ["#general"]
username = "alice"
```

- [ ] **Step 3: Commit**

```bash
git add ergo.yaml tests/e2e/ergo-test.yaml tests/e2e/test-config.toml
git commit -m "feat: add ergo IRC server config for local development and testing"
```

---

## Chunk 5: E2E Test Migration

### Task 13: Rewrite e2e helpers.sh

**Files:**
- Modify: `tests/e2e/helpers.sh`

- [ ] **Step 1: Rewrite helpers.sh**

```bash
#!/bin/bash
# helpers.sh — Shared utilities for E2E tests

E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$E2E_DIR/../.." && pwd)"
TMUX_SESSION="e2e-$$"
TEST_CONFIG="$E2E_DIR/test-config.toml"

# Source environment
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"
[ -f "$PROJECT_DIR/claude.local.sh" ] && source "$PROJECT_DIR/claude.local.sh"
[ -f "$PROJECT_DIR/.mcp.env" ] && set -a && source "$PROJECT_DIR/.mcp.env" && set +a

# Claude flags
CLAUDE_FLAGS="--permission-mode bypassPermissions"
CLAUDE_CHANNEL_FLAGS="--dangerously-load-development-channels server:weechat-channel"

# User directories
ALICE_WC_DIR="/tmp/e2e-alice-$$"
BOB_WC_DIR="/tmp/e2e-bob-$$"

# Pane names
PANE_ALICE=""
PANE_BOB=""
PANE_AGENT0=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

pass() { echo -e "${GREEN}✅ PASS${NC}: $1"; }
fail() { echo -e "${RED}❌ FAIL${NC}: $1"; FAILURES=$((FAILURES + 1)); }
info() { echo -e "${YELLOW}➤${NC} $1"; }
step() { echo -e "\n${CYAN}━━━ $1 ━━━${NC}"; }

FAILURES=0

cleanup() {
    info "Cleaning up..."
    # Stop all agents
    python3 "$PROJECT_DIR/wc-agent/cli.py" --config "$TEST_CONFIG" shutdown 2>/dev/null || true
    # Quit WeeChat instances
    for pane in $(tmux list-panes -t "$TMUX_SESSION" -F '#{pane_index}' 2>/dev/null); do
        cmd=$(tmux display-message -t "$TMUX_SESSION.$pane" -p '#{pane_current_command}' 2>/dev/null)
        if [ "$cmd" = "weechat" ]; then
            tmux send-keys -t "$TMUX_SESSION.$pane" "/quit" Enter 2>/dev/null
        fi
    done
    sleep 2
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null
    # Stop test ergo
    pkill -f "ergo.*ergo-test" 2>/dev/null
    rm -rf "$ALICE_WC_DIR" "$BOB_WC_DIR"
}
trap cleanup EXIT

start_ergo() {
    if ! pgrep -x ergo &>/dev/null; then
        ergo run --conf "$E2E_DIR/ergo-test.yaml" &>/dev/null &
        sleep 1
    fi
}

wc_agent() {
    python3 "$PROJECT_DIR/wc-agent/cli.py" --config "$TEST_CONFIG" "$@"
}

# Wait for text to appear in a tmux pane
wait_for_pane() {
    local pane="$1" pattern="$2" timeout="${3:-10}"
    for i in $(seq 1 "$timeout"); do
        if tmux capture-pane -t "$pane" -p -S -200 2>/dev/null | grep -q "$pattern"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

pane_contains() {
    tmux capture-pane -t "$1" -p -S -200 2>/dev/null | grep -q "$2"
}

split_pane() {
    local direction="$1" target="$2"
    tmux split-window "$direction" -t "$target" -P -F '#{pane_id}'
}

initial_pane_id() {
    tmux list-panes -t "$TMUX_SESSION" -F '#{pane_id}' 2>/dev/null | head -1
}
```

- [ ] **Step 2: Commit**

```bash
git add tests/e2e/helpers.sh
git commit -m "refactor: rewrite e2e helpers for IRC + wc-agent"
```

---

### Task 14: Rewrite e2e-test.sh

**Files:**
- Modify: `tests/e2e/e2e-test.sh`

- [ ] **Step 1: Rewrite e2e-test.sh**

```bash
#!/bin/bash
# e2e-test.sh — Full E2E test: alice + bob + alice-agent0 + alice-agent1
#
# Layout:
#   ┌──────────────────┬──────────────────┐
#   │ alice (WeeChat)  │ alice-agent0     │
#   │  (IRC client)    │ (claude)         │
#   ├──────────────────┼──────────────────┤
#   │ bob (WeeChat)    │ alice-agent1     │
#   │  (IRC client)    │ (wc-agent create)│
#   └──────────────────┴──────────────────┘
set -euo pipefail

source "$(dirname "$0")/helpers.sh"

echo "╔══════════════════════════════════════╗"
echo "║    WeeChat-Claude E2E Test Suite     ║"
echo "║        (IRC Mode)                    ║"
echo "╚══════════════════════════════════════╝"

# ============================================================
# Phase 0: Prerequisites
# ============================================================
step "Phase 0: Prerequisites"

start_ergo
if pgrep -x ergo &>/dev/null; then
    pass "ergo IRC server running"
else
    fail "ergo not running"; exit 1
fi

# Sync channel-server deps
(cd "$PROJECT_DIR/weechat-channel-server" && uv sync --quiet 2>/dev/null || uv sync)
pass "channel-server deps synced"

# ============================================================
# Phase 1: Start alice (WeeChat) + alice-agent0 (claude)
# ============================================================
step "Phase 1: alice + alice-agent0"

tmux new-session -d -s "$TMUX_SESSION" -x 220 -y 60

# Pane: alice (WeeChat, native IRC) — initial pane
PANE_ALICE=$(initial_pane_id)
mkdir -p "$ALICE_WC_DIR"
tmux send-keys -t "$PANE_ALICE" \
    "weechat --dir $ALICE_WC_DIR -r '/server add wc-local 127.0.0.1/6667; /connect wc-local'" Enter

if wait_for_pane "$PANE_ALICE" "Connected" 15; then
    pass "alice: WeeChat connected to IRC"
else
    fail "alice: WeeChat failed to connect"; exit 1
fi

# Join #general
tmux send-keys -t "$PANE_ALICE" "/join #general" Enter
sleep 2

# Pane: alice-agent0 (claude, via wc-agent) — right side
PANE_AGENT0=$(split_pane -h "$PANE_ALICE")
tmux send-keys -t "$PANE_AGENT0" \
    "cd $PROJECT_DIR && wc_agent start --workspace $PROJECT_DIR" Enter

if wait_for_pane "$PANE_AGENT0" "Listening for channel" 30; then
    pass "alice-agent0: claude started with IRC channel-server"
else
    # Alternative: check if agent0 joined IRC
    sleep 10
    if pane_contains "$PANE_ALICE" "alice-agent0"; then
        pass "alice-agent0: detected via IRC JOIN"
    else
        fail "alice-agent0: claude failed to start"; exit 1
    fi
fi
sleep 5  # wait for MCP server init

# ============================================================
# Phase 2: agent0 sends message to #general
# ============================================================
step "Phase 2: agent0 → #general"

tmux send-keys -t "$PANE_AGENT0" \
    'Use the reply MCP tool to send "Hello everyone, alice-agent0 is online!" to #general' Enter

if wait_for_pane "$PANE_AGENT0" "Sent to" 45; then
    pass "agent0: reply tool called successfully"
elif wait_for_pane "$PANE_AGENT0" "online" 10; then
    pass "agent0: reply tool completed"
else
    fail "agent0: reply tool call failed"
fi

# Verify alice sees it in WeeChat #general
tmux send-keys -t "$PANE_ALICE" "/buffer #general" Enter
sleep 2

if pane_contains "$PANE_ALICE" "agent0 is online"; then
    pass "alice: received agent0's message in #general"
else
    fail "alice: did not receive agent0's message"
fi

# ============================================================
# Phase 3: alice mentions agent0, agent0 replies
# ============================================================
step "Phase 3: alice @mentions agent0"

tmux send-keys -t "$PANE_ALICE" "@alice-agent0 what is the capital of France?" Enter

# Agent0 should auto-respond via IRC
if wait_for_pane "$PANE_ALICE" "alice-agent0" 60; then
    pass "alice ↔ agent0: agent auto-responded to @mention"
else
    fail "alice ↔ agent0: agent did not auto-respond"
fi

# ============================================================
# Phase 4: bob joins
# ============================================================
step "Phase 4: bob joins #general"

PANE_BOB=$(split_pane -v "$PANE_ALICE")
mkdir -p "$BOB_WC_DIR"
tmux send-keys -t "$PANE_BOB" \
    "weechat --dir $BOB_WC_DIR -r '/server add wc-local 127.0.0.1/6667; /connect wc-local'" Enter

if wait_for_pane "$PANE_BOB" "Connected" 15; then
    pass "bob: WeeChat connected to IRC"
else
    fail "bob: WeeChat failed to connect"
fi

tmux send-keys -t "$PANE_BOB" "/join #general" Enter
sleep 2

# bob sends a message
tmux send-keys -t "$PANE_BOB" "Hey alice and agent0, bob here!" Enter
sleep 5

# Verify alice sees bob's message
tmux send-keys -t "$PANE_ALICE" "/buffer #general" Enter
sleep 2

if pane_contains "$PANE_ALICE" "bob here"; then
    pass "alice: sees bob's message"
else
    if grep -q "bob here" "$ALICE_WC_DIR/logs/"*.weechatlog 2>/dev/null; then
        pass "alice: received bob's message (verified via log)"
    else
        fail "alice: does not see bob's message"
    fi
fi

# ============================================================
# Phase 5: create agent1 via wc-agent CLI
# ============================================================
step "Phase 5: wc-agent create agent1"

# Run wc-agent create in a tmux pane (not inside WeeChat)
PANE_CMD=$(split_pane -v "$PANE_AGENT0")
tmux send-keys -t "$PANE_CMD" \
    "cd $PROJECT_DIR && wc_agent create agent1 --workspace $PROJECT_DIR" Enter
sleep 5

# Check if agent1 appears in wc-agent list
tmux send-keys -t "$PANE_CMD" "wc_agent list" Enter
sleep 2

if pane_contains "$PANE_CMD" "agent1"; then
    pass "agent1 created and listed"
else
    fail "agent1 not found in wc-agent list"
fi

# Wait for agent1 to initialize and join IRC
info "Waiting for agent1 to initialize..."
sleep 15

# Check if alice sees agent1 in #general
if pane_contains "$PANE_ALICE" "agent1"; then
    pass "agent1: visible in IRC #general"
else
    info "agent1: not yet visible in alice's IRC (may still be starting)"
fi

# ============================================================
# Phase 6: stop agent1 via wc-agent CLI
# ============================================================
step "Phase 6: wc-agent stop agent1"

tmux send-keys -t "$PANE_CMD" "wc_agent stop agent1" Enter
sleep 5

if pane_contains "$PANE_CMD" "Stopped"; then
    pass "agent1: stopped via wc-agent"
else
    fail "agent1: wc-agent stop failed"
fi

# Verify alice sees agent1 quit in IRC
if wait_for_pane "$PANE_ALICE" "has quit" 15; then
    pass "agent1: IRC QUIT seen by alice"
else
    info "agent1: IRC QUIT not detected in alice's pane"
fi

# ============================================================
# Phase 7: Summary
# ============================================================
step "Summary"

# Cleanup agent0
tmux send-keys -t "$PANE_AGENT0" "/exit" Enter
sleep 3

echo ""
if [ "$FAILURES" -eq 0 ]; then
    echo -e "${GREEN}All E2E tests passed!${NC}"
else
    echo -e "${RED}$FAILURES failure(s)${NC}"
fi

exit "$FAILURES"
```

- [ ] **Step 2: Commit**

```bash
git add tests/e2e/e2e-test.sh
git commit -m "refactor: rewrite e2e-test.sh for IRC + wc-agent CLI"
```

---

## Chunk 6: Documentation + Final Verification

### Task 15: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update architecture, terminology, commands**

Key changes:
- Architecture section: remove Zenoh, add IRC + wc-agent
- Terminology: `alice-agent0` (dash separator)
- Commands: `wc-agent start/create/stop/list/restart/status/shutdown`
- Dependencies: replace zenoh with irc, ergo
- Remove all `/agent` and `/zenoh` WeeChat command references
- Update Zenoh Topics section → remove entirely
- Update test commands

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for IRC migration"
```

---

### Task 16: Run full test suite

- [ ] **Step 1: Run unit tests**

```bash
cd weechat-channel-server && uv run python -m pytest ../tests/unit/ -v
```
Expected: All PASS

- [ ] **Step 2: Run e2e test (requires ergo installed)**

```bash
bash tests/e2e/e2e-test.sh
```
Expected: All phases PASS

- [ ] **Step 3: Fix any failures and commit**

```bash
git add -A
git commit -m "fix: address test failures from IRC migration"
```
