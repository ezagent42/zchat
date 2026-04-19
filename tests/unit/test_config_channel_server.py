"""Tests for channel_server config section in project config."""
import tomllib

import pytest


@pytest.fixture
def _zchat_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
    return tmp_path


def test_default_config_has_channel_server(_zchat_home):
    """generate_default_config includes [channel_server] with correct defaults."""
    from zchat.cli.project import generate_default_config

    text = generate_default_config("test-project", server="127.0.0.1", port=6667)
    config = tomllib.loads(text)
    assert "channel_server" in config
    assert config["channel_server"]["bridge_port"] == 9999
    assert config["channel_server"]["timers"]["takeover_wait"] == 180
    assert config["channel_server"]["participants"]["max_operator_concurrent"] == 5


def test_channel_server_timers_complete(_zchat_home):
    """All timer defaults are present."""
    from zchat.cli.project import generate_default_config

    text = generate_default_config("test-project", server="127.0.0.1", port=6667)
    config = tomllib.loads(text)
    timers = config["channel_server"]["timers"]
    assert timers["takeover_wait"] == 180
    assert timers["idle_timeout"] == 300
    assert timers["close_timeout"] == 3600


def test_channel_server_participants_defaults(_zchat_home):
    """Participants section has correct defaults."""
    from zchat.cli.project import generate_default_config

    text = generate_default_config("test-project", server="127.0.0.1", port=6667)
    config = tomllib.loads(text)
    participants = config["channel_server"]["participants"]
    assert participants["operators"] == []
    assert participants["bridge_prefixes"] == []
    assert participants["max_operator_concurrent"] == 5


def test_channel_server_paths_defaults(_zchat_home):
    """channel_server has plugins_dir and db_path defaults."""
    from zchat.cli.project import generate_default_config

    text = generate_default_config("test-project", server="127.0.0.1", port=6667)
    config = tomllib.loads(text)
    cs = config["channel_server"]
    assert cs["plugins_dir"] == "plugins"
    assert cs["db_path"] == "conversations.db"


def test_create_project_config_includes_channel_server(_zchat_home):
    """create_project_config writes channel_server to config.toml on disk."""
    from zchat.cli.project import create_project_config, load_project_config

    create_project_config("test-project", server="local")
    cfg = load_project_config("test-project")
    assert "channel_server" in cfg
    assert cfg["channel_server"]["bridge_port"] == 9999
