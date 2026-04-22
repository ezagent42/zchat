"""zchat audit CLI 单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zchat.cli.app import app


runner = CliRunner()


@pytest.fixture
def audit_json(tmp_path, monkeypatch):
    """构造一个 audit plugin state.json 并 monkeypatch project_dir 让 CLI 找到。

    V7 路径：<project_dir>/plugins/audit/state.json（V6 的 audit.json 已废弃）。
    """
    data = {
        "channels": {
            "conv-a": {
                "state": "active",
                "created_at": "2026-01-01T00:00:00Z",
                "first_reply_at": "2026-01-01T00:00:02Z",
                "resolved_at": None,
                "message_count": 10,
                "takeovers": [
                    {"at": "2026-01-01T00:10:00Z", "triggered_by": "op",
                     "released_at": "2026-01-01T00:12:00Z", "released_by": "op"},
                ],
                "csat_score": None,
            },
            "conv-b": {
                "state": "resolved",
                "resolved_at": "2026-01-01T01:00:00Z",
                "message_count": 5,
                "takeovers": [],
                "csat_score": 5,
            },
            "conv-c": {
                "state": "takeover",
                "message_count": 3,
                "takeovers": [{"at": "2026-01-01T02:00:00Z", "released_at": None}],
            },
        }
    }
    # V7: state 落在 <project_dir>/plugins/audit/state.json
    project_path = tmp_path / "audit-test"
    audit_dir = project_path / "plugins" / "audit"
    audit_dir.mkdir(parents=True)
    p = audit_dir / "state.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    # 构造最小合法 project（main callback 会 load_project_config）
    (project_path / "config.toml").write_text("", encoding="utf-8")

    # Patch app.py 级别的 resolve/load（module-level import）
    from zchat.cli import app as _app
    monkeypatch.setattr(_app, "resolve_project", lambda explicit=None: "audit-test")
    monkeypatch.setattr(_app, "load_project_config", lambda name: {})
    # Patch paths.project_dir（audit_cmd 函数内 import，monkeypatch 生效）
    from zchat.cli import paths as _paths
    monkeypatch.setattr(_paths, "project_dir",
                        lambda name: project_path if name == "audit-test" else Path("/nonexistent"))
    return p


def test_audit_status_all(audit_json):
    result = runner.invoke(app, ["audit", "status"])
    assert result.exit_code == 0, result.output
    assert "total channels: 3" in result.output
    assert "total takeovers: 2" in result.output
    assert "total resolved: 1" in result.output
    # 活跃 channel
    assert "conv-a" in result.output
    assert "conv-c" in result.output


def test_audit_status_by_channel(audit_json):
    result = runner.invoke(app, ["audit", "status", "--channel", "conv-a"])
    assert result.exit_code == 0, result.output
    assert "Channel: conv-a" in result.output
    assert "state: active" in result.output
    assert "message_count: 10" in result.output


def test_audit_status_unknown_channel(audit_json):
    result = runner.invoke(app, ["audit", "status", "--channel", "no-such"])
    assert result.exit_code != 0


def test_audit_status_json(audit_json):
    result = runner.invoke(app, ["audit", "status", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "channels" in data
    assert "aggregates" in data
    assert data["aggregates"]["total_takeovers"] == 2


def test_audit_report(audit_json):
    result = runner.invoke(app, ["audit", "report"])
    assert result.exit_code == 0
    assert "total takeovers: 2" in result.output
    assert "CSAT mean" in result.output


def test_audit_report_json(audit_json):
    result = runner.invoke(app, ["audit", "report", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "total_takeovers" in data
    assert data["csat_mean"] == 5.0


def test_audit_export_stdout(audit_json):
    result = runner.invoke(app, ["audit", "export"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "channels" in data


def test_audit_export_to_file(audit_json, tmp_path):
    out = tmp_path / "export.json"
    result = runner.invoke(app, ["audit", "export", "-o", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    data = json.loads(out.read_text())
    assert "channels" in data


def test_audit_status_missing_file(tmp_path, monkeypatch):
    """state.json 不存在 → 返回空聚合。"""
    project_path = tmp_path / "empty-proj"
    project_path.mkdir()
    (project_path / "config.toml").write_text("", encoding="utf-8")
    from zchat.cli import app as _app
    monkeypatch.setattr(_app, "resolve_project", lambda explicit=None: "empty-proj")
    monkeypatch.setattr(_app, "load_project_config", lambda name: {})
    from zchat.cli import paths as _paths
    monkeypatch.setattr(_paths, "project_dir",
                        lambda name: project_path if name == "empty-proj" else Path("/nonexistent"))
    result = runner.invoke(app, ["audit", "status"])
    assert result.exit_code == 0
    assert "total channels: 0" in result.output
