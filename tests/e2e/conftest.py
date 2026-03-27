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
    import sys
    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.join(project_dir, "wc-agent"))
    sys.path.insert(0, project_dir)
    from wc_agent.irc_manager import IrcManager

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
    name = f"e2e-pytest-{os.getpid()}"
    subprocess.run(["tmux", "new-session", "-d", "-s", name, "-x", "220", "-y", "60"])
    yield name
    subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)


@pytest.fixture(scope="session")
def e2e_context(e2e_port, tmux_session):
    """Central context dict — created BEFORE ergo so ergo can use it."""
    home = tempfile.mkdtemp(prefix="e2e-wc-agent-")
    project_dir = os.path.join(home, "projects", "e2e-test")
    os.makedirs(project_dir)
    with open(os.path.join(project_dir, "config.toml"), "w") as f:
        f.write(f'[irc]\nserver = "127.0.0.1"\nport = {e2e_port}\ntls = false\npassword = ""\n\n')
        f.write('[agents]\ndefault_channels = ["#general"]\nusername = "alice"\n')
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
def wc_agent(e2e_context):
    """Returns a callable for running wc-agent CLI commands.

    Passes WC_AGENT_HOME and WC_TMUX_SESSION only to subprocesses —
    never mutates os.environ.
    """
    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    cli_path = os.path.join(project_dir, "wc-agent", "cli.py")

    def run(*args):
        cmd = [
            "uv", "run", "--project", os.path.join(project_dir, "wc-agent"),
            "python", cli_path,
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
def weechat_pane(ergo_server, e2e_context, tmux_session):
    """Start WeeChat directly in tmux (bypass wc-agent for reliability)."""
    port = ergo_server["port"]
    weechat_dir = os.path.join(e2e_context["home"], "weechat")
    os.makedirs(weechat_dir, exist_ok=True)

    result = subprocess.run(
        ["tmux", "split-window", "-h", "-P", "-F", "#{pane_id}",
         "-t", tmux_session,
         f"weechat --dir {weechat_dir} -r '/server add wc-local 127.0.0.1/{port} -notls -nicks=alice; "
         f"/set irc.server.wc-local.autojoin \"#general\"; /connect wc-local'"],
        capture_output=True, text=True,
    )
    pane_id = result.stdout.strip()
    time.sleep(5)  # Wait for WeeChat to connect
    yield pane_id
    # Stop WeeChat
    subprocess.run(["tmux", "send-keys", "-t", pane_id, "/quit", "Enter"], capture_output=True)
