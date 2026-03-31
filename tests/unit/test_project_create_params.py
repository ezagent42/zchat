"""Unit tests for project create CLI parameterization."""
import os
import tomllib
import pytest
from typer.testing import CliRunner
from zchat.cli.app import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Redirect ZCHAT_HOME to temp dir for each test."""
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    return tmp_path


def _load_config(home, name):
    with open(os.path.join(str(home), "projects", name, "config.toml"), "rb") as f:
        return tomllib.load(f)


def test_create_with_all_params(isolated_home):
    """All CLI options provided → no interactive prompts."""
    result = runner.invoke(app, [
        "project", "create", "test-proj",
        "--server", "127.0.0.1",
        "--port", "6667",
        "--channels", "#general",
        "--agent-type", "claude",
        "--proxy", "",
    ])
    assert result.exit_code == 0, result.output
    cfg = _load_config(isolated_home, "test-proj")
    assert cfg["irc"]["server"] == "127.0.0.1"
    assert cfg["irc"]["port"] == 6667
    assert cfg["irc"]["tls"] is False
    assert cfg["agents"]["default_type"] == "claude"
    assert "#general" in cfg["agents"]["default_channels"]


def test_create_with_zchat_inside_server(isolated_home):
    """--server zchat.inside.h2os.cloud → defaults: port 6697, tls True."""
    result = runner.invoke(app, [
        "project", "create", "tls-proj",
        "--server", "zchat.inside.h2os.cloud",
        "--channels", "#general",
        "--agent-type", "claude",
        "--proxy", "",
    ])
    assert result.exit_code == 0, result.output
    cfg = _load_config(isolated_home, "tls-proj")
    assert cfg["irc"]["port"] == 6697
    assert cfg["irc"]["tls"] is True


def test_create_with_explicit_port_tls(isolated_home):
    """Explicit --port and --tls override server defaults."""
    result = runner.invoke(app, [
        "project", "create", "custom-proj",
        "--server", "127.0.0.1",
        "--port", "7000",
        "--tls",
        "--channels", "#dev",
        "--agent-type", "claude",
        "--proxy", "",
    ])
    assert result.exit_code == 0, result.output
    cfg = _load_config(isolated_home, "custom-proj")
    assert cfg["irc"]["port"] == 7000
    assert cfg["irc"]["tls"] is True


def test_create_with_proxy(isolated_home):
    """--proxy creates claude.local.env with proxy settings."""
    result = runner.invoke(app, [
        "project", "create", "proxy-proj",
        "--server", "127.0.0.1",
        "--channels", "#general",
        "--agent-type", "claude",
        "--proxy", "10.0.0.1:8080",
    ])
    assert result.exit_code == 0, result.output
    env_path = os.path.join(str(isolated_home), "projects", "proxy-proj", "claude.local.env")
    assert os.path.isfile(env_path)
    content = open(env_path).read()
    assert "HTTP_PROXY=http://10.0.0.1:8080" in content


def test_create_invalid_agent_type(isolated_home):
    """--agent-type with nonexistent template → exit 1."""
    result = runner.invoke(app, [
        "project", "create", "bad-proj",
        "--server", "127.0.0.1",
        "--channels", "#general",
        "--agent-type", "nonexistent-type",
    ])
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "error" in result.output.lower()
