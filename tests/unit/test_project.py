import os

from zchat.cli.project import (
    create_project_config, list_projects, get_default_project,
    set_default_project, resolve_project, load_project_config,
    remove_project, set_config_value,
)

def test_create_project_config(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("test-proj", server="10.0.0.1", port=6667,
                          tls=False, password="", nick="alice", channels="#general")
    cfg_path = tmp_path / "projects" / "test-proj" / "config.toml"
    assert cfg_path.exists()
    import tomllib
    with open(cfg_path, "rb") as f:
        cfg = tomllib.load(f)
    assert cfg["irc"]["server"] == "10.0.0.1"
    assert cfg["agents"]["username"] == "alice"

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
    create_project_config("to-remove", server="localhost", port=6667,
                          tls=False, password="", nick="x", channels="#g")
    remove_project("to-remove")
    assert not (tmp_path / "projects" / "to-remove").exists()

def test_load_project_config(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("cfg-test", server="10.0.0.1", port=6697,
                          tls=True, password="pw", nick="bob", channels="#dev,#general")
    cfg = load_project_config("cfg-test")
    assert cfg["irc"]["server"] == "10.0.0.1"
    assert cfg["irc"]["tls"] is True
    assert cfg["agents"]["username"] == "bob"
    assert "auth" not in cfg


def test_config_has_default_type(tmp_path, monkeypatch):
    """config.toml should have default_type instead of claude_args."""
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("test", server="127.0.0.1", port=6667, tls=False,
                          password="", nick="alice", channels="#general")
    cfg = load_project_config("test")
    assert cfg["agents"]["default_type"] == "claude"
    assert "claude_args" not in cfg["agents"]


def test_set_config_value(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("test-set", server="127.0.0.1", port=6667,
                          tls=False, password="", nick="alice", channels="#general")
    set_config_value("test-set", "agents.default_type", "codex")
    cfg = load_project_config("test-set")
    assert cfg["agents"]["default_type"] == "codex"


def test_create_project_config_no_auth_section(tmp_path, monkeypatch):
    """config.toml should not contain [auth] section."""
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("test", server="127.0.0.1", port=6667, tls=False,
                          password="", nick="", channels="#general")
    cfg = load_project_config("test")
    assert "auth" not in cfg


def test_project_create_config_with_default_type(tmp_path, monkeypatch):
    """create_project_config stores the selected default_type."""
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("typed", server="127.0.0.1", port=6667, tls=False,
                          password="", nick="", channels="#general",
                          default_type="claude")
    cfg = load_project_config("typed")
    assert cfg["agents"]["default_type"] == "claude"
    assert "auth" not in cfg


def test_project_create_with_env_file(tmp_path, monkeypatch):
    """Proxy env_file path is stored in config."""
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    env_path = str(tmp_path / "projects" / "proxy-test" / "claude.local.env")
    create_project_config("proxy-test", server="127.0.0.1", port=6667, tls=False,
                          password="", nick="", channels="#general",
                          env_file=env_path)
    cfg = load_project_config("proxy-test")
    assert cfg["agents"]["env_file"] == env_path


def test_create_project_generates_tmuxp_yaml(tmp_path, monkeypatch):
    """project create should generate tmuxp.yaml and bootstrap.sh."""
    import yaml
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("test-tmuxp", server="127.0.0.1", port=6667,
                          tls=False, password="", nick="", channels="#general")
    pdir = tmp_path / "projects" / "test-tmuxp"
    tmuxp_path = pdir / "tmuxp.yaml"
    bootstrap_path = pdir / "bootstrap.sh"
    assert tmuxp_path.exists()
    assert bootstrap_path.exists()
    with open(tmuxp_path) as f:
        cfg = yaml.safe_load(f)
    assert cfg["session_name"].startswith("zchat-")
    assert cfg["before_script"] == str(bootstrap_path)
    assert str(pdir) in cfg["start_directory"]
    assert os.access(str(bootstrap_path), os.X_OK)
