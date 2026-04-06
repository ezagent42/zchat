import os
import tomllib

from zchat.cli.project import (
    create_project_config, list_projects, get_default_project,
    set_default_project, resolve_project, load_project_config,
    remove_project, set_config_value,
)


def test_create_project_config(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("test-proj", server="local", nick="alice",
                          channels="#general")
    cfg_path = tmp_path / "projects" / "test-proj" / "config.toml"
    assert cfg_path.exists()
    with open(cfg_path, "rb") as f:
        cfg = tomllib.load(f)
    assert cfg["server"] == "local"
    assert cfg["username"] == "alice"
    assert cfg["default_channels"] == ["#general"]
    assert cfg["zellij"]["session"] == "zchat-test-proj"


def test_create_project_no_tmuxp_yaml(tmp_path, monkeypatch):
    """New config should NOT generate tmuxp.yaml or bootstrap.sh."""
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("test-no-tmux", server="local", nick="",
                          channels="#general")
    pdir = tmp_path / "projects" / "test-no-tmux"
    assert not (pdir / "tmuxp.yaml").exists()
    assert not (pdir / "bootstrap.sh").exists()


def test_create_project_default_runner(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("dr", nick="", channels="#general")
    cfg = load_project_config("dr")
    assert cfg["default_runner"] == "claude-channel"


def test_create_project_custom_runner(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("cr", nick="", channels="#general",
                          default_runner="codex")
    cfg = load_project_config("cr")
    assert cfg["default_runner"] == "codex"


def test_create_project_zellij_session(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("ztest", nick="", channels="#general")
    cfg = load_project_config("ztest")
    assert cfg["zellij"]["session"] == "zchat-ztest"


def test_create_project_mcp_server_cmd(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("mcp", nick="", channels="#general",
                          mcp_server_cmd=["uv", "run", "zchat-channel"])
    cfg = load_project_config("mcp")
    assert cfg["mcp_server_cmd"] == ["uv", "run", "zchat-channel"]


def test_create_project_with_env_file(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    env_path = "/some/path/env"
    create_project_config("proxy", nick="", channels="#general",
                          env_file=env_path)
    cfg = load_project_config("proxy")
    assert cfg["env_file"] == env_path


def test_list_projects(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    (tmp_path / "projects" / "a").mkdir(parents=True)
    (tmp_path / "projects" / "b").mkdir(parents=True)
    assert set(list_projects()) == {"a", "b"}


def test_default_project(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    assert get_default_project() is None
    set_default_project("my-proj")
    assert get_default_project() == "my-proj"


def test_resolve_project_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    assert resolve_project(explicit="my-proj") == "my-proj"


def test_resolve_project_from_cwd(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    marker = tmp_path / ".zchat"
    marker.write_text("cwd-proj")
    monkeypatch.chdir(tmp_path)
    assert resolve_project() == "cwd-proj"


def test_resolve_project_from_default(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    set_default_project("default-proj")
    assert resolve_project() == "default-proj"


def test_remove_project(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("to-remove", nick="x", channels="#g")
    remove_project("to-remove")
    assert not (tmp_path / "projects" / "to-remove").exists()


def test_load_project_config_new_format(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("cfg-new", server="local", nick="bob",
                          channels="#dev,#general")
    cfg = load_project_config("cfg-new")
    assert cfg["server"] == "local"
    assert cfg["username"] == "bob"
    assert cfg["default_channels"] == ["#dev", "#general"]
    assert "irc" not in cfg


def test_load_project_config_old_format_rejected(tmp_path, monkeypatch):
    """Old [irc]/[tmux] format should be rejected with a clear error."""
    import pytest
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    pdir = tmp_path / "projects" / "old-fmt"
    pdir.mkdir(parents=True)
    (pdir / "config.toml").write_text('''[irc]
server = "10.0.0.1"
port = 6697

[tmux]
session = "zchat-abc12345-old-fmt"
''')
    with pytest.raises(SystemExit, match="old config format"):
        load_project_config("old-fmt")


def test_set_config_value(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("test-set", nick="alice", channels="#general")
    set_config_value("test-set", "default_runner", "codex")
    cfg = load_project_config("test-set")
    assert cfg["default_runner"] == "codex"


def test_load_defaults(tmp_path, monkeypatch):
    """load_project_config fills defaults for missing keys."""
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    import tomli_w
    pdir = tmp_path / "projects" / "minimal"
    pdir.mkdir(parents=True)
    # Write a minimal config
    with open(pdir / "config.toml", "wb") as f:
        tomli_w.dump({"server": "remote"}, f)
    cfg = load_project_config("minimal")
    assert cfg["server"] == "remote"
    assert cfg["default_runner"] == "claude-channel"
    assert cfg["default_channels"] == ["#general"]
    assert cfg["mcp_server_cmd"] == ["zchat-channel"]
    assert "zellij" in cfg
