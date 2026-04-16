"""Tests for zchat.cli.zellij helpers — all subprocess calls are mocked."""
from __future__ import annotations

from unittest.mock import MagicMock, call, mock_open, patch
import json
import subprocess

import pytest

from zchat.cli import zellij


# ---------------------------------------------------------------------------
# session_exists
# ---------------------------------------------------------------------------

@patch("subprocess.run")
def test_session_exists_true(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout="my-session [Created ...]\nother-session [Created ...]\n",
    )
    assert zellij.session_exists("my-session") is True
    mock_run.assert_called_once_with(
        ["zellij", "list-sessions"], capture_output=True, text=True,
    )


@patch("subprocess.run")
def test_session_exists_false(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout="other-session [Created ...]\n",
    )
    assert zellij.session_exists("my-session") is False


@patch("subprocess.run")
def test_session_exists_failure(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="error",
    )
    assert zellij.session_exists("anything") is False


# ---------------------------------------------------------------------------
# ensure_session
# ---------------------------------------------------------------------------

@patch("zchat.cli.zellij._run_global")
@patch("zchat.cli.zellij.session_exists", return_value=False)
def test_ensure_session_creates_background(mock_exists, mock_global):
    result = zellij.ensure_session("ci-runner")
    assert result == "ci-runner"
    mock_global.assert_called_once_with(["attach", "--create-background", "ci-runner"])


@patch("zchat.cli.zellij.time.sleep")
@patch("zchat.cli.zellij.subprocess.Popen")
@patch("zchat.cli.zellij.session_exists", return_value=False)
def test_ensure_session_with_layout(mock_exists, mock_popen, mock_sleep):
    result = zellij.ensure_session("ci-runner", layout="/tmp/layout.kdl")
    assert result == "ci-runner"
    mock_popen.assert_called_once_with(
        ["zellij", "--new-session-with-layout", "/tmp/layout.kdl", "--session", "ci-runner"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    mock_sleep.assert_called_once_with(2)


@patch("zchat.cli.zellij._run_global")
@patch("zchat.cli.zellij._session_exited", return_value=False)
@patch("zchat.cli.zellij.session_exists", return_value=True)
def test_ensure_session_already_exists(mock_exists, mock_exited, mock_global):
    result = zellij.ensure_session("ci-runner")
    assert result == "ci-runner"
    mock_global.assert_not_called()


# ---------------------------------------------------------------------------
# new_tab
# ---------------------------------------------------------------------------

@patch("zchat.cli.zellij._run")
def test_new_tab_with_command(mock_run):
    result = zellij.new_tab("sess", "build", command="cargo build", cwd="/project")
    assert result == "build"
    mock_run.assert_called_once_with(
        ["new-tab", "--name", "build", "--cwd", "/project",
         "--", "bash", "-c", "cargo build"],
        session="sess",
    )


@patch("zchat.cli.zellij._run")
def test_new_tab_minimal(mock_run):
    result = zellij.new_tab("sess", "shell")
    assert result == "shell"
    mock_run.assert_called_once_with(
        ["new-tab", "--name", "shell"],
        session="sess",
    )


# ---------------------------------------------------------------------------
# send_command — write-chars + enter
# ---------------------------------------------------------------------------

@patch("zchat.cli.zellij._run")
def test_send_command_uses_paste_then_enter(mock_run):
    zellij.send_command("sess", "terminal_3", "ls -la")
    assert mock_run.call_count == 2
    mock_run.assert_any_call(
        ["write-chars", "--pane-id", "terminal_3", "--", "ls -la"], session="sess",
    )
    mock_run.assert_any_call(
        ["send-keys", "--pane-id", "terminal_3", "Enter"], session="sess",
    )
    # Verify order: paste before send-keys
    calls = mock_run.call_args_list
    assert calls[0] == call(
        ["write-chars", "--pane-id", "terminal_3", "--", "ls -la"], session="sess",
    )
    assert calls[1] == call(
        ["send-keys", "--pane-id", "terminal_3", "Enter"], session="sess",
    )


# ---------------------------------------------------------------------------
# list_panes — JSON parsing
# ---------------------------------------------------------------------------

@patch("zchat.cli.zellij._run")
def test_list_panes_parses_json(mock_run):
    data = [
        {"id": 1, "tab_name": "editor", "is_plugin": False},
        {"id": 2, "tab_name": "shell", "is_plugin": False},
    ]
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(data),
    )
    result = zellij.list_panes("sess")
    assert result == data


@patch("zchat.cli.zellij._run")
def test_list_panes_returns_empty_on_error(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="",
    )
    assert zellij.list_panes("sess") == []


@patch("zchat.cli.zellij._run")
def test_list_panes_returns_empty_on_bad_json(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="not json",
    )
    assert zellij.list_panes("sess") == []


# ---------------------------------------------------------------------------
# tab_exists
# ---------------------------------------------------------------------------

@patch("zchat.cli.zellij.list_panes")
def test_tab_exists_true(mock_panes):
    mock_panes.return_value = [
        {"tab_name": "editor", "id": 1, "is_plugin": False},
        {"tab_name": "shell", "id": 2, "is_plugin": False},
    ]
    assert zellij.tab_exists("sess", "editor") is True


@patch("zchat.cli.zellij.list_panes")
def test_tab_exists_false(mock_panes):
    mock_panes.return_value = [
        {"tab_name": "shell", "id": 2, "is_plugin": False},
    ]
    assert zellij.tab_exists("sess", "editor") is False


# ---------------------------------------------------------------------------
# get_pane_id
# ---------------------------------------------------------------------------

@patch("zchat.cli.zellij.list_panes")
def test_get_pane_id_extracts_terminal_id(mock_panes):
    mock_panes.return_value = [
        {"tab_name": "editor", "id": 5, "is_plugin": False},
        {"tab_name": "editor", "id": 10, "is_plugin": True},  # plugin pane
        {"tab_name": "shell", "id": 3, "is_plugin": False},
    ]
    assert zellij.get_pane_id("sess", "editor") == "terminal_5"


@patch("zchat.cli.zellij.list_panes")
def test_get_pane_id_returns_none_when_missing(mock_panes):
    mock_panes.return_value = [
        {"tab_name": "shell", "id": 3, "is_plugin": False},
    ]
    assert zellij.get_pane_id("sess", "editor") is None


# ---------------------------------------------------------------------------
# dump_screen — --full flag placement
# ---------------------------------------------------------------------------

@patch("zchat.cli.zellij._run")
def test_dump_screen_without_full(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="screen content")
    content = zellij.dump_screen("sess", "terminal_1")
    assert content == "screen content"
    action_args = mock_run.call_args[0][0]
    assert "--full" not in action_args
    assert action_args[0] == "dump-screen"
    assert "--pane-id" in action_args


@patch("zchat.cli.zellij._run")
def test_dump_screen_with_full_flag(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="full content")
    content = zellij.dump_screen("sess", "terminal_1", full=True)
    assert content == "full content"
    action_args = mock_run.call_args[0][0]
    assert "--full" in action_args
    assert action_args[0] == "dump-screen"


@patch("zchat.cli.zellij._run")
def test_dump_screen_file_not_found(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=1, stdout="")
    content = zellij.dump_screen("sess", "terminal_1")
    assert content == ""


# ---------------------------------------------------------------------------
# close_tab — navigates then closes
# ---------------------------------------------------------------------------

@patch("zchat.cli.zellij._run")
@patch("zchat.cli.zellij.list_panes")
def test_close_tab_uses_tab_id(mock_panes, mock_run):
    mock_panes.return_value = [{"tab_name": "editor", "tab_id": 2, "id": 1, "is_plugin": False}]
    zellij.close_tab("sess", "editor")
    mock_run.assert_called_once_with(["close-tab", "--tab-id", "2"], session="sess")


@patch("zchat.cli.zellij._run")
@patch("zchat.cli.zellij.list_panes")
def test_close_tab_fallback_navigate(mock_panes, mock_run):
    """Falls back to go-to-tab-name + close-tab when tab_id not found."""
    mock_panes.return_value = []
    zellij.close_tab("sess", "editor")
    assert mock_run.call_count == 2
    calls = mock_run.call_args_list
    assert calls[0] == call(["go-to-tab-name", "editor"], session="sess")
    assert calls[1] == call(["close-tab"], session="sess")


# ---------------------------------------------------------------------------
# kill_session
# ---------------------------------------------------------------------------

@patch("zchat.cli.zellij._run_global")
def test_kill_session(mock_global):
    zellij.kill_session("my-session")
    mock_global.assert_called_once_with(["kill-session", "my-session"])
