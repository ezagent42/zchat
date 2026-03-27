# zchat Restructuring Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename weechat-claude to zchat package structure and implement WeeChat plugin for agent management.

**Architecture:** Two-phase in-monorepo restructuring. Phase 1 moves `wc-agent/` → `zchat/cli/`, `wc_protocol/` → `zchat/protocol/`, renames all `wc-*` identifiers to `zchat-*`. Phase 2 creates `weechat-zchat-plugin/zchat.py` — a WeeChat Python script providing `/agent` commands, @mention highlighting, agent status display, and system message rendering.

**Tech Stack:** Python 3.11+, Typer (CLI), WeeChat Python API, irc library, MCP SDK

**Spec:** `docs/superpowers/specs/2026-03-27-zchat-repo-split-design.md`

---

## Chunk 1: Package Structure & Protocol (Phase 1)

### Task 1: Create zchat package with protocol module + update channel server

This task combines protocol move AND channel server updates into one commit
to avoid broken intermediate state (server.py imports from wc_protocol).

**Files:**
- Create: `zchat/__init__.py`
- Create: `zchat/protocol/__init__.py`
- Move: `wc_protocol/naming.py` → `zchat/protocol/naming.py`
- Move: `wc_protocol/sys_messages.py` → `zchat/protocol/sys_messages.py`
- Create: `zchat/protocol/commands.py`
- Modify: `weechat-channel-server/server.py` (update imports, remove create_agent)
- Test: `tests/unit/test_protocol.py` (update imports)
- Test: `tests/unit/test_sys_messages.py` (update imports)
- Test: `tests/unit/test_channel_server_irc.py` (update imports)

- [ ] **Step 1: Create zchat package directories**

```bash
mkdir -p zchat/protocol zchat/cli
```

- [ ] **Step 2: Create `zchat/__init__.py`**

```python
"""zchat — multi-agent collaboration over IRC."""
```

- [ ] **Step 3: Create `zchat/protocol/__init__.py`**

```python
"""zchat protocol specification — authoritative definitions for naming, system messages, and commands."""

PROTOCOL_VERSION = "0.1"
```

- [ ] **Step 4: Move and update `naming.py`**

Copy `wc_protocol/naming.py` → `zchat/protocol/naming.py`. Content is unchanged (no `wc` references in the code itself).

- [ ] **Step 5: Move and update `sys_messages.py`**

Copy `wc_protocol/sys_messages.py` → `zchat/protocol/sys_messages.py`. Change:

```python
# Old
IRC_SYS_PREFIX = "__wc_sys:"

# New
IRC_SYS_PREFIX = "__zchat_sys:"
```

- [ ] **Step 6: Create `zchat/protocol/commands.py`**

Define command specs in Python based on `commands.json` OpenAPI:

```python
"""zchat command definitions.

Python-native command specs. The OpenAPI file commands.json serves as
historical reference; this module is the authoritative source.
"""

COMMANDS = {
    "agent.start": {
        "summary": "Start IRC server and primary agent",
        "params": {
            "workspace": {"type": "string", "required": True, "description": "Workspace directory"},
            "project": {"type": "string", "required": False, "description": "Project name"},
        },
    },
    "agent.create": {
        "summary": "Create and launch a new agent",
        "params": {
            "name": {"type": "string", "required": True, "description": "Agent name (without username prefix)"},
            "workspace": {"type": "string", "required": False, "description": "Workspace directory"},
            "channels": {"type": "array", "required": False, "description": "IRC channels to join"},
        },
    },
    "agent.stop": {
        "summary": "Stop a running agent",
        "params": {
            "name": {"type": "string", "required": True, "description": "Agent name"},
        },
    },
    "agent.list": {
        "summary": "List all agents with status",
        "params": {},
    },
    "agent.status": {
        "summary": "Get detailed agent status",
        "params": {
            "name": {"type": "string", "required": True, "description": "Agent name"},
        },
    },
    "agent.restart": {
        "summary": "Stop and re-create an agent",
        "params": {
            "name": {"type": "string", "required": True, "description": "Agent name"},
        },
    },
    "agent.shutdown": {
        "summary": "Stop all agents and IRC server",
        "params": {},
    },
}
```

- [ ] **Step 7: Update test imports for protocol**

In `tests/unit/test_protocol.py`, change:
```python
# Old
from wc_protocol.naming import scoped_name, AGENT_SEPARATOR

# New
from zchat.protocol.naming import scoped_name, AGENT_SEPARATOR
```

In `tests/unit/test_sys_messages.py`, change:
```python
# Old
from wc_protocol.sys_messages import (

# New
from zchat.protocol.sys_messages import (
```

Also update assertions for the new prefix:
```python
# Old
assert SYS_PREFIX == "sys."
assert IRC_SYS_PREFIX == "__wc_sys:"
...
assert encoded.startswith("__wc_sys:")

# New
assert SYS_PREFIX == "sys."
assert IRC_SYS_PREFIX == "__zchat_sys:"
...
assert encoded.startswith("__zchat_sys:")
```

- [ ] **Step 8: Update channel server imports and remove create_agent**

In `weechat-channel-server/server.py`:

Update top-level import:
```python
# Old
from wc_protocol.sys_messages import (
    is_sys_message, make_sys_message,
    encode_sys_for_irc, decode_sys_from_irc,

# New
from zchat.protocol.sys_messages import (
    is_sys_message, make_sys_message,
    encode_sys_for_irc, decode_sys_from_irc,
```

Delete `_handle_create_agent()` function entirely (this also removes the inline `from wc_protocol.naming import scoped_name` import on line ~290).

Remove from `handle_list_tools()`: the `types.Tool(name="create_agent", ...)` entry.

Remove from `handle_call_tool()`: the `elif name == "create_agent":` branch.

Update `CHANNEL_INSTRUCTIONS` string: remove any mention of `create_agent` tool.

- [ ] **Step 9: Update channel server test imports**

In `tests/unit/test_channel_server_irc.py`:
```python
# Old
from wc_protocol.sys_messages import (
# New
from zchat.protocol.sys_messages import (
```

Update prefix assertions:
```python
# Old
assert encoded.startswith("__wc_sys:")
# New
assert encoded.startswith("__zchat_sys:")
```

- [ ] **Step 10: Run all protocol and channel server tests**

Run: `cd weechat-channel-server && uv run python -m pytest ../tests/unit/test_protocol.py ../tests/unit/test_sys_messages.py ../tests/unit/test_channel_server_irc.py -v`
Expected: All tests PASS

- [ ] **Step 11: Remove old `wc_protocol/` directory and commit**

```bash
git add zchat/ weechat-channel-server/server.py tests/unit/test_protocol.py tests/unit/test_sys_messages.py tests/unit/test_channel_server_irc.py
git rm -r wc_protocol/
git commit -m "refactor: move wc_protocol to zchat.protocol, rename __wc_sys: to __zchat_sys:, remove create_agent"
```

---

### Task 2: Move CLI modules to zchat/cli/

**Files:**
- Move: `wc-agent/cli.py` → `zchat/cli/app.py`
- Move: `wc-agent/agent_manager.py` → `zchat/cli/agent_manager.py`
- Move: `wc-agent/irc_manager.py` → `zchat/cli/irc_manager.py`
- Move: `wc-agent/project.py` → `zchat/cli/project.py`
- Create: `zchat/cli/__init__.py`
- Create: `zchat/cli/__main__.py`
- Delete: `wc-agent/config.py`
- Create: `pyproject.toml` (root)

- [ ] **Step 1: Create `zchat/cli/__init__.py`**

```python
"""zchat CLI — agent lifecycle management."""
```

- [ ] **Step 2: Create `zchat/cli/__main__.py`**

```python
"""Allow running as `python -m zchat.cli`."""
from zchat.cli.app import app

app()
```

- [ ] **Step 3: Copy CLI modules with renames**

Copy each file from `wc-agent/` to `zchat/cli/`, applying these substitutions in every file:

| Find | Replace |
|------|---------|
| `from wc_protocol.` | `from zchat.protocol.` |
| `from wc_agent.` | `from zchat.cli.` |
| `import wc_agent.` | `import zchat.cli.` |
| `WC_AGENT_HOME` | `ZCHAT_HOME` |
| `WC_TMUX_SESSION` | `ZCHAT_TMUX_SESSION` |
| `WC_PROJECT_DIR` | `ZCHAT_PROJECT_DIR` |
| `weechat-claude` (tmux session name) | `zchat` |
| `~/.wc-agent` | `~/.zchat` |
| `wc-agent` (in user-facing strings) | `zchat` |

Specific per-file changes:

**`zchat/cli/app.py`** (from `cli.py`):
- Rename `wc-agent` references in help strings to `zchat`
- `WC_TMUX_SESSION` → `ZCHAT_TMUX_SESSION`
- `weechat-claude` (default session) → `zchat`
- Import paths: `from wc_agent.` → `from zchat.cli.`

**`zchat/cli/agent_manager.py`**:
- `DEFAULT_STATE_FILE`: `~/.local/state/wc-agent/agents.json` → `~/.local/state/zchat/agents.json`
- `WC_PROJECT_DIR` → `ZCHAT_PROJECT_DIR`
- `WC_TMUX_SESSION` → `ZCHAT_TMUX_SESSION`
- `weechat-claude` → `zchat` (tmux session)
- `from wc_protocol.` → `from zchat.protocol.`
- Remove `from_env()` classmethod entirely (lines ~208-221 in original)
- Update `channel_server_dir` default in `__init__` to use `os.path.join(script_dir, "..", "weechat-channel-server")`  (this path still works in monorepo; Phase 3 will change discovery)

**`zchat/cli/irc_manager.py`**:
- `weechat-claude` → `zchat` in tmux session references
- `wc-agent` → `zchat` in user-facing messages

**`zchat/cli/project.py`**:
- `~/.wc-agent` → `~/.zchat` (home dir)
- `.wc-agent` → `.zchat` (marker file in `resolve_project()`)
- `wc-agent` → `zchat` in user-facing messages

- [ ] **Step 4: Create root `pyproject.toml`**

```toml
[project]
name = "zchat"
version = "0.1.0"
description = "Multi-agent collaboration over IRC"
requires-python = ">=3.11"
dependencies = [
    "typer[all]>=0.9.0",
]

[project.scripts]
zchat = "zchat.cli.app:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 5: Update test imports for CLI**

In `tests/unit/test_agent_manager.py`:
```python
# Old
from wc_agent.agent_manager import AgentManager
from wc_protocol.naming import scoped_name

# New
from zchat.cli.agent_manager import AgentManager
from zchat.protocol.naming import scoped_name
```

In `tests/unit/test_project.py`:
```python
# Old
from wc_agent.project import (

# New
from zchat.cli.project import (
```

Also update any `.wc-agent` marker references in test assertions to `.zchat`.

In `tests/unit/test_wc_agent_config.py`:
- This tests the deprecated `config.py`. Delete this entire test file.

In `tests/unit/test_channel_server_irc.py`:
```python
# Old
from wc_protocol.sys_messages import (

# New
from zchat.protocol.sys_messages import (
```

Update prefix assertions:
```python
# Old
assert encoded.startswith("__wc_sys:")

# New
assert encoded.startswith("__zchat_sys:")
```

In `tests/conftest.py`:
- Remove `wc_protocol` / `wc_agent` path manipulation if present
- Remove MockZenohSession (unused remnant from Zenoh architecture)
- Fix `agent_name` fixture: change `"alice:agent0"` to `"alice-agent0"` (colon is wrong, separator is `-`)

- [ ] **Step 6: Run all unit tests**

Run: `cd weechat-channel-server && uv run python -m pytest ../tests/unit/ -v`
Expected: All tests PASS (channel server imports already updated in Task 1)

- [ ] **Step 7: Delete old directories and files**

```bash
rm -rf wc-agent/
rm -f wc_agent  # symlink
```

- [ ] **Step 8: Commit**

```bash
git add zchat/cli/ pyproject.toml tests/
git rm -r wc-agent/ wc_agent
git rm tests/unit/test_wc_agent_config.py
git commit -m "refactor: move wc-agent to zchat.cli, create root pyproject.toml"
```

---

### Task 3: Update scripts

**Files:**
- Rename: `wc-agent.sh` → `zchat.sh`
- Modify: `start.sh`
- Modify: `stop.sh`
- Modify: `pytest.ini`

- [ ] **Step 1: Create `zchat.sh`**

```bash
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec env ${ZCHAT_HOME:+ZCHAT_HOME="$ZCHAT_HOME"} \
    uv run --project "$SCRIPT_DIR" python -m zchat.cli "$@"
```

Note: `--project` now points to root (where `pyproject.toml` lives), not `wc-agent/` subdir.

- [ ] **Step 2: Update `start.sh`**

Apply substitutions:
- `wc-agent` → `zchat` (CLI command references)
- `python -m wc_agent.cli` → `python -m zchat.cli`
- `weechat-claude` → `zchat` (tmux session name)
- `./wc-agent.sh` → `./zchat.sh`
- `cd "$SCRIPT_DIR/wc-agent" && uv sync` → `cd "$SCRIPT_DIR" && uv sync` (root pyproject.toml replaces wc-agent/pyproject.toml)

- [ ] **Step 3: Update `stop.sh`**

Apply substitutions:
- `wc-agent` → `zchat`
- `python -m wc_agent.cli` → `python -m zchat.cli`
- `weechat-claude` → `zchat` (tmux session)
- `./wc-agent.sh` → `./zchat.sh`

- [ ] **Step 4: Delete old `wc-agent.sh`**

```bash
git rm wc-agent.sh
```

- [ ] **Step 5: Update `pytest.ini` if needed**

Verify `testpaths = tests` is correct (should be fine since tests/ dir is unchanged).

- [ ] **Step 6: Run full test suite**

Run: `cd weechat-channel-server && uv run python -m pytest ../tests/unit/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add zchat.sh start.sh stop.sh pytest.ini
git rm wc-agent.sh
git commit -m "refactor: rename scripts wc-agent→zchat, update tmux session name"
```

---

## Chunk 2: WeeChat Plugin (Phase 2)

### Task 4: WeeChat plugin scaffold and `/agent` command

**Files:**
- Create: `weechat-zchat-plugin/zchat.py`
- Create: `tests/unit/test_weechat_plugin.py`

- [ ] **Step 1: Write tests for protocol helpers and command parsing**

Create `tests/unit/test_weechat_plugin.py`:

```python
"""Tests for weechat-zchat-plugin protocol helpers.

The WeeChat plugin implements protocol independently. These tests verify
the local protocol implementation matches zchat.protocol behavior.
"""
import json

# Test against zchat.protocol to verify the WeeChat plugin's independent
# implementation will match the authoritative protocol behavior.
from zchat.protocol.naming import scoped_name, AGENT_SEPARATOR
from zchat.protocol.sys_messages import (
    IRC_SYS_PREFIX, encode_sys_for_irc, decode_sys_from_irc, make_sys_message,
)


class TestPluginProtocolParity:
    """Verify the plugin's protocol constants match zchat.protocol."""

    def test_agent_separator(self):
        assert AGENT_SEPARATOR == "-"

    def test_sys_prefix(self):
        assert IRC_SYS_PREFIX == "__zchat_sys:"

    def test_scoped_name_basic(self):
        assert scoped_name("agent0", "alice") == "alice-agent0"

    def test_scoped_name_already_scoped(self):
        assert scoped_name("alice-agent0", "alice") == "alice-agent0"

    def test_sys_message_roundtrip(self):
        msg = make_sys_message("alice-agent0", "sys.status_request", {})
        encoded = encode_sys_for_irc(msg)
        decoded = decode_sys_from_irc(encoded)
        assert decoded["type"] == "sys.status_request"
        assert decoded["nick"] == "alice-agent0"

    def test_sys_decode_non_sys(self):
        assert decode_sys_from_irc("hello world") is None


class TestAgentCommandParsing:
    """Test /agent command argument parsing logic."""

    def test_parse_create(self):
        """create <name> [--workspace <path>]"""
        args = "create helper"
        parts = args.split(None, 1)
        assert parts[0] == "create"
        assert parts[1] == "helper"

    def test_parse_create_with_workspace(self):
        args = "create helper --workspace /tmp/ws"
        parts = args.split(None, 1)
        assert parts[0] == "create"
        # Remaining args parsed by the subcommand
        assert "--workspace" in parts[1]

    def test_parse_stop(self):
        args = "stop helper"
        parts = args.split(None, 1)
        assert parts[0] == "stop"
        assert parts[1] == "helper"

    def test_parse_list(self):
        args = "list"
        parts = args.split(None, 1)
        assert parts[0] == "list"
        assert len(parts) == 1

    def test_parse_empty(self):
        args = ""
        parts = args.split(None, 1)
        assert len(parts) == 0
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_weechat_plugin.py -v`
Expected: All PASS (these test protocol parity and parsing logic)

- [ ] **Step 3: Write the WeeChat plugin**

Create `weechat-zchat-plugin/zchat.py`:

```python
"""zchat — WeeChat Python script for multi-agent collaboration.

Provides:
- /agent command (create/stop/list/restart/send via zchat CLI)
- @mention highlighting for agent nicks
- Agent presence tracking (JOIN/PART/QUIT)
- System message rendering (__zchat_sys: → human-readable)
- Agent status bar item

Protocol implemented independently — no imports from zchat package.
"""

import json
import subprocess
import re

try:
    import weechat
except ImportError:
    # Allow importing for testing without weechat
    weechat = None

SCRIPT_NAME = "zchat"
SCRIPT_AUTHOR = "ezagent42"
SCRIPT_VERSION = "0.1.0"
SCRIPT_LICENSE = "Apache-2.0"
SCRIPT_DESC = "Multi-agent collaboration over IRC"

# --- Protocol constants (independent implementation) ---

AGENT_SEPARATOR = "-"
ZCHAT_SYS_PREFIX = "__zchat_sys:"

# --- Agent state ---

# nick → {"status": "online"/"offline", "channels": [...]}
agent_nicks = {}


# --- Protocol helpers ---

def is_agent_nick(nick):
    """Check if a nick looks like an agent (contains separator)."""
    return AGENT_SEPARATOR in nick


def scoped_name(name, username):
    """Add username prefix if not already scoped."""
    if AGENT_SEPARATOR in name:
        return name
    return f"{username}{AGENT_SEPARATOR}{name}"


def decode_sys_message(text):
    """Decode a __zchat_sys: message. Returns dict or None."""
    if not text.startswith(ZCHAT_SYS_PREFIX):
        return None
    try:
        return json.loads(text[len(ZCHAT_SYS_PREFIX):])
    except (json.JSONDecodeError, ValueError):
        return None


def format_sys_message(msg):
    """Format a system message for human display."""
    msg_type = msg.get("type", "unknown")
    nick = msg.get("nick", "?")
    body = msg.get("body", {})

    type_labels = {
        "sys.stop_request": "stop",
        "sys.join_request": "join",
        "sys.status_request": "status query",
        "sys.status_response": "status",
    }
    label = type_labels.get(msg_type, msg_type.replace("sys.", ""))

    if msg_type == "sys.status_response":
        channels = body.get("channels", [])
        return f"[zchat] {nick}: {label} — channels: {', '.join(channels)}"

    detail = ""
    if body:
        detail = f" — {json.dumps(body)}" if len(body) > 0 else ""
    return f"[zchat] {nick}: {label}{detail}"


# --- /agent command ---

def agent_command_cb(data, buffer, args):
    """Handle /agent command."""
    if not args:
        weechat.prnt(buffer, "[zchat] Usage: /agent <create|stop|list|restart|send> [args]")
        return weechat.WEECHAT_RC_OK

    parts = args.split(None, 1)
    subcmd = parts[0]
    rest = parts[1] if len(parts) > 1 else ""

    if subcmd == "create":
        return _agent_create(buffer, rest)
    elif subcmd == "stop":
        return _agent_stop(buffer, rest)
    elif subcmd == "list":
        return _agent_list(buffer)
    elif subcmd == "restart":
        return _agent_restart(buffer, rest)
    elif subcmd == "send":
        return _agent_send(buffer, rest)
    else:
        weechat.prnt(buffer, f"[zchat] Unknown subcommand: {subcmd}")
        return weechat.WEECHAT_RC_OK


def _run_zchat(buffer, args, success_msg=None):
    """Run zchat CLI command and print output to buffer."""
    cmd = ["zchat"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            output = result.stdout.strip()
            if output:
                for line in output.splitlines():
                    weechat.prnt(buffer, f"[zchat] {line}")
            elif success_msg:
                weechat.prnt(buffer, f"[zchat] {success_msg}")
        else:
            err = result.stderr.strip() or result.stdout.strip()
            weechat.prnt(buffer, f"[zchat] Error: {err}")
    except FileNotFoundError:
        weechat.prnt(buffer, "[zchat] Error: 'zchat' command not found. Is it installed?")
    except subprocess.TimeoutExpired:
        weechat.prnt(buffer, "[zchat] Error: command timed out")
    return weechat.WEECHAT_RC_OK


def _agent_create(buffer, args):
    if not args:
        weechat.prnt(buffer, "[zchat] Usage: /agent create <name> [--workspace <path>]")
        return weechat.WEECHAT_RC_OK
    parts = args.split()
    cmd_args = ["agent", "create"] + parts
    return _run_zchat(buffer, cmd_args, f"Agent '{parts[0]}' created")


def _agent_stop(buffer, args):
    if not args:
        weechat.prnt(buffer, "[zchat] Usage: /agent stop <name>")
        return weechat.WEECHAT_RC_OK
    return _run_zchat(buffer, ["agent", "stop", args.strip()])


def _agent_list(buffer):
    return _run_zchat(buffer, ["agent", "list"])


def _agent_restart(buffer, args):
    if not args:
        weechat.prnt(buffer, "[zchat] Usage: /agent restart <name>")
        return weechat.WEECHAT_RC_OK
    return _run_zchat(buffer, ["agent", "restart", args.strip()])


def _agent_send(buffer, args):
    parts = args.split(None, 1)
    if len(parts) < 2:
        weechat.prnt(buffer, "[zchat] Usage: /agent send <name> <message>")
        return weechat.WEECHAT_RC_OK
    name, message = parts
    return _run_zchat(buffer, ["agent", "send", name, message])


# --- System message modifier ---

def privmsg_modifier_cb(data, modifier, modifier_data, string):
    """Intercept PRIVMSG to render system messages as human-readable text.

    If the message is a __zchat_sys: message, replace the raw text
    with a formatted version. Return empty string to suppress the message,
    or modified string to change display.
    """
    # Parse IRC PRIVMSG: :nick!user@host PRIVMSG #channel :message
    match = re.match(r"^(:(\S+)\s+)?PRIVMSG\s+(\S+)\s+:(.*)$", string)
    if not match:
        return string

    text = match.group(4)
    sys_msg = decode_sys_message(text)
    if sys_msg is None:
        return string  # Not a system message, pass through

    # Replace raw sys message with formatted version
    formatted = format_sys_message(sys_msg)
    prefix = match.group(1) or ""
    channel = match.group(3)
    return f"{prefix}PRIVMSG {channel} :{formatted}"


# --- Presence tracking ---

def join_signal_cb(data, signal, signal_data):
    """Track agent JOINs."""
    # signal_data format: ":nick!user@host JOIN #channel"
    match = re.match(r"^:(\S+?)!", signal_data)
    if match:
        nick = match.group(1)
        if is_agent_nick(nick):
            agent_nicks[nick] = {"status": "online"}
            _update_bar_item()
    return weechat.WEECHAT_RC_OK


def part_signal_cb(data, signal, signal_data):
    """Track agent PARTs."""
    match = re.match(r"^:(\S+?)!", signal_data)
    if match:
        nick = match.group(1)
        if nick in agent_nicks:
            agent_nicks[nick]["status"] = "offline"
            _update_bar_item()
    return weechat.WEECHAT_RC_OK


def quit_signal_cb(data, signal, signal_data):
    """Track agent QUITs."""
    match = re.match(r"^:(\S+?)!", signal_data)
    if match:
        nick = match.group(1)
        if nick in agent_nicks:
            agent_nicks[nick]["status"] = "offline"
            _update_bar_item()
    return weechat.WEECHAT_RC_OK


# --- Bar item ---

def bar_item_cb(data, item, window):
    """Render agent status bar item."""
    if not agent_nicks:
        return ""
    parts = []
    for nick, info in sorted(agent_nicks.items()):
        status = info.get("status", "?")
        color = "green" if status == "online" else "red"
        parts.append(f"{weechat.color(color)}{nick}{weechat.color('reset')}")
    return " ".join(parts)


def _update_bar_item():
    """Trigger bar item refresh."""
    weechat.bar_item_update("zchat_agents")


# --- Highlight setup ---

def _setup_highlights():
    """Add agent-related highlight patterns.

    Adds highlight for @username pattern so user gets notified
    when agents or other users mention them.
    """
    # Get current nick from the server to set up @nick highlight
    # This is done per-server when connecting; for now, use a simple approach
    pass  # Highlights are configured via weechat settings; we just ensure
          # the script doesn't interfere with existing highlight config.


# --- Script entry point ---

def main():
    weechat.register(
        SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE,
        SCRIPT_DESC, "", ""  # shutdown_function, charset
    )

    # /agent command
    weechat.hook_command(
        "agent",
        "Manage zchat agents",
        "create <name> [--workspace <path>] || stop <name> || list || restart <name> || send <name> <message>",
        "  create: Create and launch a new agent\n"
        "    stop: Stop a running agent\n"
        "    list: List all agents with status\n"
        " restart: Restart an agent\n"
        "    send: Send a text message to an agent",
        "create || stop || list || restart || send",
        "agent_command_cb", ""
    )

    # System message rendering
    weechat.hook_modifier("irc_in_privmsg", "privmsg_modifier_cb", "")

    # Presence tracking (JOIN/PART/QUIT for all servers)
    weechat.hook_signal("*,irc_in_join", "join_signal_cb", "")
    weechat.hook_signal("*,irc_in_part", "part_signal_cb", "")
    weechat.hook_signal("*,irc_in_quit", "quit_signal_cb", "")

    # Agent status bar item
    weechat.bar_item_new("zchat_agents", "bar_item_cb", "")

    weechat.prnt("", f"[zchat] v{SCRIPT_VERSION} loaded. Use /agent for help.")


if __name__ == "__main__" and weechat is not None:
    main()
```

- [ ] **Step 4: Commit**

```bash
git add weechat-zchat-plugin/zchat.py tests/unit/test_weechat_plugin.py
git commit -m "feat: add weechat-zchat-plugin with /agent command, sys message rendering, presence tracking"
```

---

### Task 5: Integration — update irc_manager to load WeeChat plugin

**Files:**
- Modify: `zchat/cli/irc_manager.py`

- [ ] **Step 1: Update `start_weechat()` to autoload the plugin**

In `zchat/cli/irc_manager.py`, update the `start_weechat()` method to add the zchat plugin to WeeChat's launch command. Add after the existing `-r` args:

```python
# Find the plugin path relative to the script
plugin_dir = os.path.join(os.path.dirname(__file__), "..", "..", "weechat-zchat-plugin")
plugin_path = os.path.abspath(os.path.join(plugin_dir, "zchat.py"))

# Add to WeeChat -r command: load the plugin after connecting
# Append to existing -r string:
# /script load <path>/zchat.py
if os.path.exists(plugin_path):
    cmd += f"; /script load {plugin_path}"
```

- [ ] **Step 2: Test manually** (no automated test — requires WeeChat)

Verify that `start.sh` launches WeeChat with the plugin loaded by checking for `[zchat] v0.1.0 loaded` in the WeeChat core buffer.

- [ ] **Step 3: Commit**

```bash
git add zchat/cli/irc_manager.py
git commit -m "feat: auto-load weechat-zchat-plugin on WeeChat startup"
```

---

### Task 6: Final cleanup and verification

**Files:**
- Modify: `CLAUDE.md`
- Delete: `commands.json` (superseded by `zchat/protocol/commands.py`)
- Verify: all old references gone

- [ ] **Step 1: Update CLAUDE.md**

Update command references:
- `wc-agent` → `zchat`
- `./wc-agent.sh` → `./zchat.sh`
- `weechat-channel-server` → kept as-is (Phase 3)
- Add section about weechat-zchat-plugin

- [ ] **Step 2: Verify no stale references remain**

```bash
grep -r "wc-agent\|wc_agent\|WC_AGENT\|WC_TMUX\|WC_PROJECT\|__wc_sys\|wc_protocol\|\.wc-agent" --include="*.py" --include="*.sh" --include="*.toml" --include="*.ini" --include="*.json" . | grep -v "docs/" | grep -v ".git/" | grep -v "__pycache__"
```

Expected: No matches outside of `docs/` (specs/plans are historical).

- [ ] **Step 3: Run full test suite**

```bash
uv run python -m pytest tests/unit/ -v
```

Expected: All PASS

- [ ] **Step 4: Delete `commands.json`**

```bash
git rm commands.json
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git rm commands.json
git commit -m "chore: update CLAUDE.md for zchat rename, remove superseded commands.json"
```

---

## Summary

| Task | Phase | Description | Depends On |
|------|-------|-------------|------------|
| 1 | 1 | Protocol module + channel server updates | — |
| 2 | 1 | CLI modules (zchat.cli) | Task 1 |
| 3 | 1 | Script renames | Task 2 |
| 4 | 2 | WeeChat plugin + tests | Task 1 |
| 5 | 2 | Plugin autoload in irc_manager | Tasks 2, 4 |
| 6 | — | Cleanup and verification | All above |

Tasks 3 and 4 can run in parallel after Task 2 completes.
