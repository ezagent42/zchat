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
    pane_id = state["irc"]["weechat_pane_id"]
    yield pane_id
    wc_agent("irc", "stop")
