# E2E Test Migration: Bash → Pytest

**Date**: 2026-03-27
**Scope**: Migrate automated e2e tests from bash scripts to pytest, using `irc` library for verification. Keep manual testing as documentation + setup script.

## Overview

Replace `e2e-test.sh` / `helpers.sh` bash scripts with pytest-based e2e tests that:
- Simulate real user operations (tmux, WeeChat, wc-agent CLI)
- Verify via IRC protocol (IrcProbe class using `irc` library)
- Use pytest fixtures for lifecycle management (ergo, tmux, agents)

Manual testing remains shell-based: `e2e-setup.sh` (environment config) + `docs/e2e-manual-test.md` (step-by-step guide).

## Components

### New files

```
tests/e2e/conftest.py      # pytest fixtures: ergo, tmux, project, probe, weechat, agent
tests/e2e/irc_probe.py     # IrcProbe class: nick check, message capture
tests/e2e/test_e2e.py      # Test cases: full user operation simulation
tests/e2e/e2e-setup.sh     # Manual test: environment config (source)
docs/e2e-manual-test.md    # Manual test: step-by-step guide
```

### Delete

```
tests/e2e/e2e-test.sh       # Replaced by pytest
tests/e2e/e2e-test-manual.sh # Split into e2e-setup.sh + docs
tests/e2e/e2e-cleanup.sh    # Replaced by fixture teardown + setup script cleanup
tests/e2e/helpers.sh        # Migrated to Python
```

### Keep

```
tests/e2e/ergo-test.yaml    # Ergo config template (used by conftest.py)
```

### Delete (continued)

```
tests/e2e/test-config.toml  # Replaced by conftest.py dynamic config generation
```

## IrcProbe Class

```python
# tests/e2e/irc_probe.py
"""IRC probe client for e2e test verification."""

import irc.client
import threading
import time


class IrcProbe:
    """Lightweight IRC client that joins a channel and records messages."""

    def __init__(self, server: str, port: int, nick: str = "e2e-probe"):
        self.server = server
        self.port = port
        self.nick = nick
        self.messages: list[dict] = []  # {"nick": str, "channel": str, "text": str}
        self._lock = threading.Lock()   # Protects self.messages (thread-safe appends)
        self._reactor = irc.client.Reactor()
        self._conn = None
        self._thread = None

    def connect(self):
        """Connect to IRC server and start reactor in background thread."""
        self._conn = self._reactor.server().connect(self.server, self.port, self.nick)
        self._conn.add_global_handler("pubmsg", self._on_pubmsg)
        self._conn.add_global_handler("privmsg", self._on_privmsg)
        self._thread = threading.Thread(target=self._reactor.process_forever, daemon=True)
        self._thread.start()

    def join(self, channel: str):
        """Join a channel to receive messages."""
        self._conn.join(channel)

    def disconnect(self):
        """Disconnect from IRC."""
        if self._conn:
            self._conn.disconnect()

    def nick_exists(self, nick: str, timeout: float = 3.0) -> bool:
        """Check if a nick is online via WHOIS on the persistent connection."""
        result = {"found": False, "done": False}

        def on_whoisuser(conn, event):
            result["found"] = True
            result["done"] = True

        def on_endofwhois(conn, event):
            result["done"] = True

        self._conn.add_global_handler("whoisuser", on_whoisuser)
        self._conn.add_global_handler("endofwhois", on_endofwhois)
        self._conn.whois([nick])
        deadline = time.time() + timeout
        while time.time() < deadline and not result["done"]:
            time.sleep(0.1)
        # Remove handlers to avoid accumulation across calls
        self._conn.remove_global_handler("whoisuser", on_whoisuser)
        self._conn.remove_global_handler("endofwhois", on_endofwhois)
        return result["found"]

    def wait_for_nick(self, nick: str, timeout: int = 5) -> bool:
        """Poll until nick appears on IRC."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.nick_exists(nick):
                return True
            time.sleep(1)
        return False

    def wait_for_nick_gone(self, nick: str, timeout: int = 10) -> bool:
        """Poll until nick disappears from IRC."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.nick_exists(nick):
                return True
            time.sleep(1)
        return False

    def wait_for_message(self, pattern: str, timeout: int = 15) -> dict | None:
        """Wait for a message matching pattern. Returns the message dict or None."""
        import re
        deadline = time.time() + timeout
        with self._lock:
            seen = len(self.messages)
        while time.time() < deadline:
            with self._lock:
                for msg in self.messages[seen:]:
                    if re.search(pattern, msg["text"], re.IGNORECASE):
                        return msg
                seen = len(self.messages)
            time.sleep(0.5)
        return None

    def _on_pubmsg(self, conn, event):
        with self._lock:
            self.messages.append({
                "nick": event.source.nick,
                "channel": event.target,
                "text": event.arguments[0],
            })

    def _on_privmsg(self, conn, event):
        with self._lock:
            self.messages.append({
                "nick": event.source.nick,
                "channel": None,
                "text": event.arguments[0],
            })
```

## Pytest Fixtures

```python
# tests/e2e/conftest.py

import os
import socket
import shutil
import subprocess
import tempfile
import time
import pytest
from irc_probe import IrcProbe


@pytest.fixture(scope="session")
def e2e_port():
    """Unique IRC port for this test session."""
    return 16667 + (os.getpid() % 1000)


@pytest.fixture(scope="session")
def ergo_server(e2e_port):
    """Start ergo on unique port, yield config, stop on teardown."""
    ergo_dir = tempfile.mkdtemp(prefix="e2e-ergo-")
    # Copy languages
    system_langs = os.path.expanduser("~/.local/share/ergo/languages")
    if os.path.isdir(system_langs):
        shutil.copytree(system_langs, os.path.join(ergo_dir, "languages"))
    # Generate config
    result = subprocess.run(["ergo", "defaultconfig"], capture_output=True, text=True)
    config = result.stdout.replace('"127.0.0.1:6667":', f'"127.0.0.1:{e2e_port}":')
    config = "\n".join(l for l in config.split("\n") if "[::1]:6667" not in l)
    # Remove TLS listener
    import re
    config = re.sub(r'":6697":\s*\n.*?min-tls-version:.*?\n', '', config, flags=re.DOTALL)
    conf_path = os.path.join(ergo_dir, "ergo.yaml")
    with open(conf_path, "w") as f:
        f.write(config)
    # Start
    proc = subprocess.Popen(
        ["ergo", "run", "--conf", conf_path],
        cwd=ergo_dir,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Wait for ergo to accept connections (socket check, max 10s)
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", e2e_port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError(f"ergo did not accept connections on port {e2e_port}")
    yield {"host": "127.0.0.1", "port": e2e_port, "proc": proc, "dir": ergo_dir}
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    shutil.rmtree(ergo_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def tmux_session():
    """Create headless tmux session, destroy on teardown."""
    name = f"e2e-pytest-{os.getpid()}"
    subprocess.run(["tmux", "new-session", "-d", "-s", name, "-x", "220", "-y", "60"])
    yield name
    subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)


@pytest.fixture(scope="session")
def e2e_context(ergo_server, tmux_session):
    """Central context dict shared by all e2e fixtures."""
    home = tempfile.mkdtemp(prefix="e2e-wc-agent-")
    project_dir = os.path.join(home, "projects", "e2e-test")
    os.makedirs(project_dir)
    # Write project config
    with open(os.path.join(project_dir, "config.toml"), "w") as f:
        f.write(f'[irc]\nserver = "{ergo_server["host"]}"\n')
        f.write(f'port = {ergo_server["port"]}\ntls = false\npassword = ""\n\n')
        f.write('[agents]\ndefault_channels = ["#general"]\nusername = "alice"\n')
    with open(os.path.join(home, "default"), "w") as f:
        f.write("e2e-test")
    ctx = {
        "home": home,
        "project": "e2e-test",
        "tmux_session": tmux_session,
        "port": ergo_server["port"],
    }
    yield ctx
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture(scope="session")
def wc_agent(e2e_context):
    """Returns a callable for running wc-agent CLI commands.

    Passes WC_AGENT_HOME and WC_TMUX_SESSION only to subprocesses —
    never mutates os.environ.
    """
    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def run(*args):
        cmd = [
            "uv", "run", "--project", os.path.join(project_dir, "wc-agent"),
            "python", "-m", "wc_agent.cli",
            "--project", e2e_context["project"],
            *args,
        ]
        env = os.environ.copy()
        env["WC_AGENT_HOME"] = e2e_context["home"]
        env["WC_TMUX_SESSION"] = e2e_context["tmux_session"]
        return subprocess.run(cmd, env=env, capture_output=True, text=True)

    return run


@pytest.fixture(scope="session")
def tmux_send(e2e_context):
    """Returns a callable for sending keys to a tmux pane."""
    def send(pane_id: str, text: str):
        subprocess.run(
            ["tmux", "send-keys", "-t", pane_id, text, "Enter"],
            capture_output=True,
        )
    return send


@pytest.fixture(scope="session")
def irc_probe(ergo_server):
    """IRC client that joins #general and records messages."""
    probe = IrcProbe(ergo_server["host"], ergo_server["port"])
    probe.connect()
    time.sleep(1)
    probe.join("#general")
    time.sleep(1)
    yield probe
    probe.disconnect()


@pytest.fixture(scope="session")
def weechat_pane(ergo_server, e2e_context, wc_agent):
    """Start WeeChat in tmux via wc-agent irc start. Yields the pane_id from state.json."""
    wc_agent("irc", "start")
    time.sleep(3)
    # Read actual pane ID written by wc-agent into state.json
    state_path = os.path.join(
        e2e_context["home"], "projects", e2e_context["project"], "state.json"
    )
    import json
    with open(state_path) as f:
        state = json.load(f)
    pane_id = state["weechat_pane"]
    yield pane_id
    wc_agent("irc", "stop")
```

### pytest marker registration

Add to `tests/e2e/conftest.py` (or a top-level `conftest.py`):

```python
def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring ergo + tmux")
```

## Test Cases

A single test function with sequential phases eliminates pytest ordering ambiguity
and mirrors the structure of the original bash script.

```python
# tests/e2e/test_e2e.py

import pytest
import time


@pytest.mark.e2e
def test_full_e2e_lifecycle(wc_agent, irc_probe, weechat_pane, tmux_send):
    """Full e2e test — sequential phases matching real user workflow."""

    # Phase 1: WeeChat connected
    assert irc_probe.wait_for_nick("alice", timeout=5), "alice not on IRC after irc start"

    # Phase 2: Create agent0 — joins IRC
    wc_agent("agent", "create", "agent0")
    assert irc_probe.wait_for_nick("alice-agent0", timeout=15), "agent0 not on IRC"

    # Phase 3: agent send — agent replies to channel
    wc_agent("agent", "send", "agent0",
             'Use the reply MCP tool to send "Hello from agent0!" to #general')
    msg = irc_probe.wait_for_message("Hello from agent0", timeout=15)
    assert msg is not None, "agent0 message not received in #general"
    assert msg["nick"] == "alice-agent0"

    # Phase 4: @mention in WeeChat — agent auto-responds
    tmux_send(weechat_pane, "@alice-agent0 what is 2+2?")
    reply = irc_probe.wait_for_message("alice-agent0", timeout=15)
    assert reply is not None, "agent0 did not respond to @mention"

    # Phase 5: Second agent — create, send, verify
    wc_agent("agent", "create", "agent1")
    assert irc_probe.wait_for_nick("alice-agent1", timeout=15), "agent1 not on IRC"
    wc_agent("agent", "send", "agent1",
             'Use the reply MCP tool to send "hello from agent1" to #general')
    msg1 = irc_probe.wait_for_message("agent1", timeout=15)
    assert msg1 is not None, "agent1 message not received"

    # Phase 6: Stop agent1 — leaves IRC
    wc_agent("agent", "stop", "agent1")
    assert irc_probe.wait_for_nick_gone("alice-agent1", timeout=10), "agent1 still on IRC after stop"

    # Phase 7: Shutdown — all agents + WeeChat gone
    wc_agent("shutdown")
    assert irc_probe.wait_for_nick_gone("alice-agent0", timeout=10), "agent0 still on IRC after shutdown"
```

## Manual Testing

### `tests/e2e/e2e-setup.sh`

Same as current `e2e-test-manual.sh` — sets up environment variables, creates project config, starts ergo. Does NOT run any tests.

### `docs/e2e-manual-test.md`

Step-by-step guide with expected results. Recreated after migration (was deleted earlier).

## Run Commands

```bash
# Automated (all e2e tests)
pytest tests/e2e/ -v -m e2e --timeout=300

# Single test (entire lifecycle as one function)
pytest tests/e2e/test_e2e.py::test_full_e2e_lifecycle -v

# Manual
source tests/e2e/e2e-setup.sh
# Follow docs/e2e-manual-test.md
```

## Timeouts

| Check | Timeout |
|-------|---------|
| IRC connection (alice, ergo) | 5s |
| Agent IRC connection | 15s |
| Claude reply (agent send, @mention) | 15s |
| Agent gone after stop | 10s |

## Dependencies

Add to `weechat-channel-server/pyproject.toml` test deps:
```toml
[project.optional-dependencies]
test = ["pytest", "pytest-asyncio", "pytest-timeout"]
```

`irc` library is already a dependency of channel-server.
