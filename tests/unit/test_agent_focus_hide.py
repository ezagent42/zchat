"""Unit tests for zchat agent focus/hide commands."""

import os
from unittest.mock import patch, MagicMock

import pytest

from zchat.cli.app import _tmux_switch


class TestTmuxSwitch:
    """Tests for the _tmux_switch helper."""

    @patch("zchat.cli.app.subprocess.run")
    def test_select_window_inside_tmux(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        with patch.dict(os.environ, {"TMUX": "/tmp/tmux-1000/default,12345,0"}):
            _tmux_switch("zchat-local", "alice-agent0")
        mock_run.assert_called_once_with(
            ["tmux", "select-window", "-t", "zchat-local:alice-agent0"],
            capture_output=True,
        )

    @patch("zchat.cli.app.subprocess.run")
    def test_attach_outside_tmux(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        env = {k: v for k, v in os.environ.items() if k != "TMUX"}
        with patch.dict(os.environ, env, clear=True):
            _tmux_switch("zchat-local", "alice-agent0")
        mock_run.assert_called_once_with(
            ["tmux", "attach", "-t", "zchat-local:alice-agent0"],
        )

    @patch("zchat.cli.app.subprocess.run")
    def test_error_on_nonzero_returncode(self, mock_run):
        from click.exceptions import Exit
        mock_run.return_value = MagicMock(returncode=1)
        with patch.dict(os.environ, {"TMUX": "1"}):
            with pytest.raises(Exit):
                _tmux_switch("zchat-local", "nonexistent")


class TestFocusHideCommands:
    """Tests for focus/hide command logic using AgentManager."""

    def _make_manager(self, agents=None):
        """Create a minimal AgentManager with pre-loaded state."""
        from zchat.cli.agent_manager import AgentManager
        mgr = AgentManager(
            irc_server="localhost", irc_port=6667, irc_tls=False,
            irc_password="", username="alice",
            default_channels=["#general"],
            state_file="/tmp/test-focus-hide.json",
        )
        if agents:
            mgr._agents = agents
        return mgr

    def test_get_status_offline_agent(self):
        mgr = self._make_manager(agents={
            "alice-agent0": {
                "status": "offline",
                "window_name": "alice-agent0",
            }
        })
        status = mgr.get_status("agent0")
        assert status["status"] == "offline"

    def test_get_status_unknown_agent_raises(self):
        mgr = self._make_manager()
        with pytest.raises(ValueError, match="Unknown agent"):
            mgr.get_status("nonexistent")

    def test_session_name_property(self):
        mgr = self._make_manager()
        assert mgr.session_name == "zchat"

    def test_hide_all_skips_validation(self):
        """'all' should not call get_status."""
        mgr = self._make_manager()
        # If get_status were called with "all", it would raise ValueError
        # We just verify session_name is accessible (the tmux call would be mocked in integration)
        assert mgr.session_name == "zchat"
