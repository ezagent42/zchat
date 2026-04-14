# tests/e2e/conftest.py

import os
import socket
import shutil
import subprocess
import tempfile
import time
import pytest
import tomli_w

from zchat.cli import zellij
from irc_probe import IrcProbe


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring ergo + zellij")


@pytest.fixture(scope="session")
def e2e_port():
    """Unique IRC port for this test session."""
    return 16667 + (os.getpid() % 1000)


@pytest.fixture(scope="session")
def zellij_session():
    """Create headless Zellij session, destroy on teardown."""
    name = f"e2e-pytest-{os.getpid()}"
    # Clean any stale session
    try:
        zellij.kill_session(name)
        time.sleep(1)
    except Exception:
        pass
    subprocess.run(["zellij", "delete-session", name], capture_output=True)
    time.sleep(0.5)

    zellij.ensure_session(name)
    time.sleep(2)
    yield name
    try:
        zellij.kill_session(name)
    except Exception:
        pass


@pytest.fixture(scope="session")
def e2e_context(e2e_port):
    """Central context dict for E2E subprocesses.

    Intentionally does not require a live Zellij binary so non-Zellij E2E
    tests (e.g. pure IRC transport checks) can run independently.
    """
    home = tempfile.mkdtemp(prefix="e2e-zchat-")
    # Write auth.json with username "alice" for get_username()
    import json as _json
    with open(os.path.join(home, "auth.json"), "w") as f:
        _json.dump({"username": "alice"}, f)
    project_dir = os.path.join(home, "projects", "e2e-test")
    os.makedirs(project_dir)
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    channel_server_dir = os.path.join(repo_root, "zchat-channel-server")
    env_file = os.path.join(repo_root, "claude.local.env")
    env_file_val = env_file if os.path.isfile(env_file) else ""
    os.makedirs(os.path.join(project_dir, "agents"), exist_ok=True)

    # Write new-format project config (no [irc]/[tmux] sections)
    project_config = {
        "server": "e2e-local",
        "default_runner": "claude",
        "default_channels": ["#general"],
        "username": "alice",
        "env_file": env_file_val,
        "mcp_server_cmd": ["uv", "run", "--project", channel_server_dir, "zchat-channel"],
        "zellij": {
            "session": f"e2e-pytest-{os.getpid()}",
        },
    }
    with open(os.path.join(project_dir, "config.toml"), "wb") as f:
        tomli_w.dump(project_config, f)

    # Write global config with server entry for the test port
    global_config = {
        "servers": {
            "e2e-local": {
                "host": "127.0.0.1",
                "port": e2e_port,
                "tls": False,
            },
        },
        "update": {
            "channel": "main",
            "auto_upgrade": True,
        },
    }
    with open(os.path.join(home, "config.toml"), "wb") as f:
        tomli_w.dump(global_config, f)

    with open(os.path.join(home, "default"), "w") as f:
        f.write("e2e-test")
    ctx = {
        "home": home,
        "project": "e2e-test",
        "zellij_session": f"e2e-pytest-{os.getpid()}",
        "port": e2e_port,
    }
    yield ctx
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture(scope="session")
def ergo_server(e2e_port, e2e_context):
    """Start ergo via IrcManager.daemon_start() — same code path as production."""
    from zchat.cli.irc_manager import IrcManager

    cfg = {"irc": {"server": "127.0.0.1", "port": e2e_port}}
    state_file = os.path.join(e2e_context["home"], "projects", e2e_context["project"], "state.json")
    mgr = IrcManager(config=cfg, state_file=state_file, zellij_session=e2e_context["zellij_session"])
    mgr.daemon_start()

    # Verify ergo is listening
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", e2e_port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    else:
        raise RuntimeError(f"ergo did not start on port {e2e_port}")

    yield {"host": "127.0.0.1", "port": e2e_port, "mgr": mgr}
    mgr.daemon_stop()


@pytest.fixture(scope="session")
def zchat_cli(e2e_context):
    """Returns a callable for running zchat CLI commands.

    Passes ZCHAT_HOME only to subprocesses — never mutates os.environ.
    """
    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def run(*args):
        cmd = [
            "uv", "run", "--project", project_dir,
            "python", "-m", "zchat.cli",
            "--project", e2e_context["project"],
            *args,
        ]
        env = os.environ.copy()
        env["ZCHAT_HOME"] = e2e_context["home"]
        return subprocess.run(cmd, env=env, capture_output=True, text=True)

    return run


@pytest.fixture(scope="session")
def zellij_send(e2e_context):
    """Returns a callable for sending keys to a Zellij tab by name."""
    def send(target: str, text: str):
        session = e2e_context["zellij_session"]
        pane_id = zellij.get_pane_id(session, target)
        if not pane_id:
            pytest.fail(
                f"Zellij pane not found: session={session}, tab={target}. "
                "Cannot send command."
            )
        zellij.send_command(session, pane_id, text)
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
def weechat_tab(ergo_server, e2e_context, zellij_session):
    """Start WeeChat in its own Zellij tab."""
    port = ergo_server["port"]
    weechat_dir = os.path.join(e2e_context["home"], "weechat")
    os.makedirs(weechat_dir, exist_ok=True)

    srv_name = f"{e2e_context['project']}-ergo"
    cmd = (
        f"weechat --dir {weechat_dir} -r '/server add {srv_name} 127.0.0.1/{port} -notls -nicks=alice; "
        f"/set irc.server.{srv_name}.autojoin \"#general\"; /connect {srv_name}'"
    )
    zellij.new_tab(zellij_session, "weechat", command=cmd)
    time.sleep(5)  # Wait for WeeChat to connect
    yield "weechat"
    try:
        pane_id = zellij.get_pane_id(zellij_session, "weechat")
        if pane_id:
            zellij.send_command(zellij_session, pane_id, "/quit")
    except Exception:
        pass
