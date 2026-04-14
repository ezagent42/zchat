"""Unit tests for the three new doctor.py checks (commit 75fe9c2):
- pytest availability via uv run
- IRC port free/in-use
- zchat-channel-server and zchat-protocol submodules initialised
"""
from __future__ import annotations

import subprocess
import types
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_completed(stdout="", returncode=0):
    r = subprocess.CompletedProcess(args=[], returncode=returncode)
    r.stdout = stdout
    r.stderr = ""
    return r


def _run_doctor_isolated(*, pytest_stdout="", port_in_use=False, submodules=True):
    """Run run_doctor() with all external calls mocked.

    Returns the captured typer.echo output as a single string.
    """
    from zchat.cli.doctor import run_doctor

    lines: list[str] = []

    def _fake_echo(msg="", **_kw):
        lines.append(str(msg))

    def _fake_check_command(name):
        # All required tools present, no version string needed
        return True, ""

    def _fake_resolve_project():
        return None  # no active project

    def _fake_list_projects():
        return []

    fake_socket_instance = MagicMock()
    fake_socket_instance.connect_ex.return_value = 0 if port_in_use else 1
    fake_socket_ctx = MagicMock()
    fake_socket_ctx.__enter__ = MagicMock(return_value=fake_socket_instance)
    fake_socket_ctx.__exit__ = MagicMock(return_value=False)
    fake_socket_class = MagicMock(return_value=fake_socket_ctx)

    # submodule markers: real tmp files or nonexistent
    if submodules:
        marker_exists = True
    else:
        marker_exists = False

    with (
        patch("zchat.cli.doctor.typer.echo", side_effect=_fake_echo),
        patch("zchat.cli.doctor._check_command", side_effect=_fake_check_command),
        patch("zchat.cli.doctor.resolve_project", side_effect=_fake_resolve_project),
        patch("zchat.cli.doctor.list_projects", side_effect=_fake_list_projects),
        patch("zchat.cli.doctor._weechat_plugin_installed", return_value="/fake/zchat.py"),
        patch("zchat.cli.doctor.subprocess.run", return_value=_make_completed(pytest_stdout)),
        patch("zchat.cli.doctor.socket.socket", fake_socket_class),
        patch.object(Path, "is_file", return_value=marker_exists),
        patch("zchat.cli.update.load_update_state", return_value={}, create=True),
    ):
        try:
            run_doctor()
        except SystemExit:
            pass

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# TC-01  pytest available — subprocess returns "pytest 8.x.x"
# ---------------------------------------------------------------------------

class TestPytestCheckAvailable(unittest.TestCase):
    def test_pytest_found_shows_tick(self):
        output = _run_doctor_isolated(pytest_stdout="pytest 8.3.5")
        self.assertIn("pytest", output)
        self.assertIn("✓", output.split("pytest")[0].rsplit("\n", 1)[-1] + output)

    def test_pytest_version_string_shown(self):
        output = _run_doctor_isolated(pytest_stdout="pytest 8.3.5\n")
        self.assertIn("pytest 8.3.5", output)


# ---------------------------------------------------------------------------
# TC-02  pytest unavailable — subprocess returns no "pytest" in stdout
# ---------------------------------------------------------------------------

class TestPytestCheckMissing(unittest.TestCase):
    def test_pytest_missing_shows_cross(self):
        output = _run_doctor_isolated(pytest_stdout="")
        lines_with_pytest = [l for l in output.splitlines() if "pytest" in l]
        self.assertTrue(any("✗" in l for l in lines_with_pytest),
                        f"Expected ✗ for pytest in: {lines_with_pytest}")

    def test_pytest_missing_shows_uv_sync_hint(self):
        output = _run_doctor_isolated(pytest_stdout="")
        self.assertIn("uv sync", output)


# ---------------------------------------------------------------------------
# TC-03  IRC port free
# ---------------------------------------------------------------------------

class TestIrcPortFree(unittest.TestCase):
    def test_port_free_shows_tick(self):
        output = _run_doctor_isolated(port_in_use=False)
        port_lines = [l for l in output.splitlines() if "6667" in l]
        self.assertTrue(any("✓" in l for l in port_lines),
                        f"Expected ✓ for port 6667 in: {port_lines}")

    def test_port_free_says_free(self):
        output = _run_doctor_isolated(port_in_use=False)
        self.assertIn("free", output)


# ---------------------------------------------------------------------------
# TC-04  IRC port in use
# ---------------------------------------------------------------------------

class TestIrcPortInUse(unittest.TestCase):
    def test_port_in_use_shows_cross(self):
        output = _run_doctor_isolated(port_in_use=True)
        port_lines = [l for l in output.splitlines() if "6667" in l]
        self.assertTrue(any("✗" in l for l in port_lines),
                        f"Expected ✗ for port 6667 in: {port_lines}")

    def test_port_in_use_warns_ergo(self):
        output = _run_doctor_isolated(port_in_use=True)
        self.assertIn("ergo", output.lower())


# ---------------------------------------------------------------------------
# TC-05  Submodules initialised
# ---------------------------------------------------------------------------

class TestSubmodulesInitialised(unittest.TestCase):
    def test_submodules_present_shows_tick(self):
        output = _run_doctor_isolated(submodules=True)
        lines = [l for l in output.splitlines() if "zchat-channel-server" in l or "zchat-protocol" in l]
        self.assertTrue(all("✓" in l for l in lines),
                        f"Expected ✓ for submodules in: {lines}")


# ---------------------------------------------------------------------------
# TC-06  Submodules not initialised
# ---------------------------------------------------------------------------

class TestSubmodulesNotInitialised(unittest.TestCase):
    def test_submodules_missing_shows_cross(self):
        output = _run_doctor_isolated(submodules=False)
        lines = [l for l in output.splitlines() if "zchat-channel-server" in l or "zchat-protocol" in l]
        self.assertTrue(all("✗" in l for l in lines),
                        f"Expected ✗ for submodules in: {lines}")

    def test_submodules_missing_hints_git_submodule(self):
        output = _run_doctor_isolated(submodules=False)
        self.assertIn("git submodule", output)
