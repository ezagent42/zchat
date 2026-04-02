# tests/pre_release/test_07_self_update.py
"""Pre-release: update/upgrade commands."""
import pytest


@pytest.mark.manual
@pytest.mark.order(1)
def test_update_check(cli):
    """update command checks for new versions."""
    result = cli("update", check=False)
    assert isinstance(result.returncode, int)


@pytest.mark.manual
@pytest.mark.order(2)
def test_upgrade(cli):
    """upgrade command is callable."""
    result = cli("upgrade", check=False)
    assert isinstance(result.returncode, int)


@pytest.mark.manual
@pytest.mark.order(3)
def test_config_list(cli):
    """config list shows update settings."""
    result = cli("config", "list", check=False)
    assert "update.channel" in result.stdout
