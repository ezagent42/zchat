"""E2E tests for IRC daemon lifecycle (requires ergo installed)."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _run_cli(home: Path, *args: str) -> subprocess.CompletedProcess:
    cmd = [
        "uv", "run", "--no-sync", "--project", str(REPO_ROOT),
        "python", "-m", "zchat.cli", *args,
    ]
    env = os.environ.copy()
    env["ZCHAT_HOME"] = str(home)
    return subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)


@pytest.mark.e2e
@pytest.mark.skipif(shutil.which("ergo") is None, reason="ergo not installed")
def test_irc_daemon_lifecycle(tmp_path):
    """irc daemon start/status/stop succeeds for a temporary project."""
    project_name = "e2e-irc-daemon"
    port = _free_port()

    create = _run_cli(
        tmp_path, "project", "create", project_name,
        "--server", "127.0.0.1", "--port", str(port),
        "--channels", "#general", "--agent-type", "claude", "--proxy", "",
    )
    assert create.returncode == 0, create.stderr or create.stdout

    login = _run_cli(
        tmp_path, "--project", project_name,
        "auth", "login", "--method", "local", "--username", "e2e-user",
    )
    assert login.returncode == 0, login.stderr or login.stdout

    start = _run_cli(tmp_path, "--project", project_name, "irc", "daemon", "start")
    assert start.returncode == 0, start.stderr or start.stdout

    status_running = _run_cli(tmp_path, "--project", project_name, "irc", "status")
    assert status_running.returncode == 0
    assert "running" in status_running.stdout.lower()

    stop = _run_cli(tmp_path, "--project", project_name, "irc", "daemon", "stop")
    assert stop.returncode == 0, stop.stderr or stop.stdout

    status_stopped = _run_cli(tmp_path, "--project", project_name, "irc", "status")
    assert status_stopped.returncode == 0
    assert "stopped" in status_stopped.stdout.lower() or "not running" in status_stopped.stdout.lower()
