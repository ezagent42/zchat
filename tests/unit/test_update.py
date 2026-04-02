"""Tests for zchat.cli.update module."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**overrides):
    """Return a minimal valid state dict, with optional overrides."""
    state = {
        "last_check": "",
        "channel": "main",
        "zchat": {"installed_ref": "", "remote_ref": ""},
        "channel_server": {"installed_ref": "", "remote_ref": ""},
        "update_available": False,
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# 1. load_update_state — missing file returns defaults
# ---------------------------------------------------------------------------

def test_load_update_state_missing_file(tmp_path):
    from zchat.cli.update import load_update_state, _DEFAULT_STATE

    path = str(tmp_path / "update.json")
    state = load_update_state(path=path)

    assert state["last_check"] == ""
    assert state["channel"] == "main"
    assert state["zchat"] == {"installed_ref": "", "remote_ref": ""}
    assert state["channel_server"] == {"installed_ref": "", "remote_ref": ""}
    assert state["update_available"] is False


# ---------------------------------------------------------------------------
# 2. save_update_state + load_update_state roundtrip
# ---------------------------------------------------------------------------

def test_save_load_roundtrip(tmp_path):
    from zchat.cli.update import load_update_state, save_update_state

    path = str(tmp_path / "update.json")
    original = {
        "last_check": "2026-04-01T10:00:00Z",
        "channel": "release",
        "zchat": {"installed_ref": "1.2.3", "remote_ref": "1.3.0"},
        "channel_server": {"installed_ref": "0.9.0", "remote_ref": "0.9.0"},
        "update_available": True,
    }
    save_update_state(original, path=path)
    loaded = load_update_state(path=path)

    assert loaded["channel"] == "release"
    assert loaded["zchat"]["installed_ref"] == "1.2.3"
    assert loaded["zchat"]["remote_ref"] == "1.3.0"
    assert loaded["update_available"] is True


def test_save_creates_parent_dirs(tmp_path):
    from zchat.cli.update import save_update_state

    path = str(tmp_path / "nested" / "dir" / "update.json")
    save_update_state(_make_state(), path=path)
    assert (tmp_path / "nested" / "dir" / "update.json").exists()


# ---------------------------------------------------------------------------
# 3. should_check_today — no previous check → True
# ---------------------------------------------------------------------------

def test_should_check_today_no_previous_check():
    from zchat.cli.update import should_check_today

    state = _make_state(last_check="")
    assert should_check_today(state) is True


# ---------------------------------------------------------------------------
# 4. should_check_today — already checked today → False
# ---------------------------------------------------------------------------

def test_should_check_today_checked_today():
    from zchat.cli.update import should_check_today

    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = _make_state(last_check=today)
    assert should_check_today(state) is False


def test_should_check_today_checked_yesterday():
    from zchat.cli.update import should_check_today

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = _make_state(last_check=yesterday)
    assert should_check_today(state) is True


def test_should_check_today_invalid_date_returns_true():
    from zchat.cli.update import should_check_today

    state = _make_state(last_check="not-a-date")
    assert should_check_today(state) is True


# ---------------------------------------------------------------------------
# 5. _check_remote_git — success (mock subprocess.run)
# ---------------------------------------------------------------------------

def test_check_remote_git_success():
    from zchat.cli.update import _check_remote_git

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "abc1234567890\trefs/heads/main\n"

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        ref = _check_remote_git("https://github.com/example/repo.git", "main")

    assert ref == "abc1234"  # 7 chars
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert "git" in call_args
    assert "ls-remote" in call_args


# ---------------------------------------------------------------------------
# 6. _check_remote_git — timeout (mock TimeoutExpired)
# ---------------------------------------------------------------------------

def test_check_remote_git_timeout():
    from zchat.cli.update import _check_remote_git

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=5)):
        ref = _check_remote_git("https://github.com/example/repo.git", "main")

    assert ref is None


def test_check_remote_git_file_not_found():
    from zchat.cli.update import _check_remote_git

    with patch("subprocess.run", side_effect=FileNotFoundError()):
        ref = _check_remote_git("https://github.com/example/repo.git", "main")

    assert ref is None


def test_check_remote_git_nonzero_returncode():
    from zchat.cli.update import _check_remote_git

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""

    with patch("subprocess.run", return_value=mock_result):
        ref = _check_remote_git("https://github.com/example/repo.git", "main")

    assert ref is None


# ---------------------------------------------------------------------------
# 7. _check_remote_pypi — success (mock urlopen)
# ---------------------------------------------------------------------------

def test_check_remote_pypi_success():
    from zchat.cli.update import _check_remote_pypi

    pypi_response = json.dumps({"info": {"version": "1.5.0"}}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = pypi_response
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        version = _check_remote_pypi("zchat")

    assert version == "1.5.0"


# ---------------------------------------------------------------------------
# 8. _check_remote_pypi — failure (mock exception)
# ---------------------------------------------------------------------------

def test_check_remote_pypi_failure():
    from zchat.cli.update import _check_remote_pypi

    with patch("urllib.request.urlopen", side_effect=Exception("network error")):
        version = _check_remote_pypi("zchat")

    assert version is None


# ---------------------------------------------------------------------------
# 9. _build_install_args — main channel
# ---------------------------------------------------------------------------

def test_build_install_args_main():
    from zchat.cli.update import _build_install_args, _ZCHAT_REPO, _CHANNEL_REPO

    args = _build_install_args("main")
    assert len(args) == 2
    assert f"git+{_ZCHAT_REPO}@main" in args[0]
    assert f"git+{_CHANNEL_REPO}@main" in args[1]


def test_build_install_args_dev():
    from zchat.cli.update import _build_install_args, _ZCHAT_REPO, _CHANNEL_REPO

    args = _build_install_args("dev")
    assert len(args) == 2
    assert "@dev" in args[0]
    assert "@dev" in args[1]


# ---------------------------------------------------------------------------
# 10. _build_install_args — release channel
# ---------------------------------------------------------------------------

def test_build_install_args_release():
    from zchat.cli.update import _build_install_args

    args = _build_install_args("release")
    assert args == ["zchat", "zchat-channel-server"]


# ---------------------------------------------------------------------------
# 11. run_upgrade — success (mock subprocess.run)
# ---------------------------------------------------------------------------

def test_run_upgrade_success(tmp_path):
    from zchat.cli.update import run_upgrade

    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        ok = run_upgrade("main")

    assert ok is True
    assert mock_run.call_count == 2  # one per package
    # verify uv tool install --force was called
    first_call = mock_run.call_args_list[0][0][0]
    assert first_call[:4] == ["uv", "tool", "install", "--force"]


def test_run_upgrade_first_package_fails(tmp_path):
    from zchat.cli.update import run_upgrade

    mock_fail = MagicMock()
    mock_fail.returncode = 1

    # State file won't exist — load_update_state should return defaults
    with patch("subprocess.run", return_value=mock_fail):
        ok = run_upgrade("release")

    assert ok is False


def test_run_upgrade_second_package_fails(tmp_path):
    from zchat.cli.update import run_upgrade

    success = MagicMock(returncode=0)
    failure = MagicMock(returncode=1)

    call_count = {"n": 0}

    def side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return success
        return failure

    with patch("subprocess.run", side_effect=side_effect):
        ok = run_upgrade("release")

    assert ok is False


# ---------------------------------------------------------------------------
# 12. check_for_updates — fresh install: installed_ref set to remote_ref, no false "update available"
# ---------------------------------------------------------------------------

def test_check_for_updates_fresh_install_no_false_update():
    from zchat.cli.update import check_for_updates

    state = _make_state(channel="main")

    with patch("zchat.cli.update._check_remote_git", return_value="abc1234"):
        state = check_for_updates(state)

    # Fresh install: installed_ref should be set to remote_ref
    assert state["zchat"]["installed_ref"] == "abc1234"
    assert state["channel_server"]["installed_ref"] == "abc1234"
    # No update should be flagged
    assert state["update_available"] is False


def test_check_for_updates_update_available():
    from zchat.cli.update import check_for_updates

    state = _make_state(channel="main")
    state["zchat"]["installed_ref"] = "old1234"
    state["zchat"]["remote_ref"] = "old1234"
    state["channel_server"]["installed_ref"] = "oldc123"
    state["channel_server"]["remote_ref"] = "oldc123"

    with patch("zchat.cli.update._check_remote_git", return_value="new5678"):
        state = check_for_updates(state)

    assert state["update_available"] is True
    assert state["zchat"]["remote_ref"] == "new5678"


def test_check_for_updates_release_channel():
    from zchat.cli.update import check_for_updates

    state = _make_state(channel="release")

    with patch("zchat.cli.update._check_remote_pypi", return_value="2.0.0"):
        state = check_for_updates(state)

    assert state["zchat"]["remote_ref"] == "2.0.0"
    assert state["channel_server"]["remote_ref"] == "2.0.0"
    # Fresh install: no false update
    assert state["update_available"] is False


def test_check_for_updates_sets_last_check_timestamp():
    from zchat.cli.update import check_for_updates

    state = _make_state(channel="main")

    with patch("zchat.cli.update._check_remote_git", return_value=None):
        state = check_for_updates(state)

    assert state["last_check"] != ""
    # Verify it's a parseable UTC timestamp
    datetime.strptime(state["last_check"], "%Y-%m-%dT%H:%M:%SZ")
