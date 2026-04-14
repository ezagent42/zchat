"""Unit tests for `zchat project use` command behavior."""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from zchat.cli.app import app

runner = CliRunner()


def test_project_use_no_attach_skips_session_launch(tmp_path, monkeypatch):
    """`project use --no-attach` should not call Zellij attach/switch."""
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
    project_name = "proj-no-attach"
    project_dir = tmp_path / "projects" / project_name
    project_dir.mkdir(parents=True)

    with patch("zchat.cli.app._launch_project_session") as mock_launch:
        result = runner.invoke(app, ["project", "use", project_name, "--no-attach"])

    assert result.exit_code == 0, result.output
    assert f"Default project set to '{project_name}'." in result.output
    assert "Skip attaching session." in result.output
    mock_launch.assert_not_called()
    assert (tmp_path / "default").read_text().strip() == project_name


def test_project_use_default_behavior_launches_session(tmp_path, monkeypatch):
    """Without --no-attach, command should still launch project session."""
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
    project_name = "proj-attach"
    Path(tmp_path / "projects" / project_name).mkdir(parents=True)

    with patch("zchat.cli.app._launch_project_session") as mock_launch:
        result = runner.invoke(app, ["project", "use", project_name])

    assert result.exit_code == 0, result.output
    mock_launch.assert_called_once_with(project_name)
