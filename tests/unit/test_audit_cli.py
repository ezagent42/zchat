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
    """构造一个 audit.json 并通过 CS_DATA_DIR 环境变量让 CLI 找到。"""
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
    p = tmp_path / "audit.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("CS_DATA_DIR", str(tmp_path))
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
    """audit.json 不存在 → 返回空聚合。"""
    monkeypatch.setenv("CS_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["audit", "status"])
    assert result.exit_code == 0
    assert "total channels: 0" in result.output
