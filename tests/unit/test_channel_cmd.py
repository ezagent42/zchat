"""单元测试：zchat channel create/list + zchat agent join 命令（V4: routing.toml）。"""
from __future__ import annotations

import json
import os

import pytest
from typer.testing import CliRunner

from zchat.cli.app import app
from zchat.cli.project import (
    create_project_config,
    normalize_channel_name,
)
from zchat.cli import paths as zchat_paths
from zchat.cli.routing import (
    add_channel as routing_add_channel,
    list_channels as routing_list_channels,
    channel_exists as routing_channel_exists,
    load_routing,
    routing_path,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixture: 隔离 ZCHAT_HOME
# ---------------------------------------------------------------------------

@pytest.fixture()
def project(tmp_path, monkeypatch):
    """Create a temporary project and set it as default."""
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
    create_project_config("testproj", server="local", nick="alice", channels="#general")
    # 写 default 文件，让 resolve_project() 自动选中
    (tmp_path / "default").write_text("testproj")
    return tmp_path


# ---------------------------------------------------------------------------
# normalize_channel_name 工具函数
# ---------------------------------------------------------------------------

def test_normalize_channel_name_with_hash():
    assert normalize_channel_name("#foo") == "#foo"


def test_normalize_channel_name_without_hash():
    assert normalize_channel_name("foo") == "#foo"


def test_normalize_channel_name_preserves_hash():
    assert normalize_channel_name("#customer-a") == "#customer-a"


# ---------------------------------------------------------------------------
# routing.py 直接调用：add_channel / list_channels / channel_exists
# ---------------------------------------------------------------------------

def test_routing_add_channel_writes_file(tmp_path):
    routing_add_channel(tmp_path, "#support")
    data = load_routing(tmp_path)
    assert "#support" in data["channels"]


def test_routing_add_channel_with_feishu(tmp_path):
    routing_add_channel(tmp_path, "#ops", feishu_chat_id="oc_xxx", squad_chat_id="oc_squad")
    data = load_routing(tmp_path)
    assert data["channels"]["#ops"]["feishu_chat_id"] == "oc_xxx"
    assert data["channels"]["#ops"]["squad_chat_id"] == "oc_squad"


def test_routing_add_channel_with_default_agents(tmp_path):
    routing_add_channel(tmp_path, "#ops", default_agents=["fast-agent", "deep-agent"])
    data = load_routing(tmp_path)
    assert data["channels"]["#ops"]["default_agents"] == ["fast-agent", "deep-agent"]


def test_routing_add_channel_duplicate_raises(tmp_path):
    routing_add_channel(tmp_path, "#support")
    with pytest.raises(ValueError, match="already exists"):
        routing_add_channel(tmp_path, "#support")


def test_routing_list_channels_empty(tmp_path):
    result = routing_list_channels(tmp_path)
    assert result == []


def test_routing_list_channels_returns_all(tmp_path):
    routing_add_channel(tmp_path, "#alpha", feishu_chat_id="oc_a")
    routing_add_channel(tmp_path, "#beta")
    channels = routing_list_channels(tmp_path)
    ids = [c["channel_id"] for c in channels]
    assert "#alpha" in ids
    assert "#beta" in ids


def test_routing_channel_exists_true(tmp_path):
    routing_add_channel(tmp_path, "#foo")
    assert routing_channel_exists(tmp_path, "#foo") is True


def test_routing_channel_exists_false(tmp_path):
    assert routing_channel_exists(tmp_path, "#nonexistent") is False


def test_routing_roundtrip(tmp_path):
    """add_channel + join_agent → save → reload → 结构一致。"""
    from zchat.cli.routing import join_agent as routing_join_agent
    routing_add_channel(tmp_path, "#ch-1", feishu_chat_id="oc_xxx")
    routing_join_agent(tmp_path, "#ch-1", "fast-agent", "alice-fast-001")
    data = load_routing(tmp_path)
    assert data["channels"]["#ch-1"]["feishu_chat_id"] == "oc_xxx"
    assert data["channels"]["#ch-1"]["agents"]["fast-agent"] == "alice-fast-001"


# ---------------------------------------------------------------------------
# project create → routing.toml 初始化
# ---------------------------------------------------------------------------

def test_project_create_creates_empty_routing_toml(project, monkeypatch):
    """project create 后应存在空的 routing.toml。"""
    monkeypatch.setenv("ZCHAT_HOME", str(project))
    rpath = project / "projects" / "testproj" / "routing.toml"
    assert rpath.exists(), "routing.toml should be created by project create"
    data = load_routing(rpath.parent)
    assert data["channels"] == {}
    assert data["operators"] == {}


def test_project_create_config_has_no_channels_section(project):
    """config.toml 中不应有 [channels] 段。"""
    import tomllib
    config_path = project / "projects" / "testproj" / "config.toml"
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)
    assert "channels" not in cfg, "config.toml should NOT contain [channels] section"


# ---------------------------------------------------------------------------
# CLI: channel create → routing.toml（不写 config.toml）
# ---------------------------------------------------------------------------

def test_channel_create_writes_routing_not_config(project):
    """channel create 写 routing.toml，不写 config.toml [channels]。"""
    import tomllib
    result = runner.invoke(app, ["channel", "create", "#ops"])
    assert result.exit_code == 0, result.output

    # routing.toml 有数据
    pdir = project / "projects" / "testproj"
    data = load_routing(pdir)
    assert "#ops" in data["channels"]

    # config.toml 无 [channels]
    config_path = pdir / "config.toml"
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)
    assert "channels" not in cfg


def test_channel_create_normalizes_hash_prefix(project):
    """传 'foo'（无 #）→ 存 '#foo'。"""
    result = runner.invoke(app, ["channel", "create", "foo"])
    assert result.exit_code == 0, result.output
    pdir = project / "projects" / "testproj"
    data = load_routing(pdir)
    assert "#foo" in data["channels"]


def test_channel_create_with_feishu_chat(project):
    result = runner.invoke(app, ["channel", "create", "#support", "--feishu-chat", "oc_abc123"])
    assert result.exit_code == 0, result.output
    pdir = project / "projects" / "testproj"
    data = load_routing(pdir)
    assert data["channels"]["#support"]["feishu_chat_id"] == "oc_abc123"


def test_channel_create_with_default_agents(project):
    result = runner.invoke(
        app,
        ["channel", "create", "#team", "--default-agents", "fast-agent,deep-agent"],
    )
    assert result.exit_code == 0, result.output
    pdir = project / "projects" / "testproj"
    data = load_routing(pdir)
    assert data["channels"]["#team"]["default_agents"] == ["fast-agent", "deep-agent"]


def test_channel_create_duplicate_fails(project):
    runner.invoke(app, ["channel", "create", "#ops"])  # 第一次
    result = runner.invoke(app, ["channel", "create", "#ops"])  # 重复
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_channel_create_no_project_fails(tmp_path, monkeypatch):
    """没有 project 时应报错退出。"""
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
    result = runner.invoke(app, ["channel", "create", "#ops"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# CLI: channel list → reads from routing.toml
# ---------------------------------------------------------------------------

def test_channel_list_empty(project):
    result = runner.invoke(app, ["channel", "list"])
    assert result.exit_code == 0
    assert "No channels" in result.output


def test_channel_list_formats(project):
    pdir = project / "projects" / "testproj"
    routing_add_channel(pdir, "#alpha", feishu_chat_id="oc_alpha", default_agents=["fast-agent"])
    routing_add_channel(pdir, "#beta")
    result = runner.invoke(app, ["channel", "list"])
    assert result.exit_code == 0
    assert "#alpha" in result.output
    assert "#beta" in result.output


def test_channel_list_no_project_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
    result = runner.invoke(app, ["channel", "list"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# CLI: agent join → updates state.json AND routing.toml
# ---------------------------------------------------------------------------

def _write_agent_state(projects_dir: str, state: dict):
    """Helper: write state.json to project state file path."""
    state_path = os.path.join(projects_dir, "testproj", "state.json")
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w") as f:
        json.dump(state, f)


def _read_agent_state(projects_dir: str) -> dict:
    state_path = os.path.join(projects_dir, "testproj", "state.json")
    with open(state_path) as f:
        return json.load(f)


@pytest.fixture()
def project_with_channel(project):
    """project fixture + 预注册 #support channel 到 routing.toml + 一个离线 agent。"""
    pdir = project / "projects" / "testproj"
    routing_add_channel(pdir, "#support")
    state = {
        "agents": {
            "alice-helper": {
                "type": "claude",
                "status": "offline",
                "channels": ["#general"],
                "workspace": "/tmp/ws",
                "created_at": 0,
            }
        }
    }
    _write_agent_state(str(project / "projects"), state)
    return project


def test_agent_join_adds_channel_to_state(project_with_channel, monkeypatch):
    monkeypatch.setenv("ZCHAT_HOME", str(project_with_channel))
    monkeypatch.setattr("zchat.cli.auth.get_username", lambda: "alice")
    result = runner.invoke(app, ["agent", "join", "helper", "#support"])
    assert result.exit_code == 0, result.output
    state = _read_agent_state(str(project_with_channel / "projects"))
    channels = state["agents"]["alice-helper"]["channels"]
    assert "#support" in channels


def test_agent_join_updates_routing(project_with_channel, monkeypatch):
    """agent join 后 routing.toml 中 channel 的 agents 表应有条目。"""
    monkeypatch.setenv("ZCHAT_HOME", str(project_with_channel))
    monkeypatch.setattr("zchat.cli.auth.get_username", lambda: "alice")
    result = runner.invoke(app, ["agent", "join", "helper", "#support"])
    assert result.exit_code == 0, result.output
    pdir = project_with_channel / "projects" / "testproj"
    data = load_routing(pdir)
    agents_map = data["channels"]["#support"]["agents"]
    # role 默认为 short name "helper"，nick 为 scoped "alice-helper"
    assert "helper" in agents_map
    assert agents_map["helper"] == "alice-helper"


def test_agent_join_with_explicit_role(project_with_channel, monkeypatch):
    """--role 参数能指定 routing.toml 中的角色名。"""
    monkeypatch.setenv("ZCHAT_HOME", str(project_with_channel))
    monkeypatch.setattr("zchat.cli.auth.get_username", lambda: "alice")
    result = runner.invoke(app, ["agent", "join", "helper", "#support", "--role", "fast-agent"])
    assert result.exit_code == 0, result.output
    pdir = project_with_channel / "projects" / "testproj"
    data = load_routing(pdir)
    assert data["channels"]["#support"]["agents"].get("fast-agent") == "alice-helper"


def test_agent_join_dedupes(project_with_channel, monkeypatch):
    """重复 join 同一 channel 不应产生重复条目（state 中）。"""
    monkeypatch.setenv("ZCHAT_HOME", str(project_with_channel))
    monkeypatch.setattr("zchat.cli.auth.get_username", lambda: "alice")
    runner.invoke(app, ["agent", "join", "helper", "#support"])
    runner.invoke(app, ["agent", "join", "helper", "#support"])
    state = _read_agent_state(str(project_with_channel / "projects"))
    channels = state["agents"]["alice-helper"]["channels"]
    assert channels.count("#support") == 1


def test_agent_join_rejects_unknown_channel(project_with_channel, monkeypatch):
    """channel 未在 routing.toml 注册时报错退出。"""
    monkeypatch.setenv("ZCHAT_HOME", str(project_with_channel))
    monkeypatch.setattr("zchat.cli.auth.get_username", lambda: "alice")
    result = runner.invoke(app, ["agent", "join", "helper", "#unknown"])
    assert result.exit_code != 0
    assert "not registered" in result.output


def test_agent_join_no_project_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
    result = runner.invoke(app, ["agent", "join", "helper", "#support"])
    assert result.exit_code != 0


def test_agent_join_unknown_agent_fails(project_with_channel, monkeypatch):
    """agent 不在 state 中时报错退出。"""
    monkeypatch.setenv("ZCHAT_HOME", str(project_with_channel))
    monkeypatch.setattr("zchat.cli.auth.get_username", lambda: "alice")
    result = runner.invoke(app, ["agent", "join", "nonexistent", "#support"])
    assert result.exit_code != 0


def test_agent_join_normalizes_channel_name(project_with_channel, monkeypatch):
    """传入不带 # 的 channel 名称应自动加 #。"""
    monkeypatch.setenv("ZCHAT_HOME", str(project_with_channel))
    monkeypatch.setattr("zchat.cli.auth.get_username", lambda: "alice")
    result = runner.invoke(app, ["agent", "join", "helper", "support"])  # 不带 #
    assert result.exit_code == 0, result.output
    state = _read_agent_state(str(project_with_channel / "projects"))
    channels = state["agents"]["alice-helper"]["channels"]
    assert "#support" in channels
