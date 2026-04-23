import os

from zchat.cli.agent_manager import AgentManager


def _make_manager(state_file="/tmp/test-agents.json", env_file="", project_dir=""):
    return AgentManager(
        irc_server="localhost", irc_port=6667, irc_tls=False,
        irc_password="",
        username="alice", default_channels=["#general"],
        env_file=env_file,
        default_type="claude",
        state_file=state_file,
        project_dir=project_dir,
    )


def test_scope_agent_name():
    mgr = _make_manager()
    assert mgr.scoped("helper") == "alice-helper"
    assert mgr.scoped("alice-helper") == "alice-alice-helper"


def test_start_brings_offline_agent_online(tmp_path, monkeypatch):
    """`agent start` 应该用 state.json 里的 channels/type 重新拉起 offline agent。"""
    import pytest
    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    mgr._agents["alice-helper"] = {
        "type": "fast-agent",
        "status": "offline",
        "channels": ["#conv-001"],
        "workspace": str(tmp_path / "agents" / "alice-helper"),
        "created_at": 0,
    }
    seen = {}

    def fake_create(name, channels, agent_type):
        seen["name"] = name
        seen["channels"] = channels
        seen["agent_type"] = agent_type
        return mgr._agents[mgr.scoped(name)]

    monkeypatch.setattr(mgr, "create", fake_create)
    mgr.start("helper")
    assert seen == {
        "name": "helper",
        "channels": ["#conv-001"],
        "agent_type": "fast-agent",
    }


def test_start_rejects_running_agent(tmp_path):
    """start 不应该在 agent 还 running 时拉，应该报错让用户用 restart。"""
    import pytest
    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    mgr._agents["alice-helper"] = {
        "type": "claude",
        "status": "running",
        "channels": ["#general"],
        "workspace": str(tmp_path / "agents" / "alice-helper"),
        "created_at": 0,
    }
    with pytest.raises(ValueError, match="not offline"):
        mgr.start("helper")


def test_start_unknown_agent_raises(tmp_path):
    import pytest
    mgr = _make_manager(state_file=str(tmp_path / "agents.json"))
    with pytest.raises(ValueError, match="Unknown agent"):
        mgr.start("ghost")


def test_create_workspace_exists():
    """create_workspace should create a directory."""
    mgr = _make_manager(state_file="/tmp/test-agents-ws2.json")
    ws = mgr._create_workspace("alice-helper")
    assert os.path.isdir(ws)
    import shutil
    shutil.rmtree(ws)


def test_build_env_context():
    """_build_env_context renders all required placeholders."""
    mgr = _make_manager(project_dir="/tmp/test-project")
    ctx = mgr._build_env_context("alice-bot", "/tmp/ws", ["#general", "#dev"])
    assert ctx["agent_name"] == "alice-bot"
    assert ctx["irc_server"] == "localhost"
    assert ctx["irc_port"] == "6667"
    assert ctx["irc_channels"] == "general,dev"
    assert ctx["irc_tls"] == "false"
    assert ctx["workspace"] == "/tmp/ws"
    assert ctx["zchat_project_dir"] == "/tmp/test-project"


def test_create_workspace_persistent(tmp_path):
    """Workspace should be under project_dir/agents/ when project_dir is set."""
    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    ws = mgr._create_workspace("alice-helper")
    assert ws == str(tmp_path / "agents" / "alice-helper")
    assert os.path.isdir(ws)


def test_cleanup_workspace_only_removes_ready_marker(tmp_path):
    """Stop should delete .ready marker but preserve workspace directory."""
    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    ws = tmp_path / "agents" / "alice-helper"
    ws.mkdir(parents=True)
    ready = tmp_path / "agents" / "alice-helper.ready"
    ready.touch()
    mgr._agents["alice-helper"] = {"workspace": str(ws), "status": "running"}
    mgr._cleanup_workspace("alice-helper")
    assert ws.is_dir(), "workspace should be preserved"
    assert not ready.exists(), "ready marker should be deleted"


def test_wait_for_ready_detects_marker(tmp_path):
    """_wait_for_ready should return True when .ready file appears."""
    import threading
    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    def touch_ready():
        import time; time.sleep(0.5)
        (agents_dir / "alice-helper.ready").touch()

    t = threading.Thread(target=touch_ready, daemon=True)
    t.start()
    result = mgr._wait_for_ready("alice-helper", timeout=5)
    assert result is True


def test_wait_for_ready_timeout(tmp_path):
    """_wait_for_ready should return False on timeout."""
    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    (tmp_path / "agents").mkdir()
    result = mgr._wait_for_ready("alice-helper", timeout=0.5)
    assert result is False


def test_send_succeeds_when_ready(tmp_path):
    """send() delivers text when agent is ready and tab exists."""
    from unittest.mock import patch
    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "alice-helper.ready").touch()
    mgr._agents["alice-helper"] = {
        "type": "claude", "workspace": "/tmp/x",
        "tab_name": "alice-helper", "status": "running",
        "created_at": 0, "channels": ["#general"],
    }
    with patch.object(mgr, "_check_alive", return_value="running"), \
         patch("zchat.cli.zellij.get_pane_id", return_value="terminal_1"), \
         patch("zchat.cli.zellij.send_command") as mock_send:
        mgr.send("helper", "hello")
    mock_send.assert_called_once_with(mgr._session_name, "terminal_1", "hello")


def test_send_raises_when_not_ready(tmp_path):
    """send() raises ValueError when .ready marker does not exist."""
    import pytest as _pytest
    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    (tmp_path / "agents").mkdir()
    mgr._agents["alice-helper"] = {
        "type": "claude", "workspace": "/tmp/x",
        "tab_name": "alice-helper", "status": "running",
        "created_at": 0, "channels": ["#general"],
    }
    from unittest.mock import patch
    with patch.object(mgr, "_check_alive", return_value="running"):
        with _pytest.raises(ValueError, match="not ready"):
            mgr.send("helper", "hello")


def test_send_raises_on_missing_window(tmp_path):
    """send() raises ValueError when zellij tab is not found."""
    import pytest as _pytest
    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "alice-helper.ready").touch()
    mgr._agents["alice-helper"] = {
        "type": "claude", "workspace": "/tmp/x",
        "tab_name": "alice-helper", "status": "running",
        "created_at": 0, "channels": ["#general"],
    }
    from unittest.mock import patch
    with patch.object(mgr, "_check_alive", return_value="running"), \
         patch("zchat.cli.zellij.get_pane_id", return_value=None):
        with _pytest.raises(ValueError, match="tab not found"):
            mgr.send("helper", "hello")


def test_agent_state_persistence(tmp_path):
    state_file = str(tmp_path / "agents.json")
    mgr = _make_manager(state_file=state_file)
    mgr._agents["alice-helper"] = {
        "type": "claude",
        "workspace": "/tmp/x", "tab_name": "alice-helper", "status": "running",
        "created_at": 0, "channels": ["#general"],
    }
    mgr._save_state()
    mgr2 = _make_manager(state_file=state_file)
    assert "alice-helper" in mgr2._agents
    assert mgr2._agents["alice-helper"]["tab_name"] == "alice-helper"


def test_find_channel_pkg_dir_via_uv(tmp_path):
    """_find_channel_pkg_dir locates package via uv tool dir."""
    from unittest.mock import patch, MagicMock
    import zchat.cli.agent_manager as am

    pkg_dir = tmp_path / "zchat-channel-server" / "lib" / "python3.11" / "site-packages" / "zchat_channel_server"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "server.py").touch()
    (pkg_dir / ".claude-plugin").mkdir()

    with patch.object(am._sp, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=str(tmp_path) + "\n")
        result = am._find_channel_pkg_dir()
        assert result is not None
        assert "zchat_channel_server" in result


def test_find_channel_pkg_dir_no_uv():
    """Falls back to None when uv is not available and no dev workspace."""
    from unittest.mock import patch, MagicMock
    import zchat.cli.agent_manager as am

    with patch.object(am._sp, "run") as mock_run, \
         patch.object(am, "_distribution", side_effect=Exception("not found")), \
         patch("os.path.isdir", return_value=False), \
         patch("os.path.isfile", return_value=False):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = am._find_channel_pkg_dir()
        assert result is None


# ---------------------------------------------------------------------------
# TC-001..006: Ctrl+C cleanup (test-plan-008 / eval-doc-007)
# These tests MUST FAIL before the fix and PASS after.
# ---------------------------------------------------------------------------

def test_create_calls_force_stop_on_keyboard_interrupt(tmp_path):
    """TC-001: create() calls _force_stop() when KeyboardInterrupt fires in _wait_for_ready."""
    import pytest
    from unittest.mock import patch

    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    (tmp_path / "agents").mkdir()

    with patch("zchat.cli.agent_manager.check_irc_connectivity"), \
         patch.object(mgr, "_spawn_tab", return_value="alice-helper"), \
         patch.object(mgr, "_auto_confirm_startup"), \
         patch.object(mgr, "_wait_for_ready", side_effect=KeyboardInterrupt), \
         patch.object(mgr, "_force_stop") as mock_force_stop, \
         patch.object(mgr, "_cleanup_workspace"):
        with pytest.raises(KeyboardInterrupt):
            mgr.create("helper")

    mock_force_stop.assert_called_once_with("alice-helper")


def test_create_writes_offline_status_on_keyboard_interrupt(tmp_path):
    """TC-002: create() writes status='offline' to state file when interrupted."""
    import json
    import pytest
    from unittest.mock import patch

    state_file = str(tmp_path / "agents.json")
    mgr = _make_manager(state_file=state_file, project_dir=str(tmp_path))
    (tmp_path / "agents").mkdir()

    with patch("zchat.cli.agent_manager.check_irc_connectivity"), \
         patch.object(mgr, "_spawn_tab", return_value="alice-helper"), \
         patch.object(mgr, "_auto_confirm_startup"), \
         patch.object(mgr, "_wait_for_ready", side_effect=KeyboardInterrupt), \
         patch.object(mgr, "_force_stop"), \
         patch.object(mgr, "_cleanup_workspace"):
        with pytest.raises(KeyboardInterrupt):
            mgr.create("helper")

    with open(state_file) as f:
        data = json.load(f)

    agent = data.get("agents", {}).get("alice-helper")
    assert agent is not None, "agent entry should exist in state file after interrupt"
    assert agent["status"] != "starting", (
        f"status must not remain 'starting' after KeyboardInterrupt, got: {agent['status']}"
    )
    assert agent["status"] == "offline", (
        f"expected status='offline' after cleanup, got: {agent['status']}"
    )


def test_create_blocked_when_status_is_starting(tmp_path):
    """TC-003: create() raises ValueError when agent already has status='starting'."""
    import pytest
    from unittest.mock import patch

    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    mgr._agents["alice-helper"] = {
        "type": "claude", "workspace": "/tmp/x",
        "tab_name": "alice-helper", "status": "starting",
        "created_at": 0, "channels": ["#general"],
    }

    with patch("zchat.cli.agent_manager.check_irc_connectivity"), \
         patch.object(mgr, "_spawn_tab") as mock_spawn:
        with pytest.raises(ValueError, match="starting|already exists"):
            mgr.create("helper")

    mock_spawn.assert_not_called()


def test_create_cleans_ready_marker_on_keyboard_interrupt(tmp_path):
    """TC-004: create() removes .ready marker when interrupted after Claude Code set it."""
    import pytest
    from unittest.mock import patch

    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    ready_file = agents_dir / "alice-helper.ready"

    def wait_touch_then_interrupt(name, timeout=60):
        ready_file.touch()
        raise KeyboardInterrupt

    with patch("zchat.cli.agent_manager.check_irc_connectivity"), \
         patch.object(mgr, "_spawn_tab", return_value="alice-helper"), \
         patch.object(mgr, "_auto_confirm_startup"), \
         patch.object(mgr, "_wait_for_ready", side_effect=wait_touch_then_interrupt), \
         patch.object(mgr, "_force_stop"):
        with pytest.raises(KeyboardInterrupt):
            mgr.create("helper")

    assert not ready_file.exists(), (
        ".ready marker should be deleted by _cleanup_workspace in finally block"
    )


def test_create_succeeds_on_second_attempt_after_interrupt(tmp_path):
    """TC-005: create() succeeds on second call after first was interrupted and cleaned up."""
    import pytest
    from unittest.mock import patch

    mgr = _make_manager(
        state_file=str(tmp_path / "agents.json"),
        project_dir=str(tmp_path),
    )
    (tmp_path / "agents").mkdir()

    spawn_calls = []

    def spawn_side(name, workspace, agent_type, channels):
        spawn_calls.append(name)
        return name

    wait_calls = []

    def wait_side(name, timeout=60):
        wait_calls.append(name)
        if len(wait_calls) == 1:
            raise KeyboardInterrupt
        return True

    with patch("zchat.cli.agent_manager.check_irc_connectivity"), \
         patch.object(mgr, "_spawn_tab", side_effect=spawn_side), \
         patch.object(mgr, "_auto_confirm_startup"), \
         patch.object(mgr, "_wait_for_ready", side_effect=wait_side), \
         patch.object(mgr, "_force_stop"), \
         patch.object(mgr, "_cleanup_workspace"):
        with pytest.raises(KeyboardInterrupt):
            mgr.create("helper")
        info = mgr.create("helper")

    assert info["status"] == "running", (
        f"second create() should return status='running', got: {info['status']}"
    )
    assert len(spawn_calls) == 2, (
        f"_spawn_tab should be called twice (once per create), got {len(spawn_calls)}"
    )


def test_auto_confirm_thread_exits_when_pane_not_found(tmp_path):
    """TC-006: _auto_confirm_startup thread terminates when pane_id is None (tab was force-stopped)."""
    import threading
    from unittest.mock import patch
    import zchat.cli.agent_manager as am

    mgr = _make_manager(state_file=str(tmp_path / "agents.json"))

    captured_threads = []
    OriginalThread = threading.Thread

    class CapturingThread(OriginalThread):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            captured_threads.append(self)

    with patch.object(am, "threading", wraps=am.threading) as mock_threading:
        mock_threading.Thread = CapturingThread
        with patch("zchat.cli.zellij.get_pane_id", return_value=None), \
             patch("zchat.cli.agent_manager.time") as mock_time:
            mock_time.sleep.return_value = None
            mock_time.time.side_effect = am.time.time
            mgr._auto_confirm_startup("alice-helper", timeout=2)

    assert len(captured_threads) == 1, "exactly one confirm thread should be spawned"
    captured_threads[0].join(timeout=3)
    assert not captured_threads[0].is_alive(), (
        "confirm thread must exit when get_pane_id returns None (tab force-stopped)"
    )
