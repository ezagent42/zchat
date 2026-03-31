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
    assert mgr.scoped("alice-helper") == "alice-helper"


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


def test_agent_state_persistence(tmp_path):
    state_file = str(tmp_path / "agents.json")
    mgr = _make_manager(state_file=state_file)
    mgr._agents["alice-helper"] = {
        "type": "claude",
        "workspace": "/tmp/x", "window_name": "alice-helper", "status": "running",
        "created_at": 0, "channels": ["#general"],
    }
    mgr._save_state()
    mgr2 = _make_manager(state_file=state_file)
    assert "alice-helper" in mgr2._agents
    assert mgr2._agents["alice-helper"]["window_name"] == "alice-helper"
