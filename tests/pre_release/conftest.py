# tests/pre_release/conftest.py
"""Pre-release acceptance test fixtures.

Fixture dependency chain:
    zchat_cmd → cli → project → ergo_server → irc_probe

Run with: uv run pytest tests/pre_release/ -v -m "prerelease and not manual"
"""
import os
import socket
import subprocess
import time

import pytest

from zchat.cli import zellij
from tests.pre_release.reporting import PreReleaseReportCollector
from tests.shared.irc_probe import IrcProbe
from tests.shared.cli_runner import make_cli_runner
from tests.pre_release import PROJECT_NAME

_REPORT_COLLECTOR: PreReleaseReportCollector | None = None


def pytest_addoption(parser):
    """Pre-release report generation options."""
    group = parser.getgroup("pre-release-report")
    group.addoption(
        "--pre-release-report-dir",
        dest="pre_release_report_dir",
        action="store",
        default=None,
        help="Directory for generated pre-release JSON/Markdown reports.",
    )
    group.addoption(
        "--no-pre-release-report",
        dest="no_pre_release_report",
        action="store_true",
        default=False,
        help="Disable automatic pre-release report generation.",
    )


def pytest_configure(config):
    """Initialize report collector for this test session."""
    global _REPORT_COLLECTOR
    _REPORT_COLLECTOR = PreReleaseReportCollector(config)


def pytest_collection_modifyitems(config, items):
    """Auto-add prerelease marker and enforce module-scoped ordering."""
    for item in items:
        if "pre_release" in str(item.fspath):
            item.add_marker(pytest.mark.prerelease)
            if _REPORT_COLLECTOR is not None:
                _REPORT_COLLECTOR.register_item(item)
    # Ensure pytest-order sorts within each module, not globally.
    # Without this, all order(1) tests across files run first, breaking
    # the file-level sequencing (test_00 → test_01 → ... → test_08).
    config.option.order_scope = "module"


def pytest_runtest_logreport(report):
    """Collect per-test outcomes for report generation."""
    if _REPORT_COLLECTOR is not None:
        _REPORT_COLLECTOR.on_report(report)


def pytest_sessionfinish(session, exitstatus):
    """Write pre-release report files at end of session."""
    if _REPORT_COLLECTOR is not None:
        _REPORT_COLLECTOR.finalize(session, exitstatus)


def pytest_terminal_summary(terminalreporter):
    """Show generated report paths in terminal summary."""
    if _REPORT_COLLECTOR is None:
        return
    if _REPORT_COLLECTOR.report_error:
        terminalreporter.section("pre-release report", sep="-", blue=True)
        terminalreporter.write_line("failed to generate report:")
        terminalreporter.write_line(_REPORT_COLLECTOR.report_error)
        return
    if _REPORT_COLLECTOR.generated_paths:
        terminalreporter.section("pre-release report", sep="-", blue=True)
        for path in _REPORT_COLLECTOR.generated_paths:
            terminalreporter.write_line(path)


@pytest.fixture(scope="session")
def zchat_cmd():
    """Resolve zchat command from ZCHAT_CMD env var (default: "zchat")."""
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
def zellij_session():
    """Create headless Zellij session, destroy on teardown."""
    name = f"prerelease-{os.getpid()}"
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
def cli(zchat_cmd, e2e_home, zellij_session):
    """CLI runner closure targeting the pre-release project."""
    env = {
        "ZCHAT_HOME": e2e_home,
    }
    return make_cli_runner(cmd=[zchat_cmd], project=PROJECT_NAME, env=env)


@pytest.fixture(scope="session")
def project(cli, e2e_port, zellij_session):
    """Create the main test project via CLI. Teardown removes it."""
    cli(
        "project", "create", PROJECT_NAME,
        "--server", "127.0.0.1",
        "--port", str(e2e_port),
        "--channels", "#general",
        "--agent-type", "claude",
        "--proxy", "127.0.0.1:7897",
    )
    # Set the zellij session name in config to match our test session
    cli("set", "zellij.session", zellij_session)
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
def weechat_tab(zellij_session):
    """Return the WeeChat Zellij tab name.

    WeeChat is started by test_03_irc via cli("irc", "start"), which creates
    a Zellij tab named "weechat". This fixture returns the known name.
    """
    return "weechat"


@pytest.fixture(scope="session")
def zellij_send(zellij_session):
    """Send keys to a Zellij tab by name."""
    def send(target: str, text: str):
        pane_id = zellij.get_pane_id(zellij_session, target)
        if not pane_id:
            pytest.fail(
                f"Zellij pane not found: session={zellij_session}, tab={target}. "
                "Cannot send command to WeeChat/agent tab."
            )
        zellij.send_command(zellij_session, pane_id, text)
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
def remote_irc_probe():
    """IRC probe connected to remote ergo (TLS+SASL). None if unavailable."""
    import json, socket
    from zchat.cli.auth import get_credentials, get_username

    host = "zchat.inside.h2os.cloud"
    port = 6697

    # Check reachability
    try:
        with socket.create_connection((host, port), timeout=5):
            pass
    except OSError:
        yield None
        return

    # Check OIDC credentials
    creds = get_credentials()
    if not creds:
        yield None
        return

    username = get_username()
    _, token = creds
    probe_nick = f"{username}-probe"
    probe = IrcProbe(host, port, nick=probe_nick, tls=True,
                     sasl_login=probe_nick, sasl_pass=token)
    try:
        probe.connect()
        time.sleep(2)
        probe.join("#general")
        time.sleep(1)
        yield probe
    except Exception:
        yield None
    finally:
        probe.disconnect()
