# tests/pre_release/test_01_project.py
"""Pre-release: project lifecycle management."""
import pytest

from tests.pre_release import PROJECT_NAME, SECOND_PROJECT


@pytest.mark.order(1)
def test_project_list(cli, project):
    """Main project appears in project list."""
    result = cli("project", "list")
    assert PROJECT_NAME in result.stdout


@pytest.mark.order(2)
def test_project_show(cli, project):
    """project show displays correct config values."""
    result = cli("project", "show", PROJECT_NAME)
    assert "127.0.0.1" in result.stdout
    assert "Channels" in result.stdout or "#general" in result.stdout


@pytest.mark.order(3)
def test_project_set(cli, project, e2e_port):
    """zchat set updates config, then restore original value."""
    cli("set", "username", "testuser")
    result = cli("project", "show", PROJECT_NAME)
    assert "testuser" in result.stdout
    # Restore
    cli("set", "username", "")


@pytest.mark.order(4)
def test_project_create_second(cli, e2e_port):
    """Create second project with full CLI params."""
    result = cli(
        "project", "create", SECOND_PROJECT,
        "--server", "127.0.0.1",
        "--port", str(e2e_port + 1),
        "--channels", "#test",
        "--agent-type", "claude",
        "--proxy", "",
        check=False,
    )
    assert result.returncode == 0, f"create failed: {result.stderr}"
    list_result = cli("project", "list")
    assert SECOND_PROJECT in list_result.stdout


@pytest.mark.order(5)
def test_project_use(cli):
    """Switch default project."""
    result = cli("project", "use", SECOND_PROJECT, "--no-attach", check=False)
    assert result.returncode == 0


@pytest.mark.order(6)
def test_project_remove_second(cli):
    """Remove second project, verify gone from list."""
    cli("project", "remove", SECOND_PROJECT)
    result = cli("project", "list")
    assert SECOND_PROJECT not in result.stdout
