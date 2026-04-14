"""Unit tests for project CLI commands via subprocess (no ergo/zellij required)."""

from __future__ import annotations

import os
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


def test_project_flow_non_interactive(tmp_path):
    """project create/show/set/use/remove works end-to-end without external services."""
    project_name = "unit-project-flow"
    port = _free_port()

    create = _run_cli(
        tmp_path, "project", "create", project_name,
        "--server", "127.0.0.1", "--port", str(port),
        "--channels", "#general", "--agent-type", "claude", "--proxy", "",
    )
    assert create.returncode == 0, create.stderr or create.stdout

    show = _run_cli(tmp_path, "--project", project_name, "project", "show", project_name)
    assert show.returncode == 0, show.stderr or show.stdout
    assert f"Project: {project_name}" in show.stdout
    assert "127.0.0.1" in show.stdout

    set_user = _run_cli(tmp_path, "--project", project_name, "set", "username", "unit-user")
    assert set_user.returncode == 0, set_user.stderr or set_user.stdout

    show2 = _run_cli(tmp_path, "--project", project_name, "project", "show", project_name)
    assert "unit-user" in show2.stdout

    use = _run_cli(tmp_path, "project", "use", project_name, "--no-attach")
    assert use.returncode == 0, use.stderr or use.stdout
    assert "Skip attaching session." in use.stdout
    assert (tmp_path / "default").read_text().strip() == project_name

    remove = _run_cli(tmp_path, "project", "remove", project_name)
    assert remove.returncode == 0, remove.stderr or remove.stdout
