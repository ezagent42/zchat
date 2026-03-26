import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from wc_agent.project import (
    create_project_config, list_projects, get_default_project,
    set_default_project, resolve_project, load_project_config,
    remove_project,
)

def test_create_project_config(tmp_path, monkeypatch):
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
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
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
    (tmp_path / "projects" / "a").mkdir(parents=True)
    (tmp_path / "projects" / "b").mkdir(parents=True)
    assert set(list_projects()) == {"a", "b"}

def test_default_project(tmp_path, monkeypatch):
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
    assert get_default_project() is None
    set_default_project("my-proj")
    assert get_default_project() == "my-proj"

def test_resolve_project_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
    assert resolve_project(explicit="my-proj") == "my-proj"

def test_resolve_project_from_cwd(tmp_path, monkeypatch):
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
    marker = tmp_path / ".wc-agent"
    marker.write_text("cwd-proj")
    monkeypatch.chdir(tmp_path)
    assert resolve_project() == "cwd-proj"

def test_resolve_project_from_default(tmp_path, monkeypatch):
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
    set_default_project("default-proj")
    assert resolve_project() == "default-proj"

def test_remove_project(tmp_path, monkeypatch):
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
    create_project_config("to-remove", server="localhost", port=6667,
                          tls=False, password="", nick="x", channels="#g")
    remove_project("to-remove")
    assert not (tmp_path / "projects" / "to-remove").exists()

def test_load_project_config(tmp_path, monkeypatch):
    monkeypatch.setattr("wc_agent.project.WC_AGENT_DIR", str(tmp_path))
    create_project_config("cfg-test", server="10.0.0.1", port=6697,
                          tls=True, password="pw", nick="bob", channels="#dev,#general")
    cfg = load_project_config("cfg-test")
    assert cfg["irc"]["server"] == "10.0.0.1"
    assert cfg["irc"]["tls"] is True
    assert cfg["agents"]["username"] == "bob"
