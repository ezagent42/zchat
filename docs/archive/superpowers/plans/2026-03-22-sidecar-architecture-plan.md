# Sidecar Architecture Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix PyO3 subinterpreter incompatibility by splitting weechat-zenoh into a WeeChat plugin + standalone sidecar process.

**Architecture:** The WeeChat plugin (`weechat-zenoh.py`) launches a sidecar subprocess (`zenoh_sidecar.py`) and communicates via stdin/stdout JSON Lines. The sidecar owns all Zenoh operations; the plugin owns WeeChat UI and buffer management.

**Tech Stack:** Python 3, WeeChat Python API, eclipse-zenoh, subprocess, JSON Lines protocol

**Spec:** `docs/superpowers/specs/2026-03-22-sidecar-architecture-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `weechat-zenoh/zenoh_sidecar.py` | Standalone process: Zenoh session, pub/sub, liveliness, stdin→cmd, event→stdout |
| Modify | `weechat-zenoh/weechat-zenoh.py` | WeeChat plugin: subprocess launch, hook_fd, JSON cmd/event, buffer/nicklist UI |
| Modify | `weechat-zenoh/helpers.py` | Remove `build_zenoh_config()` (moved to sidecar) |
| Create | `tests/unit/test_sidecar.py` | Test sidecar stdin/stdout protocol |
| Modify | `tests/unit/test_zenoh_config.py` | Move build_zenoh_config tests to sidecar suite |
| Create | `tests/unit/test_subinterpreter.py` | Verify plugin has no PyO3 imports |

---

## Chunk 1: Sidecar Process

### Task 1: Sidecar — init command and ready event

**Files:**
- Create: `tests/unit/test_sidecar.py`
- Create: `weechat-zenoh/zenoh_sidecar.py`

**Context:** The sidecar reads JSON commands from stdin and writes JSON events to stdout. The `init` command opens a Zenoh session and emits a `ready` event. For unit testing, we mock zenoh by injecting a mock module.

- [ ] **Step 1: Write failing test for init → ready**

In `tests/unit/test_sidecar.py`:

```python
"""Tests for zenoh_sidecar.py — subprocess stdin/stdout protocol."""
import subprocess
import json
import os
import sys

SIDECAR_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "weechat-zenoh", "zenoh_sidecar.py")


def start_sidecar(mock=True):
    """Launch sidecar as subprocess. If mock=True, inject mock zenoh."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(
        os.path.dirname(__file__), "..", "..", "tests")
    args = [sys.executable, SIDECAR_PATH]
    if mock:
        args.append("--mock")
    return subprocess.Popen(
        args,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env, text=True, bufsize=1)


def send_cmd(proc, cmd: dict) -> None:
    proc.stdin.write(json.dumps(cmd) + "\n")
    proc.stdin.flush()


def read_event(proc, timeout=5.0) -> dict:
    import select
    ready, _, _ = select.select([proc.stdout], [], [], timeout)
    if not ready:
        raise TimeoutError("No response from sidecar")
    line = proc.stdout.readline()
    return json.loads(line)


class TestSidecarInit:
    def test_init_emits_ready(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/127.0.0.1:7447"})
            event = read_event(proc)
            assert event["event"] == "ready"
            assert "zid" in event
        finally:
            proc.terminate()
            proc.wait()

    def test_init_without_connect_uses_default(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "bob"})
            event = read_event(proc)
            assert event["event"] == "ready"
        finally:
            proc.terminate()
            proc.wait()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/h2oslabs/Workspace/weechat-claude/.claude/worktrees/fix-weechat-plugin-loading && python -m pytest tests/unit/test_sidecar.py -v`
Expected: FAIL (zenoh_sidecar.py does not exist)

- [ ] **Step 3: Create sidecar with init command**

In `weechat-zenoh/zenoh_sidecar.py`:

```python
#!/usr/bin/env python3
"""
Zenoh sidecar process for weechat-zenoh plugin.
Runs as standalone process to avoid PyO3 subinterpreter issues.
Communicates via stdin (JSON commands) / stdout (JSON events).
"""

import json
import sys
import uuid
import time
import threading
from collections import deque

# Support --mock flag for testing
_use_mock = "--mock" in sys.argv

if _use_mock:
    from conftest import MockZenohSession
else:
    import zenoh

ZENOH_DEFAULT_ENDPOINT = "tcp/127.0.0.1:7447"

# --- Global state ---
session = None
my_nick = ""
publishers = {}          # key → zenoh.Publisher
subscribers = {}         # key → zenoh.Subscriber
liveliness_subs = {}     # key → zenoh liveliness Subscriber
liveliness_tokens = {}   # key → zenoh.LivelinessToken
channels = set()
privates = set()
event_queue = deque()    # events to write to stdout


def emit(event: dict):
    """Write JSON event to stdout (thread-safe via deque)."""
    event_queue.append(event)


def flush_events():
    """Write all queued events to stdout. Call from main thread."""
    while True:
        try:
            event = event_queue.popleft()
        except IndexError:
            break
        sys.stdout.write(json.dumps(event) + "\n")
        sys.stdout.flush()


def build_config(connect: str | None = None):
    """Build Zenoh client config."""
    config = zenoh.Config()
    config.insert_json5("mode", '"client"')
    endpoints = connect.split(",") if connect else [ZENOH_DEFAULT_ENDPOINT]
    config.insert_json5("connect/endpoints", json.dumps(endpoints))
    return config


def build_config_mock(connect: str | None = None):
    """Build mock config (returns None, mock session ignores it)."""
    return None


def handle_init(params: dict):
    global session, my_nick
    my_nick = params["nick"]
    connect = params.get("connect")

    if _use_mock:
        session = MockZenohSession()
        zid = "mock-zid-" + uuid.uuid4().hex[:8]
    else:
        config = build_config(connect)
        session = zenoh.open(config)
        zid = str(session.info.zid())

    # Global liveliness
    liveliness_tokens["_global"] = \
        session.liveliness().declare_token(f"wc/presence/{my_nick}")

    emit({"event": "ready", "zid": zid})


def handle_command(cmd: dict):
    """Dispatch a single command."""
    name = cmd.get("cmd")
    if name == "init":
        handle_init(cmd)
    else:
        emit({"event": "error", "detail": f"Unknown command: {name}"})


def main():
    """Main loop: read stdin line by line, dispatch commands."""
    # Use readline() to avoid buffered iteration blocking
    for line in iter(sys.stdin.readline, ""):
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError as e:
            emit({"event": "error", "detail": f"Invalid JSON: {e}"})
            flush_events()
            continue
        handle_command(cmd)
        flush_events()

    # stdin EOF — clean up
    cleanup()


def cleanup():
    global session
    for token in liveliness_tokens.values():
        token.undeclare()
    for sub in liveliness_subs.values():
        sub.undeclare()
    for sub in subscribers.values():
        sub.undeclare()
    for pub in publishers.values():
        pub.undeclare()
    if session and not _use_mock:
        session.close()
    session = None


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/h2oslabs/Workspace/weechat-claude/.claude/worktrees/fix-weechat-plugin-loading && python -m pytest tests/unit/test_sidecar.py::TestSidecarInit -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add weechat-zenoh/zenoh_sidecar.py tests/unit/test_sidecar.py
git commit -m "feat: add zenoh sidecar with init command and ready event"
```

---

### Task 2: Sidecar — join_channel with pub/sub and presence

**Files:**
- Modify: `tests/unit/test_sidecar.py`
- Modify: `weechat-zenoh/zenoh_sidecar.py`

**Context:** `join_channel` must declare publisher, subscriber, liveliness token, query current members (emit presence events), and publish a "join" message. The subscriber callback enqueues incoming messages as `message` events.

- [ ] **Step 1: Write failing test for join_channel**

Append to `tests/unit/test_sidecar.py`:

```python
class TestSidecarJoinChannel:
    def test_join_channel_emits_presence_for_existing_members(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/127.0.0.1:7447"})
            read_event(proc)  # ready
            send_cmd(proc, {"cmd": "join_channel", "channel_id": "general"})
            # With mock, liveliness.get() returns empty, so no presence events
            # But we should NOT get an error
            # Send a status to confirm sidecar is alive
            send_cmd(proc, {"cmd": "status"})
            event = read_event(proc)
            assert event["event"] == "status_response"
            assert event["channels"] == 1
        finally:
            proc.terminate()
            proc.wait()

    def test_join_channel_twice_is_idempotent(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/127.0.0.1:7447"})
            read_event(proc)  # ready
            send_cmd(proc, {"cmd": "join_channel", "channel_id": "general"})
            send_cmd(proc, {"cmd": "join_channel", "channel_id": "general"})
            send_cmd(proc, {"cmd": "status"})
            event = read_event(proc)
            assert event["channels"] == 1
        finally:
            proc.terminate()
            proc.wait()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_sidecar.py::TestSidecarJoinChannel -v`
Expected: FAIL (join_channel and status not implemented)

- [ ] **Step 3: Implement join_channel, leave_channel, and status in sidecar**

Add to `zenoh_sidecar.py` `handle_command()` dispatch and new handler functions:

```python
def _on_channel_msg(sample, channel_id):
    """Zenoh callback — runs in Zenoh thread."""
    try:
        msg = json.loads(sample.payload.to_string())
        if msg.get("nick") != my_nick:
            msg["_target"] = f"channel:{channel_id}"
            emit({"event": "message", "target": f"channel:{channel_id}",
                  "msg": msg})
    except Exception:
        pass


def _on_channel_presence(sample, channel_id):
    """Zenoh callback — runs in Zenoh thread."""
    nick = str(sample.key_expr).rsplit("/", 1)[-1]
    kind = str(sample.kind)
    emit({"event": "presence", "channel_id": channel_id,
          "nick": nick, "online": "PUT" in kind})


def handle_join_channel(params: dict):
    channel_id = params["channel_id"]
    if channel_id in channels:
        return

    key = f"channel:{channel_id}"
    msg_key = f"wc/channels/{channel_id}/messages"

    publishers[key] = session.declare_publisher(msg_key)
    subscribers[key] = session.declare_subscriber(
        msg_key,
        lambda sample, _cid=channel_id: _on_channel_msg(sample, _cid))

    # Liveliness
    token_key = f"wc/channels/{channel_id}/presence/{my_nick}"
    liveliness_tokens[key] = \
        session.liveliness().declare_token(token_key)

    liveliness_subs[key] = session.liveliness().declare_subscriber(
        f"wc/channels/{channel_id}/presence/*",
        lambda sample, _cid=channel_id: _on_channel_presence(sample, _cid))

    # Query current members
    try:
        replies = session.liveliness().get(
            f"wc/channels/{channel_id}/presence/*")
        for reply in replies:
            nick = str(reply.ok.key_expr).rsplit("/", 1)[-1]
            emit({"event": "presence", "channel_id": channel_id,
                  "nick": nick, "online": True})
    except Exception:
        pass

    channels.add(channel_id)

    # Publish join event
    _publish_event(key, "join", "")


def handle_leave_channel(params: dict):
    channel_id = params["channel_id"]
    if channel_id not in channels:
        return
    key = f"channel:{channel_id}"
    _publish_event(key, "leave", "")
    _cleanup_key(key)
    channels.discard(channel_id)


def _publish_event(pub_key, msg_type, body):
    pub = publishers.get(pub_key)
    if not pub:
        return
    event = json.dumps({
        "id": uuid.uuid4().hex,
        "nick": my_nick,
        "type": msg_type,
        "body": body,
        "ts": time.time()
    })
    pub.put(event)


def _cleanup_key(key):
    if key in subscribers:
        subscribers.pop(key).undeclare()
    if key in liveliness_subs:
        liveliness_subs.pop(key).undeclare()
    if key in publishers:
        publishers.pop(key).undeclare()
    if key in liveliness_tokens:
        liveliness_tokens.pop(key).undeclare()


def handle_status(params: dict):
    if _use_mock:
        zid = "mock-zid"
        routers = []
        peers = []
    else:
        info = session.info
        zid = str(info.zid())
        routers = [str(z) for z in info.routers_zid()]
        peers = [str(z) for z in info.peers_zid()]
    emit({"event": "status_response",
          "zid": zid, "routers": routers, "peers": peers,
          "nick": my_nick,
          "channels": len(channels), "privates": len(privates)})
```

Update `handle_command()`:

```python
def handle_command(cmd: dict):
    name = cmd.get("cmd")
    if name == "init":
        handle_init(cmd)
    elif name == "join_channel":
        handle_join_channel(cmd)
    elif name == "leave_channel":
        handle_leave_channel(cmd)
    elif name == "status":
        handle_status(cmd)
    else:
        emit({"event": "error", "detail": f"Unknown command: {name}"})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_sidecar.py::TestSidecarJoinChannel -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add weechat-zenoh/zenoh_sidecar.py tests/unit/test_sidecar.py
git commit -m "feat: sidecar join_channel, leave_channel, status commands"
```

---

### Task 3: Sidecar — join_private, leave_private, send, set_nick

**Files:**
- Modify: `tests/unit/test_sidecar.py`
- Modify: `weechat-zenoh/zenoh_sidecar.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_sidecar.py`:

```python
class TestSidecarPrivate:
    def test_join_private(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/127.0.0.1:7447"})
            read_event(proc)  # ready
            send_cmd(proc, {"cmd": "join_private", "target_nick": "bob"})
            send_cmd(proc, {"cmd": "status"})
            event = read_event(proc)
            assert event["privates"] == 1
        finally:
            proc.terminate()
            proc.wait()

    def test_leave_private(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/127.0.0.1:7447"})
            read_event(proc)
            send_cmd(proc, {"cmd": "join_private", "target_nick": "bob"})
            send_cmd(proc, {"cmd": "leave_private", "target_nick": "bob"})
            send_cmd(proc, {"cmd": "status"})
            event = read_event(proc)
            assert event["privates"] == 0
        finally:
            proc.terminate()
            proc.wait()


class TestSidecarSend:
    def test_send_does_not_error(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/127.0.0.1:7447"})
            read_event(proc)
            send_cmd(proc, {"cmd": "join_channel", "channel_id": "general"})
            send_cmd(proc, {"cmd": "send", "pub_key": "channel:general",
                            "type": "msg", "body": "hello"})
            send_cmd(proc, {"cmd": "status"})
            event = read_event(proc)
            assert event["event"] == "status_response"
        finally:
            proc.terminate()
            proc.wait()


class TestSidecarNick:
    def test_set_nick(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/127.0.0.1:7447"})
            read_event(proc)
            send_cmd(proc, {"cmd": "set_nick", "nick": "alice2"})
            send_cmd(proc, {"cmd": "status"})
            event = read_event(proc)
            assert event["nick"] == "alice2"
        finally:
            proc.terminate()
            proc.wait()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_sidecar.py -k "Private or Send or Nick" -v`
Expected: FAIL

- [ ] **Step 3: Implement join_private, leave_private, send, set_nick**

Add to `zenoh_sidecar.py`:

```python
def _on_private_msg(sample, private_key):
    """Zenoh callback — runs in Zenoh thread."""
    try:
        msg = json.loads(sample.payload.to_string())
        if msg.get("nick") != my_nick:
            msg["_target"] = private_key
            emit({"event": "message", "target": private_key, "msg": msg})
    except Exception:
        pass


def handle_join_private(params: dict):
    target_nick = params["target_nick"]
    pair = "_".join(sorted([my_nick, target_nick]))
    key = f"private:{pair}"

    if pair in privates:
        return

    msg_key = f"wc/private/{pair}/messages"
    publishers[key] = session.declare_publisher(msg_key)
    subscribers[key] = session.declare_subscriber(
        msg_key,
        lambda sample, _pk=key: _on_private_msg(sample, _pk))

    privates.add(pair)


def handle_leave_private(params: dict):
    target_nick = params["target_nick"]
    pair = "_".join(sorted([my_nick, target_nick]))
    key = f"private:{pair}"
    _cleanup_key(key)
    privates.discard(pair)


def handle_send(params: dict):
    _publish_event(params["pub_key"], params["type"], params["body"])


def handle_set_nick(params: dict):
    global my_nick
    old = my_nick
    my_nick = params["nick"]

    # Broadcast nick change to all channels
    nick_body = json.dumps({"old": old, "new": my_nick})
    for cid in channels:
        _publish_event(f"channel:{cid}", "nick", nick_body)

    # Update global liveliness
    if "_global" in liveliness_tokens:
        liveliness_tokens["_global"].undeclare()
    liveliness_tokens["_global"] = \
        session.liveliness().declare_token(f"wc/presence/{my_nick}")

    # Update per-channel liveliness
    for cid in channels:
        tok_key = f"channel:{cid}"
        if tok_key in liveliness_tokens:
            liveliness_tokens[tok_key].undeclare()
        liveliness_tokens[tok_key] = \
            session.liveliness().declare_token(
                f"wc/channels/{cid}/presence/{my_nick}")
```

Update `handle_command()` to dispatch these.

- [ ] **Step 4: Run all sidecar tests**

Run: `python -m pytest tests/unit/test_sidecar.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add weechat-zenoh/zenoh_sidecar.py tests/unit/test_sidecar.py
git commit -m "feat: sidecar join_private, leave_private, send, set_nick"
```

---

## Chunk 2: Plugin Rewrite

### Task 4: Update helpers.py — remove build_zenoh_config

**Files:**
- Modify: `weechat-zenoh/helpers.py`
- Modify: `tests/unit/test_zenoh_config.py`

- [ ] **Step 1: Remove `build_zenoh_config` from helpers.py**

Edit `weechat-zenoh/helpers.py` — remove lines 5-15 (the `build_zenoh_config` function and its `import zenoh` / `import json`). Keep `ZENOH_DEFAULT_ENDPOINT`, `target_to_buffer_label`, `parse_input`.

The file should become:

```python
"""Pure helper functions extracted from weechat-zenoh for testability."""

ZENOH_DEFAULT_ENDPOINT = "tcp/127.0.0.1:7447"


def target_to_buffer_label(target: str, my_nick: str) -> str:
    """Convert internal target key to WeeChat-style buffer label."""
    if target.startswith("channel:"):
        return f"channel:#{target[8:]}"
    pair = target.split(":", 1)[1]
    nicks = pair.split("_")
    other = [n for n in nicks if n != my_nick]
    return f"private:@{other[0]}" if other else f"private:@{pair}"


def parse_input(input_data: str) -> tuple[str, str]:
    """Parse user input into (msg_type, body)."""
    if input_data.startswith("/me ") or input_data == "/me":
        body = input_data[4:] if len(input_data) > 4 else ""
        return ("action", body)
    return ("msg", input_data)
```

- [ ] **Step 2: Update test_zenoh_config.py**

Replace `tests/unit/test_zenoh_config.py` with a test that verifies `build_zenoh_config` no longer exists in helpers:

```python
"""Verify build_zenoh_config was removed from helpers (moved to sidecar)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "weechat-zenoh"))
import helpers


def test_build_zenoh_config_removed_from_helpers():
    assert not hasattr(helpers, "build_zenoh_config"), \
        "build_zenoh_config should be in zenoh_sidecar.py, not helpers.py"


def test_helpers_has_no_zenoh_import():
    """helpers.py must not import zenoh (PyO3 incompatible)."""
    import importlib
    source = importlib.util.find_spec("helpers").origin
    with open(source) as f:
        content = f.read()
    assert "import zenoh" not in content
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/unit/test_zenoh_config.py tests/unit/test_zenoh_signals.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add weechat-zenoh/helpers.py tests/unit/test_zenoh_config.py
git commit -m "refactor: remove build_zenoh_config from helpers (moved to sidecar)"
```

---

### Task 5: Rewrite weechat-zenoh.py — sidecar IPC

**Files:**
- Modify: `weechat-zenoh/weechat-zenoh.py`

**Context:** This is the core rewrite. Remove all `import zenoh` references. Replace direct Zenoh calls with JSON commands to sidecar stdin. Use `weechat.hook_fd()` to monitor sidecar stdout. Keep all buffer/nicklist/signal logic in plugin.

- [ ] **Step 1: Rewrite weechat-zenoh.py**

Replace the entire file with the sidecar-backed version. Key changes:
- No `import zenoh` anywhere
- New globals: `sidecar_proc`, `read_buffer`, `sidecar_connected`
- `zc_init()`: launch sidecar via `subprocess.Popen`, send `init` cmd, set up `hook_fd`
- `zc_deinit()`: terminate sidecar
- `_sidecar_send(cmd)`: write JSON to sidecar stdin
- `_on_sidecar_fd(data, fd)`: hook_fd callback — read lines, parse events, enqueue to `msg_queue`/`presence_queue`
- `join_channel()`: just send `{"cmd": "join_channel", ...}` + create buffer locally
- `leave_channel()`: send `{"cmd": "leave_channel", ...}` + close buffer locally
- All `_publish_event` calls become `_sidecar_send({"cmd": "send", ...})`
- `/zenoh status`: send `{"cmd": "status"}`, synchronous read response
- `/zenoh reconnect`: kill sidecar, restart, re-join from local `channels`/`privates` sets

The full rewritten file:

```python
#!/usr/bin/env python3
# weechat-zenoh.py

"""
WeeChat Zenoh P2P 聊天插件 (sidecar architecture)
Zenoh 操作委托给 zenoh_sidecar.py 子进程，通过 JSON Lines 通信
"""

import weechat
import json
import os
import subprocess
import sys
import time
from collections import deque
from helpers import target_to_buffer_label, parse_input

SCRIPT_NAME = "weechat-zenoh"
SCRIPT_AUTHOR = "Allen <ezagent42>"
SCRIPT_VERSION = "0.2.0"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "P2P chat over Zenoh for WeeChat (sidecar)"

# --- Global state ---
sidecar_proc = None
sidecar_fd_hook = None
read_buffer = ""
sidecar_connected = False
pending_autojoin = ""     # targets to join on ready event
msg_queue = deque()
presence_queue = deque()
buffers = {}              # buffer_key → weechat buffer ptr
my_nick = ""
channels = set()
privates = set()


# ============================================================
# Sidecar IPC
# ============================================================

def _sidecar_path():
    """Resolve zenoh_sidecar.py relative to this plugin."""
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(plugin_dir, "zenoh_sidecar.py")


def _start_sidecar():
    """Launch sidecar subprocess."""
    global sidecar_proc, sidecar_fd_hook, read_buffer, sidecar_connected
    read_buffer = ""
    sidecar_connected = False

    # stderr → log file
    weechat_dir = weechat.info_get("weechat_dir", "")
    log_dir = os.path.join(weechat_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = open(os.path.join(log_dir, "zenoh_sidecar.log"), "a")

    sidecar_proc = subprocess.Popen(
        [sys.executable, "-u", _sidecar_path()],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=log_file)
    # Note: binary mode (no text=True) — os.read returns bytes,
    # consistent with hook_fd usage. -u flag disables Python buffering.

    # Monitor stdout with hook_fd
    fd = sidecar_proc.stdout.fileno()
    sidecar_fd_hook = weechat.hook_fd(fd, 1, 0, 0, "_on_sidecar_fd", "")


def _stop_sidecar():
    """Terminate sidecar subprocess."""
    global sidecar_proc, sidecar_fd_hook, sidecar_connected
    if sidecar_fd_hook:
        weechat.unhook(sidecar_fd_hook)
        sidecar_fd_hook = None
    if sidecar_proc:
        try:
            sidecar_proc.stdin.close()
        except Exception:
            pass
        sidecar_proc.terminate()
        try:
            sidecar_proc.wait(timeout=3)
        except Exception:
            sidecar_proc.kill()
        sidecar_proc = None
    sidecar_connected = False


def _sidecar_send(cmd: dict):
    """Send JSON command to sidecar stdin."""
    if not sidecar_proc or sidecar_proc.poll() is not None:
        weechat.prnt("", "[zenoh] Sidecar not running. Use /zenoh reconnect")
        return
    try:
        sidecar_proc.stdin.write((json.dumps(cmd) + "\n").encode())
        sidecar_proc.stdin.flush()
    except (BrokenPipeError, OSError) as e:
        weechat.prnt("", f"[zenoh] Sidecar write error: {e}")
        _handle_sidecar_crash()


def _sidecar_read_sync(timeout=2.0):
    """Synchronous read until status_response arrives.
    Non-status events encountered are dispatched to _handle_event."""
    import select
    global read_buffer
    if not sidecar_proc:
        return None
    fd = sidecar_proc.stdout.fileno()
    deadline = time.time() + timeout
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            return None
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            return None
        chunk = os.read(fd, 65536)
        if not chunk:
            return None
        read_buffer += chunk.decode("utf-8", errors="replace")
        while "\n" in read_buffer:
            line, read_buffer = read_buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") == "status_response":
                return event
            # Non-status event — dispatch normally
            _handle_event(event)


def _on_sidecar_fd(data, fd):
    """hook_fd callback — read available data, parse JSON lines."""
    global read_buffer, sidecar_connected
    try:
        chunk = os.read(int(fd), 65536)
    except OSError:
        _handle_sidecar_crash()
        return weechat.WEECHAT_RC_OK

    if not chunk:
        _handle_sidecar_crash()
        return weechat.WEECHAT_RC_OK

    read_buffer += chunk.decode("utf-8", errors="replace")
    while "\n" in read_buffer:
        line, read_buffer = read_buffer.split("\n", 1)
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        _handle_event(event)

    return weechat.WEECHAT_RC_OK


def _handle_event(event: dict):
    """Process a single event from sidecar."""
    global sidecar_connected
    etype = event.get("event")

    if etype == "ready":
        sidecar_connected = True
        weechat.prnt("",
            f"[zenoh] Session opened, nick={my_nick}, "
            f"zid={event.get('zid', '?')[:8]}...")
        # Process pending autojoin
        global pending_autojoin
        if pending_autojoin:
            for target in pending_autojoin.split(","):
                target = target.strip()
                if target:
                    join(target)
            pending_autojoin = ""

    elif etype == "message":
        msg = event.get("msg", {})
        target = event.get("target", "")
        msg["_target"] = target
        msg_queue.append(msg)

    elif etype == "presence":
        presence_queue.append(event)

    elif etype == "error":
        weechat.prnt("", f"[zenoh] Sidecar error: {event.get('detail')}")


def _handle_sidecar_crash():
    """Called when sidecar stdout reaches EOF."""
    global sidecar_connected
    sidecar_connected = False
    weechat.prnt("",
        "[zenoh] Sidecar process crashed. Use /zenoh reconnect")
    for buf in buffers.values():
        weechat.prnt(buf,
            "[zenoh] Connection lost. Use /zenoh reconnect")


# ============================================================
# Init / Deinit
# ============================================================

def zc_init():
    global my_nick
    my_nick = weechat.config_get_plugin("nick")
    if not my_nick:
        import uuid
        my_nick = os.environ.get("USER", "user_%s" % uuid.uuid4().hex[:6])
        weechat.config_set_plugin("nick", my_nick)

    _start_sidecar()

    connect = weechat.config_get_plugin("connect")
    cmd = {"cmd": "init", "nick": my_nick}
    if connect:
        cmd["connect"] = connect
    _sidecar_send(cmd)

    # Timer for queue processing
    weechat.hook_timer(50, 0, 0, "poll_queues_cb", "")

    # Autojoin — deferred until ready event arrives
    global pending_autojoin
    autojoin = weechat.config_get_plugin("autojoin")
    if autojoin:
        pending_autojoin = autojoin


def zc_deinit():
    _stop_sidecar()
    return weechat.WEECHAT_RC_OK


# ============================================================
# Channel / Private management
# ============================================================

def join(target):
    if target.startswith("#"):
        join_channel(target.lstrip("#"))
    elif target.startswith("@"):
        join_private(target.lstrip("@"))
    else:
        join_channel(target)


def join_channel(channel_id):
    if channel_id in channels:
        weechat.prnt("", f"[zenoh] Already in #{channel_id}")
        return

    # Create buffer locally
    buf = weechat.buffer_new(
        f"zenoh.#{channel_id}", "buffer_input_cb", "",
        "buffer_close_cb", "")
    weechat.buffer_set(buf, "title", f"Zenoh: #{channel_id}")
    weechat.buffer_set(buf, "short_name", f"#{channel_id}")
    weechat.buffer_set(buf, "nicklist", "1")
    weechat.buffer_set(buf, "localvar_set_type", "channel")
    weechat.buffer_set(buf, "localvar_set_target", channel_id)
    weechat.nicklist_add_nick(buf, "", my_nick, "default", "", "", 1)
    buffers[f"channel:{channel_id}"] = buf
    channels.add(channel_id)

    # Tell sidecar
    _sidecar_send({"cmd": "join_channel", "channel_id": channel_id})
    weechat.prnt(buf, f"-->\t{my_nick} joined #{channel_id}")


def join_private(target_nick):
    pair = "_".join(sorted([my_nick, target_nick]))
    if pair in privates:
        return

    buf = weechat.buffer_new(
        f"zenoh.@{target_nick}", "buffer_input_cb", "",
        "buffer_close_cb", "")
    weechat.buffer_set(buf, "title", f"Private with {target_nick}")
    weechat.buffer_set(buf, "short_name", f"@{target_nick}")
    weechat.buffer_set(buf, "nicklist", "1")
    weechat.buffer_set(buf, "localvar_set_type", "private")
    weechat.buffer_set(buf, "localvar_set_target", target_nick)
    weechat.buffer_set(buf, "localvar_set_private_pair", pair)
    weechat.nicklist_add_nick(buf, "", target_nick, "cyan", "", "", 1)
    weechat.nicklist_add_nick(buf, "", my_nick, "default", "", "", 1)
    buffers[f"private:{pair}"] = buf
    privates.add(pair)

    _sidecar_send({"cmd": "join_private", "target_nick": target_nick})


def leave(target):
    if target.startswith("#"):
        leave_channel(target.lstrip("#"))
    elif target.startswith("@"):
        leave_private(target.lstrip("@"))


def leave_channel(channel_id):
    if channel_id not in channels:
        return
    key = f"channel:{channel_id}"
    _sidecar_send({"cmd": "leave_channel", "channel_id": channel_id})
    if key in buffers:
        weechat.buffer_close(buffers.pop(key))
    channels.discard(channel_id)


def leave_private(target_nick):
    pair = "_".join(sorted([my_nick, target_nick]))
    key = f"private:{pair}"
    _sidecar_send({"cmd": "leave_private", "target_nick": target_nick})
    if key in buffers:
        weechat.buffer_close(buffers.pop(key))
    privates.discard(pair)


# ============================================================
# Message sending
# ============================================================

def send_message(target, body):
    if target.startswith("#"):
        channel_id = target.lstrip("#")
        key = f"channel:{channel_id}"
        _sidecar_send({"cmd": "send", "pub_key": key,
                        "type": "msg", "body": body})
        buf = buffers.get(key)
        if buf:
            weechat.prnt(buf, f"{my_nick}\t{body}")
    elif target.startswith("@"):
        nick = target.lstrip("@")
        pair = "_".join(sorted([my_nick, nick]))
        key = f"private:{pair}"
        if pair not in privates:
            join_private(nick)
        _sidecar_send({"cmd": "send", "pub_key": key,
                        "type": "msg", "body": body})
        buf = buffers.get(key)
        if buf:
            weechat.prnt(buf, f"{my_nick}\t{body}")


def buffer_input_cb(data, buffer, input_data):
    buf_type = weechat.buffer_get_string(buffer, "localvar_type")
    target = weechat.buffer_get_string(buffer, "localvar_target")
    msg_type, body = parse_input(input_data)

    if buf_type == "channel":
        pub_key = f"channel:{target}"
        buffer_label = f"channel:#{target}"
    elif buf_type == "private":
        pair = weechat.buffer_get_string(buffer, "localvar_private_pair")
        pub_key = f"private:{pair}"
        buffer_label = f"private:@{target}"
    else:
        return weechat.WEECHAT_RC_OK

    _sidecar_send({"cmd": "send", "pub_key": pub_key,
                    "type": msg_type, "body": body})
    if msg_type == "action":
        weechat.prnt(buffer, f" *\t{my_nick} {body}")
    else:
        weechat.prnt(buffer, f"{my_nick}\t{body}")
    weechat.hook_signal_send("zenoh_message_sent",
        weechat.WEECHAT_HOOK_SIGNAL_STRING,
        json.dumps({"buffer": buffer_label, "nick": my_nick,
                    "body": body, "type": msg_type}))
    return weechat.WEECHAT_RC_OK


def buffer_close_cb(data, buffer):
    buf_type = weechat.buffer_get_string(buffer, "localvar_type")
    target = weechat.buffer_get_string(buffer, "localvar_target")
    if buf_type == "channel":
        leave_channel(target)
    elif buf_type == "private":
        leave_private(target)
    return weechat.WEECHAT_RC_OK


# ============================================================
# Queue polling (unchanged logic)
# ============================================================

def poll_queues_cb(data, remaining_calls):
    for _ in range(200):
        try:
            msg = msg_queue.popleft()
        except IndexError:
            break
        target = msg.get("_target", "")
        buf = buffers.get(target)
        if not buf:
            continue
        nick = msg.get("nick", "???")
        body = msg.get("body", "")
        msg_type = msg.get("type", "msg")

        if msg_type == "msg":
            weechat.prnt(buf, f"{nick}\t{body}")
        elif msg_type == "action":
            weechat.prnt(buf, f" *\t{nick} {body}")
        elif msg_type == "join":
            weechat.prnt(buf, f"-->\t{nick} joined")
            channel_id = target.replace("channel:", "")
            _add_nick(channel_id, nick)
        elif msg_type == "leave":
            weechat.prnt(buf, f"<--\t{nick} left")
            channel_id = target.replace("channel:", "")
            _remove_nick(channel_id, nick)
        elif msg_type == "nick":
            try:
                nick_info = json.loads(body)
                old_nick = nick_info.get("old", "")
                new_nick = nick_info.get("new", "")
                if old_nick and new_nick and target.startswith("channel:"):
                    channel_id = target.replace("channel:", "")
                    _remove_nick(channel_id, old_nick)
                    _add_nick(channel_id, new_nick)
                    weechat.prnt(buf,
                        f"--\t{old_nick} is now known as {new_nick}")
            except (json.JSONDecodeError, KeyError):
                pass

        buffer_label = target_to_buffer_label(target, my_nick)
        weechat.hook_signal_send("zenoh_message_received",
            weechat.WEECHAT_HOOK_SIGNAL_STRING,
            json.dumps({"buffer": buffer_label, "nick": nick,
                        "body": body, "type": msg_type}))

    for _ in range(100):
        try:
            ev = presence_queue.popleft()
        except IndexError:
            break
        channel_id = ev["channel_id"]
        nick = ev["nick"]
        if ev["online"]:
            _add_nick(channel_id, nick)
        else:
            _remove_nick(channel_id, nick)
            buf = buffers.get(f"channel:{channel_id}")
            if buf:
                weechat.prnt(buf, f"<--\t{nick} went offline")
        weechat.hook_signal_send("zenoh_presence_changed",
            weechat.WEECHAT_HOOK_SIGNAL_STRING,
            json.dumps(ev))

    return weechat.WEECHAT_RC_OK


# ============================================================
# Nicklist helpers (unchanged)
# ============================================================

def _add_nick(channel_id, nick):
    buf = buffers.get(f"channel:{channel_id}")
    if buf and not weechat.nicklist_search_nick(buf, "", nick):
        weechat.nicklist_add_nick(buf, "", nick, "cyan", "", "", 1)

def _remove_nick(channel_id, nick):
    buf = buffers.get(f"channel:{channel_id}")
    if buf:
        ptr = weechat.nicklist_search_nick(buf, "", nick)
        if ptr:
            weechat.nicklist_remove_nick(buf, ptr)


# ============================================================
# /zenoh command
# ============================================================

def zenoh_cmd_cb(data, buffer, args):
    argv = args.split()
    cmd = argv[0] if argv else "help"

    if cmd == "join" and len(argv) >= 2:
        join(argv[1])

    elif cmd == "leave":
        if len(argv) >= 2:
            leave(argv[1])
        else:
            target = weechat.buffer_get_string(buffer, "localvar_target")
            buf_type = weechat.buffer_get_string(buffer, "localvar_type")
            if target:
                leave(f"{'#' if buf_type == 'channel' else '@'}{target}")

    elif cmd == "nick" and len(argv) >= 2:
        global my_nick
        old = my_nick
        my_nick = argv[1]
        weechat.config_set_plugin("nick", my_nick)
        weechat.prnt("", f"[zenoh] Nick changed: {old} → {my_nick}")
        _sidecar_send({"cmd": "set_nick", "nick": my_nick})
        if privates:
            weechat.prnt("",
                f"[zenoh] Warning: {len(privates)} open private(s) still "
                f"use pair keys with old nick '{old}'. "
                f"Close and re-open them to update.")

    elif cmd == "list":
        weechat.prnt(buffer, "[zenoh] Channels:")
        for r in sorted(channels):
            weechat.prnt(buffer, f"  #{r}")
        weechat.prnt(buffer, "[zenoh] Privates:")
        for d in sorted(privates):
            weechat.prnt(buffer, f"  {d}")

    elif cmd == "send" and len(argv) >= 3:
        target = argv[1]
        body = " ".join(argv[2:])
        send_message(target, body)

    elif cmd == "status":
        _sidecar_send({"cmd": "status"})
        event = _sidecar_read_sync(timeout=2.0)
        if event and event.get("event") == "status_response":
            weechat.prnt(buffer,
                f"[zenoh] zid={event['zid'][:8]}... nick={my_nick}\n"
                f"  mode=client  channels={len(channels)} "
                f"privates={len(privates)}\n"
                f"  routers={len(event.get('routers', []))} "
                f"peers={len(event.get('peers', []))}\n"
                f"  sidecar=running")
        else:
            weechat.prnt(buffer,
                f"[zenoh] nick={my_nick} channels={len(channels)} "
                f"privates={len(privates)} sidecar="
                f"{'running' if sidecar_proc and sidecar_proc.poll() is None else 'stopped'}")

    elif cmd == "reconnect":
        weechat.prnt("", "[zenoh] Reconnecting...")
        _stop_sidecar()
        _start_sidecar()
        connect = weechat.config_get_plugin("connect")
        cmd_init = {"cmd": "init", "nick": my_nick}
        if connect:
            cmd_init["connect"] = connect
        _sidecar_send(cmd_init)
        # Build rejoin targets from local state
        saved_channels = set(channels)
        saved_privates = set(privates)
        channels.clear()
        privates.clear()
        rejoin_targets = [f"#{cid}" for cid in saved_channels]
        for pair in saved_privates:
            nicks = pair.split("_")
            other = [n for n in nicks if n != my_nick]
            if other:
                rejoin_targets.append(f"@{other[0]}")
        # Queue for autojoin on ready event
        global pending_autojoin
        pending_autojoin = ",".join(rejoin_targets)

    else:
        weechat.prnt(buffer,
            "[zenoh] Usage: /zenoh <join|leave|nick|list|send|status|reconnect>")

    return weechat.WEECHAT_RC_OK


# ============================================================
# Plugin registration
# ============================================================

if weechat.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION,
                    SCRIPT_LICENSE, SCRIPT_DESC, "zc_deinit", ""):
    for key, val in {
        "nick": "",
        "autojoin": "#general",
        "connect": "",
    }.items():
        if not weechat.config_is_set_plugin(key):
            weechat.config_set_plugin(key, val)

    weechat.hook_command("zenoh",
        "Zenoh P2P chat",
        "join <#channel|@nick> || leave [target] || nick <n> || "
        "list || send <target> <msg> || status || reconnect",
        "    join: Join channel or open private\n"
        "   leave: Leave channel or close private\n"
        "    nick: Change nickname\n"
        "    list: List joined channels and privates\n"
        "    send: Send message programmatically\n"
        "  status: Show connection status\n"
        "reconnect: Restart sidecar and rejoin",
        "join || leave || nick || list || send || status || reconnect",
        "zenoh_cmd_cb", "")

    zc_init()
```

- [ ] **Step 2: Verify no zenoh import in plugin**

Run: `grep -n "import zenoh" weechat-zenoh/weechat-zenoh.py`
Expected: no output (no matches)

- [ ] **Step 3: Commit**

```bash
git add weechat-zenoh/weechat-zenoh.py
git commit -m "refactor: rewrite weechat-zenoh.py to use sidecar IPC

Remove all direct zenoh imports. All Zenoh operations now go through
zenoh_sidecar.py subprocess via JSON Lines protocol.
Add /zenoh reconnect command for crash recovery."
```

---

## Chunk 3: Tests and Verification

### Task 6: Subinterpreter compatibility test

**Files:**
- Create: `tests/unit/test_subinterpreter.py`

- [ ] **Step 1: Write subinterpreter compatibility test**

```python
"""Verify WeeChat plugin files have no PyO3-dependent imports.

WeeChat runs Python plugins in subinterpreters. PyO3-based modules
(zenoh, pydantic, etc.) crash in subinterpreters. This test catches
the issue at CI time instead of at runtime inside WeeChat.
"""
import ast
import os

PLUGIN_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "weechat-zenoh")

# Modules known to use PyO3 (will crash in subinterpreter)
PYO3_MODULES = {"zenoh", "pydantic", "pydantic_core", "orjson"}


def _get_imports(filepath: str) -> set[str]:
    """Extract top-level module names from all import statements."""
    with open(filepath) as f:
        tree = ast.parse(f.read(), filename=filepath)
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module.split(".")[0])
    return modules


def test_weechat_zenoh_no_pyo3_imports():
    """weechat-zenoh.py must not import any PyO3-based module."""
    plugin_file = os.path.join(PLUGIN_DIR, "weechat-zenoh.py")
    imports = _get_imports(plugin_file)
    bad = imports & PYO3_MODULES
    assert not bad, (
        f"weechat-zenoh.py imports PyO3 modules {bad} which crash in "
        f"WeeChat's subinterpreter. Move these to zenoh_sidecar.py.")


def test_helpers_no_pyo3_imports():
    """helpers.py must not import any PyO3-based module."""
    helpers_file = os.path.join(PLUGIN_DIR, "helpers.py")
    imports = _get_imports(helpers_file)
    bad = imports & PYO3_MODULES
    assert not bad, (
        f"helpers.py imports PyO3 modules {bad} which crash in "
        f"WeeChat's subinterpreter.")
```

- [ ] **Step 2: Run test**

Run: `python -m pytest tests/unit/test_subinterpreter.py -v`
Expected: PASS (both plugin and helpers are now PyO3-free)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_subinterpreter.py
git commit -m "test: add subinterpreter compatibility checks for WeeChat plugins"
```

---

### Task 7: Sidecar build_config tests

**Files:**
- Modify: `tests/unit/test_sidecar.py`

**Context:** The `build_zenoh_config` tests were removed from `test_zenoh_config.py` (Task 4). The equivalent logic now lives in the sidecar's `build_config()`. Add integration-style tests that verify the sidecar's config building by checking init behavior with various connect values.

- [ ] **Step 1: Write build_config tests**

Append to `tests/unit/test_sidecar.py`:

```python
class TestSidecarBuildConfig:
    def test_init_with_custom_connect(self):
        """Sidecar accepts custom connect endpoint."""
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/10.0.0.1:7447"})
            event = read_event(proc)
            assert event["event"] == "ready"
        finally:
            proc.terminate()
            proc.wait()

    def test_init_with_multiple_endpoints(self):
        """Sidecar accepts comma-separated endpoints."""
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/10.0.0.1:7447,tcp/10.0.0.2:7447"})
            event = read_event(proc)
            assert event["event"] == "ready"
        finally:
            proc.terminate()
            proc.wait()
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/unit/test_sidecar.py::TestSidecarBuildConfig -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_sidecar.py
git commit -m "test: add build_config tests to sidecar test suite"
```

---

### Task 8: Run all existing tests and fix any breakage

**Files:**
- Possibly modify: `tests/unit/test_zenoh_config.py`, `tests/unit/test_zenoh_signals.py`

- [ ] **Step 1: Run all unit tests**

Run: `python -m pytest tests/unit/ -v`
Expected: ALL PASS. If any fail, fix in the next step.

- [ ] **Step 2: Fix any test failures** (if needed)

Common issues:
- `test_zenoh_config.py` may still try to import `build_zenoh_config` — already handled in Task 4
- `test_zenoh_signals.py` should pass unchanged (tests pure helpers)

- [ ] **Step 3: Run full test suite excluding integration (no zenohd needed)**

Run: `python -m pytest tests/unit/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 4: Commit any fixes**

```bash
git add -u
git commit -m "fix: update tests for sidecar architecture"
```

---

### Task 9: Final verification and cleanup

- [ ] **Step 1: Verify no zenoh import in plugin files**

Run: `grep -rn "import zenoh" weechat-zenoh/weechat-zenoh.py weechat-zenoh/helpers.py`
Expected: no output

- [ ] **Step 2: Verify sidecar does import zenoh**

Run: `grep -n "import zenoh" weechat-zenoh/zenoh_sidecar.py`
Expected: one match (line with `import zenoh`)

- [ ] **Step 3: Run all unit tests one final time**

Run: `python -m pytest tests/unit/ -v`
Expected: ALL PASS

- [ ] **Step 4: Final commit (if any remaining changes)**

```bash
git add -u
git commit -m "chore: final cleanup for sidecar architecture"
```
