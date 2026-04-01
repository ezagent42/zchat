# tests/pre_release/conftest.py
"""Pre-release acceptance test fixtures.

Fixture dependency chain:
    zchat_cmd → cli → project → ergo_server → irc_probe

Run with: uv run pytest tests/pre_release/ -v -m "prerelease and not manual"
"""
import os
import socket
import time

import pytest

from tests.shared.irc_probe import IrcProbe
from tests.shared.cli_runner import make_cli_runner
from tests.pre_release import PROJECT_NAME


def pytest_collection_modifyitems(config, items):
    """Auto-add prerelease marker and enforce module-scoped ordering."""
    for item in items:
        if "pre_release" in str(item.fspath):
            item.add_marker(pytest.mark.prerelease)
    # Ensure pytest-order sorts within each module, not globally.
    # Without this, all order(1) tests across files run first, breaking
    # the file-level sequencing (test_00 → test_01 → ... → test_08).
    config.option.order_scope = "module"


@pytest.fixture(scope="session")
def zchat_cmd():
    """Resolve zchat command from ZCHAT_CMD env var (default: "zchat")."""
    import subprocess
    cmd = os.environ.get("ZCHAT_CMD", "zchat")
    result = subprocess.run([cmd, "--version"], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"'{cmd}' not found or not working: {result.stderr}"
    )
    return cmd


@pytest.fixture(scope="session")
def e2e_port():
    """Dynamic port to avoid conflicts with other test sessions."""
    return 16667 + (os.getpid() % 1000)


@pytest.fixture(scope="session")
def e2e_home(tmp_path_factory):
    """Isolated ZCHAT_HOME temp directory."""
    return str(tmp_path_factory.mktemp("zchat-prerelease"))


@pytest.fixture(scope="session")
def tmux_session():
    """Create headless tmux session, destroy on teardown."""
    import libtmux
    srv = libtmux.Server()
    name = f"prerelease-{os.getpid()}"
    session = srv.new_session(session_name=name, attach=False, x=220, y=60)
    yield name
    try:
        session.kill()
    except Exception:
        pass


@pytest.fixture(scope="session")
def cli(zchat_cmd, e2e_home, tmux_session):
    """CLI runner closure targeting the pre-release project."""
    env = {
        "ZCHAT_HOME": e2e_home,
        "ZCHAT_TMUX_SESSION": tmux_session,
    }
    return make_cli_runner(cmd=[zchat_cmd], project=PROJECT_NAME, env=env)


@pytest.fixture(scope="session")
def project(cli, e2e_port, tmux_session):
    """Create the main test project via CLI. Teardown removes it."""
    cli(
        "project", "create", PROJECT_NAME,
        "--server", "127.0.0.1",
        "--port", str(e2e_port),
        "--channels", "#general",
        "--agent-type", "claude",
        "--proxy", "",
    )
    # Set the tmux session name in config to match our test session
    cli("set", "tmux.session", tmux_session)
    # Set up local auth for get_username()
    cli("auth", "login", "--method", "local", "--username", os.environ.get("USER", "test"))
    yield PROJECT_NAME
    try:
        cli("project", "remove", PROJECT_NAME, check=False)
    except Exception:
        pass


@pytest.fixture(scope="session")
def ergo_server(cli, project, e2e_port):
    """Start ergo via CLI, verify port is listening."""
    cli("irc", "daemon", "start")
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", e2e_port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    else:
        raise RuntimeError(f"ergo did not start on port {e2e_port}")
    yield {"host": "127.0.0.1", "port": e2e_port}
    # Safety net: stop ergo if still running
    try:
        cli("irc", "daemon", "stop", check=False)
    except Exception:
        pass


@pytest.fixture(scope="session")
def bob_probe(ergo_server):
    """Second IRC client (bob) for user-to-user tests."""
    probe = IrcProbe(ergo_server["host"], ergo_server["port"], nick="bob")
    probe.connect()
    time.sleep(1)
    probe.join("#general")
    time.sleep(1)
    yield probe
    probe.disconnect()


@pytest.fixture(scope="session")
def weechat_window(tmux_session):
    """Return the WeeChat tmux window name.

    WeeChat is started by test_03_irc via cli("irc", "start"), which creates
    a tmux window named "weechat". This fixture returns the known name.
    """
    return "weechat"


@pytest.fixture(scope="session")
def tmux_send(tmux_session):
    """Send keys to a tmux window by name."""
    from zchat.cli.tmux import get_session, find_window
    def send(target: str, text: str):
        session = get_session(tmux_session)
        window = find_window(session, target)
        if window and window.active_pane:
            window.active_pane.send_keys(text, enter=True)
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
