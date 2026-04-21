# tests/unit/test_paths.py
"""Tests for centralized path resolution."""
from pathlib import Path
from unittest.mock import patch

import pytest

from zchat.cli import paths


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear lru_cache between tests."""
    paths._load_default_paths.cache_clear()
    yield
    paths._load_default_paths.cache_clear()


class TestZchatHome:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("ZCHAT_HOME", raising=False)
        result = paths.zchat_home()
        assert result == Path("~/.zchat").expanduser()

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("ZCHAT_HOME", "/tmp/custom-zchat")
        assert paths.zchat_home() == Path("/tmp/custom-zchat")

    def test_tilde_expansion(self, monkeypatch):
        monkeypatch.setenv("ZCHAT_HOME", "~/my-zchat")
        result = paths.zchat_home()
        assert "~" not in str(result)
        assert result.name == "my-zchat"


class TestPluginsDir:
    def test_default(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        monkeypatch.delenv("ZCHAT_PLUGINS_DIR", raising=False)
        assert paths.plugins_dir() == tmp_path / "plugins"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("ZCHAT_PLUGINS_DIR", "/opt/plugins")
        assert paths.plugins_dir() == Path("/opt/plugins")

    def test_config_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        monkeypatch.delenv("ZCHAT_PLUGINS_DIR", raising=False)
        # Write config.toml with [paths]
        import tomli_w
        config = {"paths": {"plugins": "custom-plugins"}}
        (tmp_path / "config.toml").write_bytes(tomli_w.dumps(config).encode())
        assert paths.plugins_dir() == tmp_path / "custom-plugins"

    def test_config_absolute_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        monkeypatch.delenv("ZCHAT_PLUGINS_DIR", raising=False)
        import tomli_w
        config = {"paths": {"plugins": "/absolute/plugins"}}
        (tmp_path / "config.toml").write_bytes(tomli_w.dumps(config).encode())
        assert paths.plugins_dir() == Path("/absolute/plugins")


class TestTemplatesDir:
    def test_default(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        monkeypatch.delenv("ZCHAT_TEMPLATES_DIR", raising=False)
        assert paths.templates_dir() == tmp_path / "templates"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("ZCHAT_TEMPLATES_DIR", "/opt/templates")
        assert paths.templates_dir() == Path("/opt/templates")


class TestProjectPaths:
    def test_project_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        assert paths.project_dir("myproj") == tmp_path / "projects" / "myproj"

    def test_project_config(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        assert paths.project_config("myproj") == tmp_path / "projects" / "myproj" / "config.toml"

    def test_project_state(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        assert paths.project_state("myproj") == tmp_path / "projects" / "myproj" / "state.json"

    def test_ergo_data_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        assert paths.ergo_data_dir("myproj") == tmp_path / "projects" / "myproj" / "ergo"

    def test_weechat_home(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        assert paths.weechat_home("myproj") == tmp_path / "projects" / "myproj" / ".weechat"

    def test_project_env_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        assert paths.project_env_file("myproj") == tmp_path / "projects" / "myproj" / "claude.local.env"


class TestAgentPaths:
    def test_workspace(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        assert paths.agent_workspace("proj", "alice-agent0") == (
            tmp_path / "projects" / "proj" / "agents" / "alice-agent0"
        )

    def test_ready_marker(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        assert paths.agent_ready_marker("proj", "alice-agent0") == (
            tmp_path / "projects" / "proj" / "agents" / "alice-agent0.ready"
        )


class TestGlobalFiles:
    def test_global_config(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        assert paths.global_config_path() == tmp_path / "config.toml"

    def test_update_state(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        assert paths.update_state() == tmp_path / "update.json"

    def test_default_project_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        assert paths.default_project_file() == tmp_path / "default"


class TestResolutionPriority:
    """Verify env var > config.toml > defaults.toml priority."""

    def test_env_beats_config(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        monkeypatch.setenv("ZCHAT_PLUGINS_DIR", "/env-plugins")
        import tomli_w
        config = {"paths": {"plugins": "config-plugins"}}
        (tmp_path / "config.toml").write_bytes(tomli_w.dumps(config).encode())
        assert paths.plugins_dir() == Path("/env-plugins")

    def test_config_beats_defaults(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        monkeypatch.delenv("ZCHAT_PLUGINS_DIR", raising=False)
        import tomli_w
        config = {"paths": {"plugins": "override-plugins"}}
        (tmp_path / "config.toml").write_bytes(tomli_w.dumps(config).encode())
        assert paths.plugins_dir() == tmp_path / "override-plugins"

    def test_defaults_fallback(self, monkeypatch, tmp_path):
        """No env var, no config.toml → uses defaults.toml value."""
        monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
        monkeypatch.delenv("ZCHAT_PLUGINS_DIR", raising=False)
        # No config.toml exists, so falls through to defaults.toml
        result = paths.plugins_dir()
        # defaults.toml has plugins = "plugins"
        assert result == tmp_path / "plugins"
