# tests/e2e/conftest.py

import os
import socket
import shutil
import subprocess
import tempfile
import time
import pytest
from irc_probe import IrcProbe


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring ergo + tmux")


@pytest.fixture(scope="session")
def e2e_port():
    """Unique IRC port for this test session."""
    return 16667 + (os.getpid() % 1000)


@pytest.fixture(scope="session")
def ergo_server(e2e_port, e2e_context):
    """Start ergo via IrcManager.daemon_start() — same code path as production."""
    from zchat.cli.irc_manager import IrcManager

    cfg = {"irc": {"server": "127.0.0.1", "port": e2e_port}}
    state_file = os.path.join(e2e_context["home"], "projects", e2e_context["project"], "state.json")
    mgr = IrcManager(config=cfg, state_file=state_file, tmux_session=e2e_context["tmux_session"])
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
def tmux_session():
    """Create headless tmux session, destroy on teardown."""
    import libtmux
    srv = libtmux.Server()
    name = f"e2e-pytest-{os.getpid()}"
    session = srv.new_session(session_name=name, attach=False, x=220, y=60)
    yield name
    try:
        session.kill()
    except Exception:
        pass  # session may already be killed by zchat shutdown


@pytest.fixture(scope="session")
def e2e_context(e2e_port, tmux_session):
    """Central context dict — created BEFORE ergo so ergo can use it."""
    home = tempfile.mkdtemp(prefix="e2e-zchat-")
    project_dir = os.path.join(home, "projects", "e2e-test")
    os.makedirs(project_dir)
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    channel_server_dir = os.path.join(repo_root, "zchat-channel-server")
    env_file = os.path.join(repo_root, "claude.local.env")
    env_file_val = env_file if os.path.isfile(env_file) else ""
    os.makedirs(os.path.join(project_dir, "agents"), exist_ok=True)
    with open(os.path.join(project_dir, "config.toml"), "w") as f:
        f.write(f'[irc]\nserver = "127.0.0.1"\nport = {e2e_port}\ntls = false\npassword = ""\n\n')
        f.write('[agents]\ndefault_channels = ["#general"]\nusername = "alice"\n')
        f.write(f'default_type = "claude"\n')
        f.write(f'env_file = "{env_file_val}"\n')
        f.write(f'mcp_server_cmd = ["uv", "run", "--project", "{channel_server_dir}", "zchat-channel"]\n\n')
        f.write(f'[tmux]\nsession = "{tmux_session}"\n')
    with open(os.path.join(home, "default"), "w") as f:
        f.write("e2e-test")
    ctx = {
        "home": home,
        "project": "e2e-test",
        "tmux_session": tmux_session,
        "port": e2e_port,
    }
    yield ctx
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture(scope="session")
def zchat_cli(e2e_context):
    """Returns a callable for running zchat CLI commands.

    Passes ZCHAT_HOME and ZCHAT_TMUX_SESSION only to subprocesses —
    never mutates os.environ.
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
        env["ZCHAT_TMUX_SESSION"] = e2e_context["tmux_session"]
        return subprocess.run(cmd, env=env, capture_output=True, text=True)

    return run


@pytest.fixture(scope="session")
def tmux_send(e2e_context):
    """Returns a callable for sending keys to a tmux window (by name) or pane (by ID)."""
    from zchat.cli.tmux import get_session, find_pane, find_window
    def send(target: str, text: str):
        session = get_session(e2e_context["tmux_session"])
        # Try window name first, then pane ID
        window = find_window(session, target)
        if window and window.active_pane:
            window.active_pane.send_keys(text, enter=True)
            return
        pane = find_pane(session, target)
        if pane:
            pane.send_keys(text, enter=True)
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
def weechat_window(ergo_server, e2e_context, tmux_session):
    """Start WeeChat in its own tmux window."""
    from zchat.cli.tmux import get_session

    port = ergo_server["port"]
    weechat_dir = os.path.join(e2e_context["home"], "weechat")
    os.makedirs(weechat_dir, exist_ok=True)

    session = get_session(tmux_session)
    srv_name = f"{e2e_context['project']}-ergo"
    cmd = (
        f"weechat --dir {weechat_dir} -r '/server add {srv_name} 127.0.0.1/{port} -notls -nicks=alice; "
        f"/set irc.server.{srv_name}.autojoin \"#general\"; /connect {srv_name}'"
    )
    window = session.new_window(
        window_name="weechat", window_shell=cmd, attach=False,
    )
    time.sleep(5)  # Wait for WeeChat to connect
    yield window.window_name
    try:
        if window.active_pane:
            window.active_pane.send_keys("/quit", enter=True)
    except Exception:
        pass  # window may already be killed by zchat shutdown
