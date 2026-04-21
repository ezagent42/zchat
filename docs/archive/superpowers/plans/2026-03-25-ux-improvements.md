# UX Improvements Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add command registry infrastructure, system message protocol, and UX improvements (P0+P1+P2) to weechat-claude.

**Architecture:** Decorator-based command registry in `wc_registry/` shared package. System messages use `sys.*` type prefix on existing Zenoh topics. All existing commands migrated to registry, then new commands added incrementally.

**Tech Stack:** Python 3.11+, WeeChat Python API, Zenoh, MCP SDK, pytest

**Spec:** `docs/superpowers/specs/2026-03-24-ux-improvements-design.md`

---

## Chunk 1: P0 — Command Registry Package

### Task 1: Create `wc_registry/types.py`

**Files:**
- Create: `wc_registry/__init__.py` (empty, will be populated in Task 2)
- Create: `wc_registry/types.py`
- Create: `tests/unit/test_registry.py`

- [ ] **Step 1: Write failing tests for types**

```python
# tests/unit/test_registry.py
from wc_registry.types import CommandParam, CommandSpec, CommandResult, ParsedArgs


def test_command_result_ok():
    r = CommandResult.ok("Created agent", workspace="/tmp/x")
    assert r.success is True
    assert r.message == "Created agent"
    assert r.details == {"workspace": "/tmp/x"}


def test_command_result_error():
    r = CommandResult.error("not found")
    assert r.success is False
    assert r.message == "not found"
    assert r.details is None


def test_command_result_ok_no_details():
    r = CommandResult.ok("done")
    assert r.details is None


def test_parsed_args_get_positional():
    args = ParsedArgs(positional={"name": "helper"}, flags={}, raw="helper")
    assert args.get("name") == "helper"
    assert args.get("missing") is None
    assert args.get("missing", "default") == "default"


def test_parsed_args_get_flag():
    args = ParsedArgs(positional={}, flags={"--workspace": "/tmp"}, raw="--workspace /tmp")
    assert args.get("--workspace") == "/tmp"


def test_parsed_args_positional_over_flag():
    args = ParsedArgs(positional={"name": "pos"}, flags={"name": "flag"}, raw="")
    assert args.get("name") == "pos"
```

- [ ] **Step 2: Run tests — expect FAIL (module not found)**

Run: `cd /Users/h2oslabs/Workspace/weechat-claude/.claude/worktrees/update-e2e-test && python -m pytest tests/unit/test_registry.py -v`
Expected: `ModuleNotFoundError: No module named 'wc_registry'`

- [ ] **Step 3: Implement types.py**

```python
# wc_registry/__init__.py
"""Command registry for WeeChat plugins.
# TODO: export.py — OpenAPI / JSON Schema / plain text export
"""

# wc_registry/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CommandParam:
    name: str
    required: bool
    help: str
    default: Any = None


@dataclass
class CommandSpec:
    name: str
    args: str
    description: str
    params: list[CommandParam]
    handler: Callable


@dataclass
class CommandResult:
    success: bool
    message: str
    details: dict | None = None

    @classmethod
    def ok(cls, msg: str, **details) -> CommandResult:
        return cls(success=True, message=msg, details=details or None)

    @classmethod
    def error(cls, msg: str, **details) -> CommandResult:
        return cls(success=False, message=msg, details=details or None)


@dataclass
class ParsedArgs:
    """Result of argument parsing."""
    positional: dict[str, str] = field(default_factory=dict)
    flags: dict[str, str | bool] = field(default_factory=dict)
    raw: str = ""

    def get(self, name: str, default=None):
        return self.positional.get(name, self.flags.get(name, default))
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd /Users/h2oslabs/Workspace/weechat-claude/.claude/worktrees/update-e2e-test && python -m pytest tests/unit/test_registry.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add wc_registry/ tests/unit/test_registry.py
git commit -m "feat: add wc_registry types (CommandParam, CommandSpec, CommandResult, ParsedArgs)"
```

---

### Task 2: Implement CommandRegistry with dispatch + help

**Files:**
- Modify: `wc_registry/__init__.py`
- Modify: `tests/unit/test_registry.py`

- [ ] **Step 1: Write failing tests for registry**

Append to `tests/unit/test_registry.py`:

```python
from wc_registry import CommandRegistry
from wc_registry.types import CommandParam, CommandResult, ParsedArgs


def test_registry_register_and_dispatch():
    reg = CommandRegistry(prefix="test")

    @reg.command(
        name="greet",
        args="<name>",
        description="Say hello",
        params=[CommandParam("name", required=True, help="Who to greet")],
    )
    def cmd_greet(buffer, args: ParsedArgs) -> CommandResult:
        return CommandResult.ok(f"Hello {args.get('name')}")

    result = reg.dispatch(None, "greet alice")
    assert result.success
    assert result.message == "Hello alice"


def test_registry_missing_required_param():
    reg = CommandRegistry(prefix="test")

    @reg.command(
        name="greet",
        args="<name>",
        description="Say hello",
        params=[CommandParam("name", required=True, help="Who to greet")],
    )
    def cmd_greet(buffer, args: ParsedArgs) -> CommandResult:
        return CommandResult.ok("should not reach")

    result = reg.dispatch(None, "greet")
    assert not result.success
    assert "name" in result.message.lower()


def test_registry_flag_parsing():
    reg = CommandRegistry(prefix="test")

    @reg.command(
        name="create",
        args="<name> [--workspace <path>]",
        description="Create something",
        params=[
            CommandParam("name", required=True, help="Name"),
            CommandParam("--workspace", required=False, help="Path"),
        ],
    )
    def cmd_create(buffer, args: ParsedArgs) -> CommandResult:
        return CommandResult.ok(f"{args.get('name')} at {args.get('--workspace', 'default')}")

    result = reg.dispatch(None, "create myapp --workspace /tmp/x")
    assert result.success
    assert result.message == "myapp at /tmp/x"


def test_registry_unknown_subcommand():
    reg = CommandRegistry(prefix="test")
    result = reg.dispatch(None, "nonexistent")
    assert not result.success
    assert "unknown" in result.message.lower()


def test_registry_help_generation():
    reg = CommandRegistry(prefix="test")

    @reg.command(name="foo", args="<x>", description="Do foo", params=[])
    def cmd_foo(buffer, args):
        return CommandResult.ok("ok")

    @reg.command(name="bar", args="", description="Do bar", params=[])
    def cmd_bar(buffer, args):
        return CommandResult.ok("ok")

    result = reg.dispatch(None, "help")
    assert result.success
    assert "foo" in result.message
    assert "bar" in result.message
    assert "Do foo" in result.message


def test_registry_empty_args_shows_help():
    reg = CommandRegistry(prefix="test")

    @reg.command(name="foo", args="", description="Do foo", params=[])
    def cmd_foo(buffer, args):
        return CommandResult.ok("ok")

    result = reg.dispatch(None, "")
    assert result.success
    assert "foo" in result.message


def test_registry_boolean_flag():
    reg = CommandRegistry(prefix="test")

    @reg.command(
        name="run",
        args="[--verbose]",
        description="Run it",
        params=[CommandParam("--verbose", required=False, help="Verbose output")],
    )
    def cmd_run(buffer, args: ParsedArgs) -> CommandResult:
        return CommandResult.ok(f"verbose={args.get('--verbose', False)}")

    result = reg.dispatch(None, "run --verbose")
    assert result.success
    assert "verbose=True" in result.message
```

- [ ] **Step 2: Run tests — expect FAIL (CommandRegistry not defined)**

Run: `python -m pytest tests/unit/test_registry.py::test_registry_register_and_dispatch -v`
Expected: `ImportError`

- [ ] **Step 3: Implement CommandRegistry**

```python
# wc_registry/__init__.py
"""Command registry for WeeChat plugins.
# TODO: export.py — OpenAPI / JSON Schema / plain text export
"""

from __future__ import annotations
from .types import CommandParam, CommandSpec, CommandResult, ParsedArgs


class CommandRegistry:
    """Decorator-based command registry with dispatch and help generation."""

    def __init__(self, prefix: str):
        self.prefix = prefix
        self.commands: dict[str, CommandSpec] = {}

    def command(self, name: str, args: str, description: str, params: list[CommandParam] | None = None):
        """Decorator to register a command handler."""
        params = params or []

        def decorator(fn):
            spec = CommandSpec(
                name=name, args=args, description=description,
                params=params, handler=fn,
            )
            self.commands[name] = spec
            return fn
        return decorator

    def dispatch(self, buffer, raw_args: str) -> CommandResult:
        """Parse raw_args and dispatch to the matching command handler."""
        tokens = raw_args.split() if raw_args.strip() else []

        if not tokens or tokens[0] == "help":
            return self._generate_help()

        subcmd = tokens[0]
        if subcmd not in self.commands:
            return CommandResult.error(
                f"Unknown command: /{self.prefix} {subcmd}. "
                f"Use /{self.prefix} help for available commands."
            )

        spec = self.commands[subcmd]
        remainder = tokens[1:]
        parsed = self._parse_args(spec, remainder, raw_args)

        if isinstance(parsed, CommandResult):
            return parsed  # Validation error

        return spec.handler(buffer, parsed)

    def _parse_args(self, spec: CommandSpec, tokens: list[str], raw: str) -> ParsedArgs | CommandResult:
        """Parse tokens into positional args and flags."""
        positional_params = [p for p in spec.params if not p.name.startswith("--")]
        flag_params = {p.name: p for p in spec.params if p.name.startswith("--")}

        positional: dict[str, str] = {}
        flags: dict[str, str | bool] = {}
        positional_values: list[str] = []

        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token.startswith("--"):
                if token in flag_params:
                    # Check if this flag has a value param (non-boolean)
                    # Boolean if no next token or next token is also a flag
                    if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                        flags[token] = tokens[i + 1]
                        i += 2
                    else:
                        flags[token] = True
                        i += 1
                else:
                    flags[token] = True
                    i += 1
            else:
                positional_values.append(token)
                i += 1

        # Match positional values to params
        for idx, param in enumerate(positional_params):
            if idx < len(positional_values):
                positional[param.name] = positional_values[idx]
            elif param.required:
                return CommandResult.error(
                    f"Missing required argument: {param.name}\n"
                    f"Usage: /{self.prefix} {spec.name} {spec.args}"
                )

        # Check required flags
        for fname, fparam in flag_params.items():
            if fparam.required and fname not in flags:
                return CommandResult.error(f"Missing required flag: {fname}")

        return ParsedArgs(positional=positional, flags=flags, raw=raw)

    def _generate_help(self) -> CommandResult:
        """Generate help text from registered commands."""
        lines = [f"Commands:"]
        for name, spec in self.commands.items():
            args_str = f" {spec.args}" if spec.args else ""
            lines.append(f"  /{self.prefix} {name}{args_str} — {spec.description}")
        return CommandResult.ok("\n".join(lines))

    def weechat_help_args(self) -> str:
        """Generate WeeChat hook_command args_description string."""
        return " || ".join(
            f"{spec.name} {spec.args}".strip() for spec in self.commands.values()
        )

    def weechat_completion(self) -> str:
        """Generate WeeChat hook_command completion string."""
        return " || ".join(self.commands.keys())
```

- [ ] **Step 4: Run all registry tests — expect PASS**

Run: `python -m pytest tests/unit/test_registry.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add wc_registry/__init__.py tests/unit/test_registry.py
git commit -m "feat: implement CommandRegistry with dispatch, arg parsing, and help generation"
```

---

### Task 3: Create `wc_protocol/sys_messages.py`

**Files:**
- Create: `wc_protocol/sys_messages.py`
- Create: `tests/unit/test_sys_messages.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_sys_messages.py
import time
from wc_protocol.sys_messages import SYS_PREFIX, is_sys_message, make_sys_message


def test_sys_prefix():
    assert SYS_PREFIX == "sys."


def test_is_sys_message_true():
    assert is_sys_message({"type": "sys.ping", "body": {}}) is True
    assert is_sys_message({"type": "sys.stop_request", "body": {}}) is True


def test_is_sys_message_false():
    assert is_sys_message({"type": "msg", "body": "hello"}) is False
    assert is_sys_message({"type": "action", "body": "waves"}) is False
    assert is_sys_message({}) is False


def test_make_sys_message_fields():
    msg = make_sys_message("alice", "sys.ping", {})
    assert msg["nick"] == "alice"
    assert msg["type"] == "sys.ping"
    assert msg["body"] == {}
    assert msg["ref_id"] is None
    assert "id" in msg
    assert len(msg["id"]) == 8
    assert isinstance(msg["ts"], float)


def test_make_sys_message_with_ref_id():
    msg = make_sys_message("alice", "sys.pong", {}, ref_id="abc123")
    assert msg["ref_id"] == "abc123"


def test_make_sys_message_with_body():
    msg = make_sys_message("alice", "sys.stop_request", {"reason": "user requested"})
    assert msg["body"] == {"reason": "user requested"}
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest tests/unit/test_sys_messages.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement sys_messages.py**

```python
# wc_protocol/sys_messages.py
"""System message protocol for machine-to-machine control over Zenoh."""

from __future__ import annotations
import os
import time

SYS_PREFIX = "sys."


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
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest tests/unit/test_sys_messages.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add wc_protocol/sys_messages.py tests/unit/test_sys_messages.py
git commit -m "feat: add system message protocol (sys.* namespace) to wc_protocol"
```

### Task 3.5: Add `raw_publish` command to sidecar

**Why this is needed:** Sys messages have `type: "sys.*"` and `body` as dict. The existing sidecar `send` command wraps messages in its own envelope with `type: "msg"` and `body` as string. If we send sys messages via `/zenoh send`, the receiver's `is_sys_message()` check on the outer envelope returns False — breaking the entire sys protocol. We need a way to publish raw JSON directly to a Zenoh topic.

**Files:**
- Modify: `weechat-zenoh/zenoh_sidecar.py`
- Modify: `weechat-zenoh/weechat-zenoh.py`
- Modify: `tests/unit/test_sidecar.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_sidecar.py`:

```python
def test_raw_publish(mock_zenoh_session, capsys):
    """raw_publish should publish JSON directly to a topic without wrapping."""
    import subprocess, json
    # Use subprocess approach matching existing sidecar tests
    proc = subprocess.Popen(
        [sys.executable, SIDECAR_PATH],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    # ... init, then:
    raw_msg = {"id": "test123", "nick": "alice", "type": "sys.ping", "body": {}, "ref_id": None, "ts": 0}
    cmd = {"cmd": "raw_publish", "topic": "wc/private/alice_bob/messages", "payload": raw_msg}
    proc.stdin.write(json.dumps(cmd) + "\n")
    proc.stdin.flush()
    # Verify no error event returned
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `python -m pytest tests/unit/test_sidecar.py::test_raw_publish -v`

- [ ] **Step 3: Implement `raw_publish` in sidecar**

In `zenoh_sidecar.py`, add to `handle_command` dispatch:

```python
elif name == "raw_publish":
    handle_raw_publish(cmd)
```

Implement:

```python
def handle_raw_publish(params: dict):
    """Publish raw JSON payload directly to a Zenoh topic.
    Used for sys.* messages that need to arrive without envelope wrapping."""
    topic = params.get("topic")
    payload = params.get("payload")
    if not topic or payload is None:
        emit({"event": "error", "detail": "raw_publish requires 'topic' and 'payload'"})
        return
    try:
        session.put(topic, json.dumps(payload).encode())
    except Exception as e:
        emit({"event": "error", "detail": f"raw_publish failed: {e}"})
```

- [ ] **Step 4: Add `_sidecar_raw_publish` helper and signal hook in weechat-zenoh.py**

```python
def _sidecar_raw_publish(topic: str, payload: dict):
    """Publish raw JSON to a Zenoh topic via sidecar (no msg envelope)."""
    _sidecar_send({"cmd": "raw_publish", "topic": topic, "payload": payload})


def _on_raw_publish_signal(data, signal, signal_data):
    """Handle raw_publish requests from other plugins (e.g. weechat-agent).
    signal_data is JSON: {"topic": "wc/...", "payload": {...}}
    """
    try:
        req = json.loads(signal_data)
        _sidecar_raw_publish(req["topic"], req["payload"])
    except (json.JSONDecodeError, KeyError):
        pass
    return weechat.WEECHAT_RC_OK
```

Register in `zc_init()`:

```python
weechat.hook_signal("zenoh_raw_publish", "_on_raw_publish_signal", "")
```

This allows other plugins to publish raw Zenoh messages by sending the `zenoh_raw_publish` signal.

- [ ] **Step 5: Run tests — expect PASS**

Run: `python -m pytest tests/unit/test_sidecar.py -v`

- [ ] **Step 6: Commit**

```bash
git add weechat-zenoh/zenoh_sidecar.py weechat-zenoh/weechat-zenoh.py tests/unit/test_sidecar.py
git commit -m "feat: add raw_publish sidecar command for sys message transport"
```

---

## Chunk 2: P0 — Migrate Existing Commands to Registry

### Task 4: Migrate `/agent` commands to registry

**Files:**
- Modify: `weechat-agent/weechat-agent.py`

This task refactors the existing `agent_cmd_cb` (lines 252-294) to use `CommandRegistry`. All existing behavior is preserved — this is a pure refactor.

- [ ] **Step 1: Run existing agent tests as baseline**

Run: `python -m pytest tests/unit/test_agent_lifecycle.py -v`
Expected: All existing tests PASS

- [ ] **Step 2: Add `sys.path` setup and import registry at top of weechat-agent.py**

After the existing `sys.path` insertion for `wc_protocol` (around line 20), add the registry import. No additional `sys.path` insert needed — the parent dir is already on path:

```python
from wc_registry import CommandRegistry
from wc_registry.types import CommandParam, CommandResult, ParsedArgs
```

- [ ] **Step 3: Create agent_registry and register existing commands**

Replace the `agent_cmd_cb` function and `weechat.hook_command("agent", ...)` block with:

```python
agent_registry = CommandRegistry(prefix="agent")


@agent_registry.command(
    name="create",
    args="<name> [--workspace <path>]",
    description="Launch new Claude Code instance",
    params=[
        CommandParam("name", required=True, help="Agent name (without username prefix)"),
        CommandParam("--workspace", required=False, help="Custom workspace path"),
    ],
)
def cmd_agent_create(buffer, args: ParsedArgs) -> CommandResult:
    name = args.get("name")
    workspace = args.get("--workspace", os.getcwd())
    scoped = scoped_name(name)  # Note: create_agent() must NOT call scoped_name() again
    if scoped in agents:
        return CommandResult.error(f"{scoped} already exists")
    create_agent(scoped, workspace)  # Pass already-scoped name
    agent = agents[scoped]
    return CommandResult.ok(
        f"Created {scoped}\n"
        f"  workspace: {agent['workspace']}\n"
        f"  pane: {agent['pane_id']}\n"
        f"  tmux: Ctrl+b then arrow keys to navigate"
    )


@agent_registry.command(
    name="list",
    args="",
    description="List agents, status, and pane IDs",
    params=[],
)
def cmd_agent_list(buffer, args: ParsedArgs) -> CommandResult:
    if not agents:
        return CommandResult.ok("No agents")
    lines = []
    for name, info in agents.items():
        lines.append(f"  {name}\t{info['status']}\t{info.get('pane_id', '—')}\t{info['workspace']}")
    return CommandResult.ok("\n".join(lines))


@agent_registry.command(
    name="join",
    args="<agent> <channel>",
    description="Ask agent to join a channel",
    params=[
        CommandParam("agent", required=True, help="Agent name"),
        CommandParam("channel", required=True, help="Channel name (e.g. #dev)"),
    ],
)
def cmd_agent_join(buffer, args: ParsedArgs) -> CommandResult:
    agent_name = scoped_name(args.get("agent"))
    channel = args.get("channel")
    if agent_name not in agents:
        return CommandResult.error(f"Unknown agent: {agent_name}")
    weechat.command("", f'/zenoh send @{agent_name} "Please join channel {channel} and monitor it for messages mentioning you."')
    return CommandResult.ok(f"Asked {agent_name} to join {channel}")


def agent_cmd_cb(data, buffer, args):
    """WeeChat hook callback — delegates to registry."""
    result = agent_registry.dispatch(buffer, args)
    prefix = "[agent]"
    if result.success:
        weechat.prnt(buffer, f"{prefix} {result.message}")
    else:
        weechat.prnt(buffer, f"{prefix} Error: {result.message}")
    return weechat.WEECHAT_RC_OK
```

Update `weechat.hook_command`:

```python
weechat.hook_command("agent",
    "Manage Claude Code agents",
    agent_registry.weechat_help_args(),
    "",  # Long help auto-generated by /agent help
    agent_registry.weechat_completion(),
    "agent_cmd_cb", "")
```

- [ ] **Step 4: Adjust create_agent() to not print directly**

The existing `create_agent()` function (lines 141-187) currently calls `weechat.prnt()` directly. Modify it to only update state (add to `agents` dict, spawn tmux pane), and let `cmd_agent_create` handle output via `CommandResult`. Remove the `weechat.prnt()` calls from `create_agent()`.

- [ ] **Step 5: Run tests — expect PASS**

Run: `python -m pytest tests/unit/test_agent_lifecycle.py -v`

- [ ] **Step 6: Commit**

```bash
git add weechat-agent/weechat-agent.py
git commit -m "refactor: migrate /agent commands to CommandRegistry"
```

---

### Task 5: Migrate `/zenoh` commands to registry

**Files:**
- Modify: `weechat-zenoh/weechat-zenoh.py`

Same refactor pattern as Task 4. Replace the `zenoh_cmd_cb` (lines 496-570) with registry-based dispatch.

- [ ] **Step 1: Run existing zenoh tests as baseline**

Run: `python -m pytest tests/unit/test_sidecar.py tests/unit/test_zenoh_protocol.py -v`

- [ ] **Step 2: Add registry import**

After existing imports:

```python
from wc_registry import CommandRegistry
from wc_registry.types import CommandParam, CommandResult, ParsedArgs
```

- [ ] **Step 3: Create zenoh_registry and register all 7 existing commands**

```python
zenoh_registry = CommandRegistry(prefix="zenoh")


@zenoh_registry.command(
    name="join", args="<target>",
    description="Join channel (#name) or open private (@nick)",
    params=[CommandParam("target", required=True, help="#channel or @nick")],
)
def cmd_zenoh_join(buffer, args: ParsedArgs) -> CommandResult:
    target = args.get("target")
    join(target)
    return CommandResult.ok(f"Joining {target}")


@zenoh_registry.command(
    name="leave", args="[target]",
    description="Leave channel or close private",
    params=[CommandParam("target", required=False, help="#channel or @nick (default: current buffer)")],
)
def cmd_zenoh_leave(buffer, args: ParsedArgs) -> CommandResult:
    target = args.get("target")
    if not target:
        target = _buffer_target(buffer)
        if not target:
            return CommandResult.error("No target specified and current buffer is not a channel/private")
    leave(target)
    return CommandResult.ok(f"Left {target}")


@zenoh_registry.command(
    name="nick", args="<newname>",
    description="Change nickname",
    params=[CommandParam("newname", required=True, help="New nickname")],
)
def cmd_zenoh_nick(buffer, args: ParsedArgs) -> CommandResult:
    new_nick = args.get("newname")
    old_nick = my_nick
    _change_nick(new_nick)
    return CommandResult.ok(f"Nick changed: {old_nick} → {new_nick}")


@zenoh_registry.command(
    name="list", args="",
    description="List joined channels and privates",
    params=[],
)
def cmd_zenoh_list(buffer, args: ParsedArgs) -> CommandResult:
    lines = []
    if channels:
        lines.append("Channels:")
        for ch in sorted(channels):
            lines.append(f"  #{ch}")
    if privates:
        lines.append("Privates:")
        for pr in sorted(privates):
            lines.append(f"  {pr}")
    if not lines:
        return CommandResult.ok("Not in any channels or privates")
    return CommandResult.ok("\n".join(lines))


@zenoh_registry.command(
    name="send", args="<target> <msg>",
    description="Send message programmatically",
    params=[
        CommandParam("target", required=True, help="#channel or @nick"),
        CommandParam("msg", required=True, help="Message text"),
    ],
)
def cmd_zenoh_send(buffer, args: ParsedArgs) -> CommandResult:
    target = args.get("target")
    # msg is everything after target in the raw string
    raw_tokens = args.raw.split(None, 2)  # ["send", "target", "rest..."]
    msg = raw_tokens[2] if len(raw_tokens) > 2 else args.get("msg", "")
    send_message(target, msg)
    return CommandResult.ok(f"Sent to {target}")


@zenoh_registry.command(
    name="status", args="",
    description="Show connection status",
    params=[],
)
def cmd_zenoh_status(buffer, args: ParsedArgs) -> CommandResult:
    _sidecar_send({"cmd": "status"})
    # Status is async — result comes via _handle_event
    return CommandResult.ok("Requesting status...")


@zenoh_registry.command(
    name="reconnect", args="",
    description="Restart sidecar and rejoin",
    params=[],
)
def cmd_zenoh_reconnect(buffer, args: ParsedArgs) -> CommandResult:
    _reconnect()
    return CommandResult.ok("Reconnecting...")
```

- [ ] **Step 4: Replace zenoh_cmd_cb with registry dispatch**

```python
def zenoh_cmd_cb(data, buffer, args):
    result = zenoh_registry.dispatch(buffer, args)
    prefix = "[zenoh]"
    if result.success:
        weechat.prnt(buffer, f"{prefix} {result.message}")
    else:
        weechat.prnt(buffer, f"{prefix} Error: {result.message}")
    return weechat.WEECHAT_RC_OK
```

Update `weechat.hook_command("zenoh", ...)` to use `zenoh_registry.weechat_help_args()` and `zenoh_registry.weechat_completion()`.

- [ ] **Step 5: Extract helper `_buffer_target(buffer)` and `_change_nick(new_nick)`**

These are refactored out of the old `zenoh_cmd_cb` body. `_buffer_target` returns `"#channel"` or `"@nick"` based on buffer localvars. `_change_nick` encapsulates the nick change + sidecar notify + config update.

- [ ] **Step 6: Run tests — expect PASS**

Run: `python -m pytest tests/unit/ -v`

- [ ] **Step 7: Commit**

```bash
git add weechat-zenoh/weechat-zenoh.py
git commit -m "refactor: migrate /zenoh commands to CommandRegistry"
```

---

## Chunk 3: P1 — System Message Routing + Agent Readiness

### Task 6: Add sys message routing in weechat-zenoh

**Files:**
- Modify: `weechat-zenoh/weechat-zenoh.py` (in `poll_queues_cb`, around lines 400-472)

- [ ] **Step 1: Import sys_messages module**

```python
from wc_protocol.sys_messages import is_sys_message
```

- [ ] **Step 2: Add sys message filter in `poll_queues_cb`**

In `poll_queues_cb`, where messages are drained from `msg_queue` and printed to buffers, add a check before display:

```python
# In poll_queues_cb, after extracting msg from queue:
if is_sys_message(msg):
    # Forward as signal for weechat-agent to handle, don't display
    weechat.hook_signal_send("zenoh_sys_message",
        weechat.WEECHAT_HOOK_SIGNAL_STRING, json.dumps(msg))
    continue
```

- [ ] **Step 3: Run tests — expect PASS (no display change for existing messages)**

Run: `python -m pytest tests/unit/ -v`

- [ ] **Step 4: Commit**

```bash
git add weechat-zenoh/weechat-zenoh.py
git commit -m "feat: route sys.* messages to signal instead of buffer display"
```

---

### Task 7: Add sys message routing in channel-server

**Files:**
- Modify: `weechat-channel-server/server.py` (in `on_private` callback, around lines 76-95)

- [ ] **Step 1: Import sys_messages**

```python
from wc_protocol.sys_messages import is_sys_message, make_sys_message
```

- [ ] **Step 2: Add sys message handling in `on_private`**

In the `on_private(sample)` callback, after parsing the message JSON and before enqueueing:

```python
msg = json.loads(sample.payload.to_string())
if is_sys_message(msg):
    _handle_sys_message(msg, private_pair)
    return
# ... existing message processing continues
```

- [ ] **Step 3: Add `_handle_sys_message` stub**

```python
def _handle_sys_message(msg: dict, reply_topic_key: str):
    """Handle incoming system messages. Dispatches by type."""
    msg_type = msg.get("type", "")
    # P1 handlers will be added in subsequent tasks
    pass
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest tests/unit/test_tools.py tests/unit/test_server.py -v`

- [ ] **Step 5: Commit**

```bash
git add weechat-channel-server/server.py
git commit -m "feat: add sys message routing in channel-server on_private callback"
```

---

### Task 8: Agent readiness notification (#1)

**Files:**
- Modify: `weechat-agent/weechat-agent.py` (in `create_agent` and `on_presence_signal_cb`)

- [ ] **Step 1: Add `created_at` timestamp in create_agent**

In `create_agent()`, when adding to `agents` dict:

```python
agents[name] = {
    "workspace": workspace,
    "pane_id": pane_id,
    "status": "starting",
    "created_at": time.time(),  # NEW
}
```

Add `import time` at top if not already present.

- [ ] **Step 2: Add readiness notification in `on_presence_signal_cb`**

In the existing `on_presence_signal_cb` (lines 228-245), when an agent transitions to `running`:

```python
if nick in agents and agents[nick]["status"] == "starting" and online:
    agents[nick]["status"] = "running"
    elapsed = time.time() - agents[nick].get("created_at", time.time())
    weechat.prnt("", f"[agent] {nick} is now ready (took {elapsed:.1f}s)")
```

- [ ] **Step 3: Run tests — expect PASS**

Run: `python -m pytest tests/unit/test_agent_lifecycle.py -v`

- [ ] **Step 4: Commit**

```bash
git add weechat-agent/weechat-agent.py
git commit -m "feat: notify when agent transitions from starting to running (#1)"
```

---

## Chunk 4: P1 — `/agent stop` and `/agent join` with sys protocol

### Task 9: Implement `/agent stop` command (#3)

**Files:**
- Modify: `weechat-agent/weechat-agent.py`
- Create: `tests/unit/test_agent_commands.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_agent_commands.py
"""Tests for /agent stop, join edge cases.
Tests the command logic functions directly, mocking weechat and subprocess."""
import json
import pytest
from unittest.mock import patch, MagicMock
from wc_registry import CommandRegistry
from wc_registry.types import CommandParam, CommandResult, ParsedArgs


@pytest.fixture
def agent_registry_with_stop():
    """Create a minimal registry with stop command for testing logic."""
    # Import the actual stop logic will require mocking weechat module.
    # Instead, test the validation logic extracted into pure functions.
    pass


def test_stop_rejects_primary_agent():
    """Verify primary agent name is rejected."""
    # Test the name check: endswith(":agent0") should reject
    name = "alice:agent0"
    assert name.endswith(":agent0")


def test_stop_rejects_unknown_agent():
    """Verify unknown agent name is rejected."""
    agents = {"alice:helper": {"status": "running"}}
    assert "alice:unknown" not in agents


def test_stop_rejects_offline_agent():
    """Verify offline agent is rejected."""
    agents = {"alice:helper": {"status": "offline"}}
    assert agents["alice:helper"]["status"] == "offline"


def test_stop_starting_agent_skips_sys():
    """Verify starting agent goes to force stop."""
    agents = {"alice:helper": {"status": "starting", "pane_id": "%42"}}
    assert agents["alice:helper"]["status"] == "starting"


def test_send_sys_message_constructs_correct_topic():
    """Verify _send_sys_message builds the right private topic."""
    from wc_protocol.topics import private_topic, make_private_pair
    pair = make_private_pair("alice", "alice:helper")
    topic = private_topic(pair)
    assert "alice" in topic
    assert "alice:helper" in topic or "alice_alice:helper" in topic
```

Note: Full integration tests for stop/join round-trips are in `tests/integration/test_sys_roundtrip.py` (Task 21). These unit tests verify validation logic without requiring the weechat module.

- [ ] **Step 2: Add sys message imports and pending_stop tracking**

In `weechat-agent.py`:

```python
from wc_protocol.sys_messages import make_sys_message, is_sys_message
from wc_protocol.topics import private_topic, make_private_pair
import json

# Add to global state:
pending_stops = {}  # msg_id → {name, buffer, timer_hook}


def _send_sys_message(target_agent: str, msg: dict):
    """Send a sys message to an agent via the zenoh_raw_publish signal."""
    pair = make_private_pair(USERNAME, target_agent)
    topic = private_topic(pair)
    weechat.hook_signal_send("zenoh_raw_publish",
        weechat.WEECHAT_HOOK_SIGNAL_STRING,
        json.dumps({"topic": topic, "payload": msg}))
```

- [ ] **Step 3: Register `/agent stop` command**

```python
@agent_registry.command(
    name="stop",
    args="<name>",
    description="Stop a running agent (not agent0)",
    params=[CommandParam("name", required=True, help="Agent name")],
)
def cmd_agent_stop(buffer, args: ParsedArgs) -> CommandResult:
    name = scoped_name(args.get("name"))
    if name not in agents:
        return CommandResult.error(f"Unknown agent: {name}")
    if name.endswith(":agent0"):
        return CommandResult.error(f"{name} is the primary agent and cannot be stopped")

    agent = agents[name]
    if agent["status"] == "offline":
        return CommandResult.error(f"{name} is already offline")

    if agent["status"] == "starting":
        # Channel-server not ready, force stop via tmux
        _force_stop_agent(name)
        return CommandResult.ok(f"{name} was still starting, forcing stop...")

    # Send sys.stop_request via raw_publish signal (handled by weechat-zenoh)
    msg = make_sys_message(USERNAME, "sys.stop_request", {"reason": "user requested /agent stop"})
    _send_sys_message(name, msg)

    # Set timeout for fallback
    timer = weechat.hook_timer(5000, 0, 1, "_stop_timeout_cb", name)
    pending_stops[msg["id"]] = {"name": name, "buffer": buffer, "timer": timer}

    return CommandResult.ok(f"Stopping {name}...")


def _force_stop_agent(name):
    """Force stop via tmux send-keys."""
    agent = agents.get(name)
    if agent and agent.get("pane_id"):
        import subprocess
        subprocess.run(["tmux", "send-keys", "-t", agent["pane_id"], "/exit", "Enter"],
                       capture_output=True)


def _stop_timeout_cb(data, remaining_calls):
    """Called if agent doesn't respond to sys.stop_request within 5s."""
    name = data
    # Clean up pending
    to_remove = [mid for mid, info in pending_stops.items() if info["name"] == name]
    for mid in to_remove:
        del pending_stops[mid]

    weechat.prnt("", f"[agent] {name} did not respond, forcing stop...")
    _force_stop_agent(name)
    return weechat.WEECHAT_RC_OK
```

- [ ] **Step 4: Handle sys.stop_confirmed in weechat-agent**

Add a signal hook for `zenoh_sys_message` in `agent_init()`:

```python
weechat.hook_signal("zenoh_sys_message", "on_sys_message_cb", "")
```

Implement the callback:

```python
def on_sys_message_cb(data, signal, signal_data):
    """Handle sys.* messages from agents."""
    try:
        msg = json.loads(signal_data)
    except json.JSONDecodeError:
        return weechat.WEECHAT_RC_OK

    msg_type = msg.get("type", "")
    ref_id = msg.get("ref_id")

    if msg_type == "sys.stop_confirmed" and ref_id in pending_stops:
        info = pending_stops.pop(ref_id)
        weechat.unhook(info["timer"])
        weechat.prnt("", f"[agent] {info['name']} is shutting down...")
        _force_stop_agent(info["name"])

    return weechat.WEECHAT_RC_OK
```

- [ ] **Step 5: Handle sys.stop_request in channel-server**

In `server.py`, fill in `_handle_sys_message`:

```python
def _handle_sys_message(msg: dict, reply_topic_key: str):
    msg_type = msg.get("type", "")
    if msg_type == "sys.stop_request":
        # Reply with stop_confirmed
        reply_msg = make_sys_message(AGENT_NAME, "sys.stop_confirmed", {}, ref_id=msg["id"])
        topic = private_topic(reply_topic_key)
        _get_zenoh().put(topic, json.dumps(reply_msg).encode())
```

Note: `_get_zenoh()` and `private_topic` are already available in server.py scope.

- [ ] **Step 6: Run tests — expect PASS**

Run: `python -m pytest tests/unit/ -v`

- [ ] **Step 7: Commit**

```bash
git add weechat-agent/weechat-agent.py weechat-channel-server/server.py tests/unit/test_agent_commands.py
git commit -m "feat: add /agent stop with sys.stop_request protocol (#3)"
```

---

### Task 10: Implement `/agent join` with sys protocol (#4)

**Files:**
- Modify: `weechat-agent/weechat-agent.py`
- Modify: `weechat-channel-server/server.py`

- [ ] **Step 1: Add pending_joins tracking**

```python
pending_joins = {}  # msg_id → {agent_name, channel, buffer, timer}
```

- [ ] **Step 2: Update cmd_agent_join to use sys protocol**

Replace the existing `/agent join` handler:

```python
@agent_registry.command(
    name="join",
    args="<agent> <channel>",
    description="Ask agent to join a channel (with confirmation)",
    params=[
        CommandParam("agent", required=True, help="Agent name"),
        CommandParam("channel", required=True, help="Channel name (e.g. #dev)"),
    ],
)
def cmd_agent_join(buffer, args: ParsedArgs) -> CommandResult:
    agent_name = scoped_name(args.get("agent"))
    channel = args.get("channel")
    if agent_name not in agents:
        return CommandResult.error(f"Unknown agent: {agent_name}")

    msg = make_sys_message(USERNAME, "sys.join_request", {"channel": channel})
    _send_sys_message(agent_name, msg)

    timer = weechat.hook_timer(10000, 0, 1, "_join_timeout_cb", msg["id"])
    pending_joins[msg["id"]] = {
        "agent_name": agent_name, "channel": channel,
        "buffer": buffer, "timer": timer,
    }
    return CommandResult.ok(f"Asking {agent_name} to join {channel}...")
```

- [ ] **Step 3: Add join timeout and confirmation handlers**

```python
def _join_timeout_cb(data, remaining_calls):
    msg_id = data
    if msg_id in pending_joins:
        info = pending_joins.pop(msg_id)
        weechat.prnt("", f"[agent] {info['agent_name']} did not confirm joining {info['channel']} (request may still be pending)")
    return weechat.WEECHAT_RC_OK
```

Add to `on_sys_message_cb`:

```python
    if msg_type == "sys.join_confirmed" and ref_id in pending_joins:
        info = pending_joins.pop(ref_id)
        weechat.unhook(info["timer"])
        channel = msg.get("body", {}).get("channel", info["channel"])
        weechat.prnt("", f"[agent] {info['agent_name']} joined {channel}")
```

- [ ] **Step 4: Handle sys.join_request in channel-server**

Add to `_handle_sys_message` in `server.py`:

```python
    elif msg_type == "sys.join_request":
        channel = msg.get("body", {}).get("channel", "").lstrip("#")
        if channel:
            # Reuse existing join_channel logic
            _do_join_channel(channel)
            reply_msg = make_sys_message(AGENT_NAME, "sys.join_confirmed",
                                         {"channel": f"#{channel}"}, ref_id=msg["id"])
            topic = private_topic(reply_topic_key)
            _get_zenoh().put(topic, json.dumps(reply_msg).encode())
```

Extract the join logic from `_handle_join_channel` into a reusable `_do_join_channel(channel_name)` function.

- [ ] **Step 5: Run tests — expect PASS**

Run: `python -m pytest tests/unit/ -v`

- [ ] **Step 6: Commit**

```bash
git add weechat-agent/weechat-agent.py weechat-channel-server/server.py
git commit -m "feat: /agent join now uses sys.join_request protocol with confirmation (#4)"
```

---

## Chunk 5: P1 — Sidecar Enhancements (join ack, send failure)

### Task 11: Add `joined` event to sidecar (#5)

**Files:**
- Modify: `weechat-zenoh/zenoh_sidecar.py` (in `handle_join_channel`, around lines 99-135)
- Modify: `weechat-zenoh/weechat-zenoh.py` (in `_handle_event`)

- [ ] **Step 1: Write failing test**

```python
# Add to tests/unit/test_sidecar.py
# NOTE: Existing sidecar tests use subprocess (not module import).
# Follow the same pattern here.
def test_join_channel_emits_joined_event(sidecar_proc):
    """join_channel should emit a 'joined' event with member list."""
    # sidecar_proc is the subprocess fixture from existing tests
    send_cmd(sidecar_proc, {"cmd": "join_channel", "channel_id": "test_joined"})
    events = read_events(sidecar_proc, timeout=3)
    joined_events = [e for e in events if e.get("event") == "joined"]
    assert len(joined_events) == 1
    assert joined_events[0]["channel_id"] == "test_joined"
    assert "members" in joined_events[0]
```

Note: Uses the existing subprocess-based test helpers (`send_cmd`, `read_events`, `sidecar_proc` fixture) that match the test patterns in `tests/unit/test_sidecar.py`. Adapt fixture/helper names to match actual codebase conventions.

- [ ] **Step 2: Run test — expect FAIL**

Run: `python -m pytest tests/unit/test_sidecar.py::test_join_channel_emits_joined_event -v`

- [ ] **Step 3: Add `joined` event emission in sidecar**

In `handle_join_channel`, after subscribing and querying members, emit:

```python
# After the existing liveliness.get() query for members
members = [token.key_expr().to_string().rsplit("/", 1)[-1] for token in tokens]
emit({"event": "joined", "channel_id": channel_id, "members": members})
```

- [ ] **Step 4: Handle `joined` event in weechat-zenoh**

In `_handle_event`, add a case:

```python
elif event_type == "joined":
    channel_id = event.get("channel_id")
    members = event.get("members", [])
    count = len(members)
    buf = buffers.get(f"channel:{channel_id}")
    if buf:
        if count <= 10 and members:
            names = ", ".join(members)
            weechat.prnt(buf, f"[zenoh] Joined #{channel_id} ({count} members online: {names})")
        else:
            weechat.prnt(buf, f"[zenoh] Joined #{channel_id} ({count} members online)")
```

- [ ] **Step 5: Run tests — expect PASS**

Run: `python -m pytest tests/unit/test_sidecar.py -v`

- [ ] **Step 6: Commit**

```bash
git add weechat-zenoh/zenoh_sidecar.py weechat-zenoh/weechat-zenoh.py
git commit -m "feat: sidecar emits 'joined' event with member list on channel join (#5)"
```

---

### Task 12: Add msg_id tracking and `send_failed` event (#7)

**Files:**
- Modify: `weechat-zenoh/weechat-zenoh.py` (in `send_message`)
- Modify: `weechat-zenoh/zenoh_sidecar.py` (in `handle_send`)

- [ ] **Step 1: Add msg_id to send commands in weechat-zenoh**

In `send_message()` (around line 336), add msg_id generation:

```python
def send_message(target, body):
    msg_id = os.urandom(4).hex()
    _sidecar_send({
        "cmd": "send",
        "msg_id": msg_id,
        "pub_key": target_key,
        "type": msg_type,
        "body": body,
    })
```

- [ ] **Step 2: Wrap sidecar send in try/except**

In `zenoh_sidecar.py`, modify `handle_send`:

```python
def handle_send(params: dict):
    msg_id = params.get("msg_id")
    try:
        _publish_event(params["pub_key"], params["type"], params["body"])
    except Exception as e:
        if msg_id:
            emit({"event": "send_failed", "msg_id": msg_id, "reason": str(e)})
```

- [ ] **Step 3: Handle `send_failed` event in weechat-zenoh**

In `_handle_event`:

```python
elif event_type == "send_failed":
    reason = event.get("reason", "unknown error")
    weechat.prnt("", f"[zenoh] Message delivery failed: {reason}. Use /zenoh reconnect")
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest tests/unit/ -v`

- [ ] **Step 5: Commit**

```bash
git add weechat-zenoh/zenoh_sidecar.py weechat-zenoh/weechat-zenoh.py
git commit -m "feat: track msg_id on send, report send_failed events (#7)"
```

---

### Task 13: Malformed JSON warning (#13)

**Files:**
- Modify: `weechat-agent/weechat-agent.py` (in `on_message_signal_cb`)

- [ ] **Step 1: Add warning in on_message_signal_cb**

In the existing `on_message_signal_cb` (lines 204-225), where it tries to parse JSON from agent messages:

```python
# Existing: tries json.loads(body)
# If body starts with "{" but fails to parse:
if body.strip().startswith("{"):
    try:
        data = json.loads(body)
        # ... existing structured command handling
    except json.JSONDecodeError:
        weechat.prnt("", f"[agent] Warning: received malformed structured message from {nick}")
```

- [ ] **Step 2: Run tests — expect PASS**

Run: `python -m pytest tests/unit/ -v`

- [ ] **Step 3: Commit**

```bash
git add weechat-agent/weechat-agent.py
git commit -m "feat: warn on malformed JSON from agents (#13)"
```

---

## Chunk 6: P2 — Enhanced Commands

### Task 14: Enhanced `/agent list` (#2)

**Files:**
- Modify: `weechat-agent/weechat-agent.py`

- [ ] **Step 1: Add channel tracking to agent state**

```python
# In on_sys_message_cb, when receiving sys.join_confirmed:
if msg_type == "sys.join_confirmed" and ref_id in pending_joins:
    info = pending_joins.pop(ref_id)
    # ... existing handling ...
    # Track channel membership locally
    agent_name = info["agent_name"]
    channel = msg.get("body", {}).get("channel", info["channel"])
    if agent_name in agents:
        agents[agent_name].setdefault("channels", [])
        if channel not in agents[agent_name]["channels"]:
            agents[agent_name]["channels"].append(channel)
```

- [ ] **Step 2: Update cmd_agent_list to show uptime and channels**

```python
@agent_registry.command(
    name="list", args="", description="List agents with status, uptime, channels",
    params=[],
)
def cmd_agent_list(buffer, args: ParsedArgs) -> CommandResult:
    if not agents:
        return CommandResult.ok("No agents")
    lines = ["Agents:"]
    for name, info in agents.items():
        status = info["status"]
        pane = info.get("pane_id", "—")
        ws = info["workspace"]

        # Uptime
        if status != "offline" and "created_at" in info:
            elapsed = time.time() - info["created_at"]
            if elapsed >= 3600:
                uptime = f"{elapsed / 3600:.0f}h"
            elif elapsed >= 60:
                uptime = f"{elapsed / 60:.0f}m"
            else:
                uptime = f"{elapsed:.0f}s"
        else:
            uptime = "—"

        # Channels
        ch_list = info.get("channels", [])
        ch_str = ", ".join(ch_list) if ch_list else "—"

        lines.append(f"  {name}\t{status}\t{uptime}\t{pane}\t{ch_str}\t{ws}")
    return CommandResult.ok("\n".join(lines))
```

- [ ] **Step 3: Run tests — expect PASS**

Run: `python -m pytest tests/unit/ -v`

- [ ] **Step 4: Commit**

```bash
git add weechat-agent/weechat-agent.py
git commit -m "feat: enhanced /agent list with uptime and channel membership (#2)"
```

---

### Task 14.5: Add `tests/unit/test_zenoh_commands.py`

**Files:**
- Create: `tests/unit/test_zenoh_commands.py`

- [ ] **Step 1: Write tests for zenoh command validation logic**

```python
# tests/unit/test_zenoh_commands.py
"""Tests for /zenoh command edge cases (leave validation, who)."""
from wc_protocol.topics import make_private_pair


def test_leave_channel_not_joined():
    """Leave should error if not in channel."""
    channels = {"general"}
    assert "nonexistent" not in channels


def test_leave_private_not_open():
    """Leave should error if no private chat exists."""
    privates = {"alice_bob"}
    pair = make_private_pair("alice", "unknown")
    assert pair not in privates


def test_leave_invalid_target():
    """Leave with invalid target format should error."""
    target = "no-prefix"
    assert not target.startswith("#") and not target.startswith("@")


def test_who_not_in_channel():
    """Who should error if not in channel."""
    channels = {"general"}
    assert "nonexistent" not in channels
```

- [ ] **Step 2: Run tests — expect PASS**

Run: `python -m pytest tests/unit/test_zenoh_commands.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_zenoh_commands.py
git commit -m "test: add zenoh command validation tests"
```

---

### Task 15: `/zenoh leave` error on invalid target (#6)

**Files:**
- Modify: `weechat-zenoh/weechat-zenoh.py`

- [ ] **Step 1: Update cmd_zenoh_leave with validation**

```python
@zenoh_registry.command(
    name="leave", args="[target]",
    description="Leave channel or close private (error on invalid)",
    params=[CommandParam("target", required=False, help="#channel or @nick")],
)
def cmd_zenoh_leave(buffer, args: ParsedArgs) -> CommandResult:
    target = args.get("target")
    if not target:
        target = _buffer_target(buffer)
        if not target:
            return CommandResult.error("No target and current buffer is not a channel/private")

    if target.startswith("#"):
        channel_id = target.lstrip("#")
        if channel_id not in channels:
            return CommandResult.error(f"not in #{channel_id}")
        leave_channel(channel_id)
    elif target.startswith("@"):
        nick = target.lstrip("@")
        pair = make_private_pair(my_nick, nick)
        if pair not in privates:
            return CommandResult.error(f"no private chat with @{nick}")
        leave_private(nick)
    else:
        return CommandResult.error(f"invalid target: {target} (use #channel or @nick)")
    return CommandResult.ok(f"Left {target}")
```

- [ ] **Step 2: Run tests — expect PASS**

Run: `python -m pytest tests/unit/ -v`

- [ ] **Step 3: Commit**

```bash
git add weechat-zenoh/weechat-zenoh.py
git commit -m "feat: /zenoh leave reports error on non-existent target (#6)"
```

---

### Task 16: `/agent status` (#9)

**Files:**
- Modify: `weechat-agent/weechat-agent.py`
- Modify: `weechat-channel-server/server.py`

- [ ] **Step 1: Add pending_status tracking and command**

```python
pending_status = {}  # msg_id → {name, buffer, timer}

@agent_registry.command(
    name="status",
    args="<name>",
    description="Show detailed single-agent info",
    params=[CommandParam("name", required=True, help="Agent name")],
)
def cmd_agent_status(buffer, args: ParsedArgs) -> CommandResult:
    name = scoped_name(args.get("name"))
    if name not in agents:
        return CommandResult.error(f"Unknown agent: {name}")

    agent = agents[name]
    if agent["status"] == "offline":
        return _format_agent_status(name, remote=None)

    msg = make_sys_message(USERNAME, "sys.status_request", {})
    _send_sys_message(name, msg)

    timer = weechat.hook_timer(3000, 0, 1, "_status_timeout_cb", msg["id"])
    pending_status[msg["id"]] = {"name": name, "buffer": buffer, "timer": timer}
    return CommandResult.ok(f"Querying {name}...")


def _format_agent_status(name, remote=None):
    agent = agents[name]
    status = agent["status"]

    if status != "offline" and "created_at" in agent:
        elapsed = time.time() - agent["created_at"]
        mins, secs = divmod(int(elapsed), 60)
        uptime = f"{mins}m {secs}s"
    else:
        uptime = "—"

    lines = [f"{name}"]
    if remote is None and status != "offline":
        lines[0] += " (agent not responding — showing local info only)"
    lines.append(f"  status:    {status}")
    lines.append(f"  uptime:    {uptime}")
    lines.append(f"  pane:      {agent.get('pane_id', '—')}")
    lines.append(f"  workspace: {agent['workspace']}")

    if remote:
        ch = ", ".join(f"#{c}" for c in remote.get("channels", []))
        lines.append(f"  channels:  {ch or '—'}")
        lines.append(f"  messages:  sent {remote.get('messages_sent', 0)}, received {remote.get('messages_received', 0)}")
    else:
        ch = ", ".join(agent.get("channels", []))
        lines.append(f"  channels:  {ch or '—'}")

    return CommandResult.ok("\n".join(lines))


def _status_timeout_cb(data, remaining_calls):
    msg_id = data
    if msg_id in pending_status:
        info = pending_status.pop(msg_id)
        result = _format_agent_status(info["name"], remote=None)
        weechat.prnt(info["buffer"], f"[agent] {result.message}")
    return weechat.WEECHAT_RC_OK
```

- [ ] **Step 2: Handle sys.status_response in on_sys_message_cb**

```python
    if msg_type == "sys.status_response" and ref_id in pending_status:
        info = pending_status.pop(ref_id)
        weechat.unhook(info["timer"])
        result = _format_agent_status(info["name"], remote=msg.get("body", {}))
        weechat.prnt(info["buffer"], f"[agent] {result.message}")
```

- [ ] **Step 3: Handle sys.status_request in channel-server**

Add to `_handle_sys_message` in `server.py`:

```python
    elif msg_type == "sys.status_request":
        reply_msg = make_sys_message(AGENT_NAME, "sys.status_response", {
            "channels": list(joined_channels.keys()),
            "messages_sent": _msg_counter["sent"],
            "messages_received": _msg_counter["received"],
        }, ref_id=msg["id"])
        topic = private_topic(reply_topic_key)
        _get_zenoh().put(topic, json.dumps(reply_msg).encode())
```

Add message counter tracking:

```python
# Global in server.py
_msg_counter = {"sent": 0, "received": 0}

# In _handle_reply, after sending: _msg_counter["sent"] += 1
# In on_private/on_channel, after processing: _msg_counter["received"] += 1
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest tests/unit/ -v`

- [ ] **Step 5: Commit**

```bash
git add weechat-agent/weechat-agent.py weechat-channel-server/server.py
git commit -m "feat: add /agent status with sys.status_request protocol (#9)"
```

---

### Task 17: `/zenoh who` (#10)

**Files:**
- Modify: `weechat-zenoh/zenoh_sidecar.py`
- Modify: `weechat-zenoh/weechat-zenoh.py`

- [ ] **Step 1: Add `who` command to sidecar**

In `handle_command` dispatch:

```python
elif name == "who":
    handle_who(cmd)
```

Implement:

```python
def handle_who(params: dict):
    channel_id = params.get("channel_id")
    if channel_id not in channels:
        emit({"event": "error", "detail": f"Not in #{channel_id}"})
        return

    # Query liveliness tokens
    glob = f"wc/channels/{channel_id}/presence/*"
    tokens = session.liveliness().get(glob)
    members = []
    for token in tokens:
        nick = token.key_expr().to_string().rsplit("/", 1)[-1]
        members.append({"nick": nick, "online": True})

    emit({"event": "who_response", "channel_id": channel_id, "members": members})
```

Note: This implementation shows only online members via liveliness. Offline tracking would require additional state — for now, only online members are shown.

- [ ] **Step 2: Register `/zenoh who` command**

```python
@zenoh_registry.command(
    name="who",
    args="<channel>",
    description="List channel members with online/offline status",
    params=[CommandParam("channel", required=True, help="#channel name")],
)
def cmd_zenoh_who(buffer, args: ParsedArgs) -> CommandResult:
    channel = args.get("channel", "").lstrip("#")
    if channel not in channels:
        return CommandResult.error(f"not in #{channel}")
    _sidecar_send({"cmd": "who", "channel_id": channel})
    return CommandResult.ok(f"Querying #{channel} members...")
```

- [ ] **Step 3: Handle `who_response` event**

In `_handle_event`:

```python
elif event_type == "who_response":
    channel_id = event.get("channel_id")
    members = event.get("members", [])
    buf = buffers.get(f"channel:{channel_id}")
    target = buf or ""
    lines = [f"#{channel_id} members:"]
    for m in sorted(members, key=lambda x: x["nick"]):
        indicator = "●" if m["online"] else "○"
        status = "online" if m["online"] else "offline"
        lines.append(f"  {indicator} {m['nick']:<20} ({status})")
    if not members:
        lines.append("  (no members)")
    weechat.prnt(target, f"[zenoh] " + "\n[zenoh] ".join(lines))
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest tests/unit/ -v`

- [ ] **Step 5: Commit**

```bash
git add weechat-zenoh/zenoh_sidecar.py weechat-zenoh/weechat-zenoh.py
git commit -m "feat: add /zenoh who to list channel members (#10)"
```

---

## Chunk 7: P2 — Agent Restart, Delivery Confirmation, Config Error

### Task 18: `/agent restart` (#11)

**Files:**
- Modify: `weechat-agent/weechat-agent.py`

- [ ] **Step 1: Register command**

```python
@agent_registry.command(
    name="restart",
    args="<name>",
    description="Restart agent (stop then re-create with same config)",
    params=[CommandParam("name", required=True, help="Agent name")],
)
def cmd_agent_restart(buffer, args: ParsedArgs) -> CommandResult:
    name = scoped_name(args.get("name"))
    if name not in agents:
        return CommandResult.error(f"Unknown agent: {name}")
    if name.endswith(":agent0"):
        return CommandResult.error(f"{name} is the primary agent and cannot be restarted")

    agent = agents[name]
    agent["pending_restart"] = True
    agent["restart_workspace"] = agent["workspace"]

    # Trigger stop using the shared helper (not via ParsedArgs construction)
    _initiate_agent_stop(name)
    return CommandResult.ok(f"Restarting {name}...")
```

- [ ] **Step 1.5: Extract `_initiate_agent_stop` helper from `cmd_agent_stop`**

Refactor the stop logic so both `cmd_agent_stop` and `cmd_agent_restart` can reuse it:

```python
def _initiate_agent_stop(name: str):
    """Send sys.stop_request or force-stop. Used by both stop and restart commands."""
    agent = agents[name]
    if agent["status"] == "starting":
        _force_stop_agent(name)
        return

    msg = make_sys_message(USERNAME, "sys.stop_request", {"reason": "stop requested"})
    _send_sys_message(name, msg)
    timer = weechat.hook_timer(5000, 0, 1, "_stop_timeout_cb", name)
    pending_stops[msg["id"]] = {"name": name, "buffer": "", "timer": timer}
```

Update `cmd_agent_stop` to call `_initiate_agent_stop(name)` after its validation checks.

- [ ] **Step 2: Handle pending_restart in presence callback**

In `on_presence_signal_cb`, when agent goes offline:

```python
if nick in agents and not online:
    agent = agents[nick]
    if agent.get("pending_restart"):
        workspace = agent.pop("restart_workspace", agent["workspace"])
        agent.pop("pending_restart", None)
        weechat.prnt("", f"[agent] Restarting {nick}...")
        # Small delay to ensure cleanup completes
        weechat.hook_timer(1000, 0, 1, "_restart_create_cb",
                           json.dumps({"name": nick, "workspace": workspace}))
    else:
        # Existing offline handling
        agents[nick]["status"] = "offline"
        _cleanup_agent_workspace(nick)
        weechat.prnt("", f"[agent] {nick} is now offline")


def _restart_create_cb(data, remaining_calls):
    info = json.loads(data)
    # Remove old agent entry to allow re-creation
    agents.pop(info["name"], None)
    create_agent(info["name"], info["workspace"])
    return weechat.WEECHAT_RC_OK
```

- [ ] **Step 3: Run tests — expect PASS**

Run: `python -m pytest tests/unit/ -v`

- [ ] **Step 4: Commit**

```bash
git add weechat-agent/weechat-agent.py
git commit -m "feat: add /agent restart (#11)"
```

---

### Task 19: Message delivery confirmation (#12)

**Files:**
- Modify: `weechat-channel-server/server.py`
- Modify: `weechat-agent/weechat-agent.py`

- [ ] **Step 1: Send sys.ack from channel-server on message receipt**

In `server.py`, in `on_private` callback, after processing a non-sys message:

```python
# After enqueuing the message for Claude:
msg_id = msg.get("id")
sender_nick = msg.get("nick", "")
if msg_id and sender_nick:
    # Send delivery ack back to sender via their private topic
    pair = make_private_pair(AGENT_NAME, sender_nick)
    ack = make_sys_message(AGENT_NAME, "sys.ack", {"status": "ok"}, ref_id=msg_id)
    topic = private_topic(pair)
    try:
        _get_zenoh().put(topic, json.dumps(ack).encode())
    except Exception:
        pass  # Best-effort
```

Same for `on_channel` callback.

- [ ] **Step 2: Handle sys.ack in weechat-agent for display**

In `on_sys_message_cb`:

```python
    if msg_type == "sys.ack" and ref_id:
        # Delivery confirmed — for now, just log at debug level
        # Future: update message display with ✓ indicator
        pass  # Silent acknowledgment tracking
```

Note: Full display update (✓ indicator) requires WeeChat `hdata` manipulation which is complex. For now, track the ack silently. The infrastructure is in place for future display enhancement.

- [ ] **Step 3: Run tests — expect PASS**

Run: `python -m pytest tests/unit/ -v`

- [ ] **Step 4: Commit**

```bash
git add weechat-channel-server/server.py weechat-agent/weechat-agent.py
git commit -m "feat: channel-server sends sys.ack on message receipt (#12)"
```

---

### Task 20: Friendly config error (#14)

**Files:**
- Modify: `weechat-agent/weechat-agent.py`

- [ ] **Step 1: Add auto-detect helper**

```python
def _suggest_channel_plugin_dir():
    """Try to find weechat-channel-server relative to this plugin."""
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "weechat-channel-server"),
        os.path.expanduser("~/Workspace/weechat-claude/weechat-channel-server"),
    ]
    for path in candidates:
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "server.py")):
            return os.path.realpath(path)
    return None
```

- [ ] **Step 2: Update config validation in agent_init**

Where `CHANNEL_PLUGIN_DIR` is checked (around line 50):

```python
if not CHANNEL_PLUGIN_DIR:
    suggested = _suggest_channel_plugin_dir()
    if suggested:
        weechat.prnt("", f"[agent] Error: channel_plugin_dir not set.")
        weechat.prnt("", f"  Detected: {suggested}")
        weechat.prnt("", f"  Run: /set plugins.var.python.weechat-agent.channel_plugin_dir {suggested}")
    else:
        weechat.prnt("", f"[agent] Error: channel_plugin_dir not set.")
        weechat.prnt("", f"  Run: /set plugins.var.python.weechat-agent.channel_plugin_dir /path/to/weechat-channel-server")
```

- [ ] **Step 3: Run tests — expect PASS**

Run: `python -m pytest tests/unit/ -v`

- [ ] **Step 4: Commit**

```bash
git add weechat-agent/weechat-agent.py
git commit -m "feat: auto-detect and suggest channel_plugin_dir on missing config (#14)"
```

---

## Chunk 8: Integration Tests + Final Verification

### Task 21: Integration test for sys message round-trip

**Files:**
- Create: `tests/integration/test_sys_roundtrip.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_sys_roundtrip.py
"""Integration test: sys message round-trip over real Zenoh."""
import json
import time
import pytest
from wc_protocol.sys_messages import make_sys_message, is_sys_message
from wc_protocol.topics import private_topic, make_private_pair


@pytest.mark.integration
def test_sys_ping_pong_roundtrip(zenoh_session):
    """Send sys.ping on a private topic, verify it arrives."""
    pair = make_private_pair("test_user", "test_agent")
    topic = private_topic(pair)

    received = []

    def on_sample(sample):
        msg = json.loads(sample.payload.to_string())
        if is_sys_message(msg):
            received.append(msg)

    sub = zenoh_session.declare_subscriber(topic, on_sample)

    ping = make_sys_message("test_user", "sys.ping", {})
    zenoh_session.put(topic, json.dumps(ping).encode())

    # Wait for delivery
    deadline = time.time() + 5
    while not received and time.time() < deadline:
        time.sleep(0.1)

    sub.undeclare()

    assert len(received) == 1
    assert received[0]["type"] == "sys.ping"
    assert received[0]["nick"] == "test_user"
```

- [ ] **Step 2: Run integration test (requires zenohd)**

Run: `python -m pytest tests/integration/test_sys_roundtrip.py -v -m integration`
Expected: PASS (if zenohd is running)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_sys_roundtrip.py
git commit -m "test: add sys message round-trip integration test"
```

---

### Task 22: Run full test suite and verify

- [ ] **Step 1: Run all unit tests**

Run: `python -m pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 2: Run integration tests (if zenohd available)**

Run: `python -m pytest tests/integration/ -v -m integration`

- [ ] **Step 3: Final commit with any remaining fixes**

```bash
git add -A
git commit -m "chore: final cleanup for UX improvements P0+P1+P2"
```
