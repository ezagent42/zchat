"""Unit tests for `zchat project use` command behavior (V6).

V6 行为变更：默认不启动服务（与 V5 反向）。
- 无 flag：仅切默认项目，不 attach session
- `--attach`：保留 V5 旧行为（启动 ergo + WeeChat + agent）
"""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from zchat.cli.app import app

runner = CliRunner()


def test_project_use_default_does_not_launch(tmp_path, monkeypatch):
    """V6: 默认行为不应触发 _launch_project_session。"""
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
    project_name = "proj-default"
    (tmp_path / "projects" / project_name).mkdir(parents=True)

    with patch("zchat.cli.app._launch_project_session") as mock_launch:
        result = runner.invoke(app, ["project", "use", project_name])

    assert result.exit_code == 0, result.output
    assert f"Default project set to '{project_name}'." in result.output
    assert "Run `zchat up`" in result.output
    mock_launch.assert_not_called()
    assert (tmp_path / "default").read_text().strip() == project_name


def test_project_use_attach_launches_session(tmp_path, monkeypatch):
    """V6: --attach 显式选择 V5 行为，会启动 session。"""
    monkeypatch.setenv("ZCHAT_HOME", str(tmp_path))
    project_name = "proj-attach"
    Path(tmp_path / "projects" / project_name).mkdir(parents=True)

    with patch("zchat.cli.app._launch_project_session") as mock_launch:
        result = runner.invoke(app, ["project", "use", project_name, "--attach"])

    assert result.exit_code == 0, result.output
    mock_launch.assert_called_once_with(project_name)
