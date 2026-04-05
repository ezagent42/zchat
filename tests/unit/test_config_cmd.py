"""Tests for global config management (config_cmd.py)."""
from __future__ import annotations

import pytest


@pytest.fixture
def config_toml(tmp_path, monkeypatch):
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
    import zchat.cli.project as proj
    monkeypatch.setattr(proj, "ZCHAT_DIR", str(tmp_path))
    import zchat.cli.config_cmd as cfg
    monkeypatch.setattr(cfg, "_GLOBAL_CONFIG", str(tmp_path / "config.toml"))
    return str(tmp_path / "config.toml")


def test_load_missing_file_returns_defaults(config_toml):
    """load_global_config with no file returns hardcoded defaults."""
    import zchat.cli.config_cmd as cfg

    result = cfg.load_global_config(config_toml)

    assert result["update"]["channel"] == "main"
    assert result["update"]["auto_upgrade"] is True


def test_save_and_load_roundtrip(config_toml):
    """save_global_config + load_global_config preserves all values."""
    import zchat.cli.config_cmd as cfg

    data = {"update": {"channel": "stable", "auto_upgrade": False}}
    cfg.save_global_config(data, config_toml)

    loaded = cfg.load_global_config(config_toml)

    assert loaded["update"]["channel"] == "stable"
    assert loaded["update"]["auto_upgrade"] is False


def test_set_and_get_string_value(config_toml):
    """set_config_value + get_config_value works for string values."""
    import zchat.cli.config_cmd as cfg

    config = cfg.load_global_config(config_toml)
    cfg.set_config_value(config, "update.channel", "stable")

    assert cfg.get_config_value(config, "update.channel") == "stable"


def test_set_bool_false(config_toml):
    """set_config_value converts 'false' string to Python False."""
    import zchat.cli.config_cmd as cfg

    config = cfg.load_global_config(config_toml)
    cfg.set_config_value(config, "update.auto_upgrade", "false")

    assert cfg.get_config_value(config, "update.auto_upgrade") is False


def test_set_bool_true(config_toml):
    """set_config_value converts 'true' string to Python True."""
    import zchat.cli.config_cmd as cfg

    config = cfg.load_global_config(config_toml)
    cfg.set_config_value(config, "update.auto_upgrade", "true")

    assert cfg.get_config_value(config, "update.auto_upgrade") is True


def test_get_missing_key_returns_none(config_toml):
    """get_config_value returns None for a key that doesn't exist."""
    import zchat.cli.config_cmd as cfg

    config = cfg.load_global_config(config_toml)

    assert cfg.get_config_value(config, "nonexistent.key") is None
    assert cfg.get_config_value(config, "update.nonexistent") is None


def test_set_nested_server_config(config_toml):
    """set_config_value supports deeply nested keys like servers.local.host."""
    import zchat.cli.config_cmd as cfg

    config = cfg.load_global_config(config_toml)
    cfg.set_config_value(config, "servers.local.host", "127.0.0.1")
    cfg.set_config_value(config, "servers.local.port", 6667)

    assert cfg.get_config_value(config, "servers.local.host") == "127.0.0.1"
    assert cfg.get_config_value(config, "servers.local.port") == 6667


def test_set_runner_config(config_toml):
    """set_config_value supports runner config with string command."""
    import zchat.cli.config_cmd as cfg

    config = cfg.load_global_config(config_toml)
    cfg.set_config_value(config, "runners.claude-channel.command", "claude")
    cfg.set_config_value(config, "runners.claude-channel.args", ["--model", "opus"])

    assert cfg.get_config_value(config, "runners.claude-channel.command") == "claude"
    assert cfg.get_config_value(config, "runners.claude-channel.args") == ["--model", "opus"]


def test_set_int_value(config_toml):
    """set_config_value stores int values directly (no string coercion)."""
    import zchat.cli.config_cmd as cfg

    config = cfg.load_global_config(config_toml)
    cfg.set_config_value(config, "servers.local.port", 6697)

    assert cfg.get_config_value(config, "servers.local.port") == 6697
    assert isinstance(cfg.get_config_value(config, "servers.local.port"), int)


def test_set_bool_value_direct(config_toml):
    """set_config_value stores bool values directly (no string coercion)."""
    import zchat.cli.config_cmd as cfg

    config = cfg.load_global_config(config_toml)
    cfg.set_config_value(config, "servers.local.tls", True)

    assert cfg.get_config_value(config, "servers.local.tls") is True


def test_set_list_value(config_toml):
    """set_config_value stores list values directly."""
    import zchat.cli.config_cmd as cfg

    config = cfg.load_global_config(config_toml)
    cfg.set_config_value(config, "default_channels", ["#general", "#dev"])

    assert cfg.get_config_value(config, "default_channels") == ["#general", "#dev"]
