---
type: code-diff
id: code-diff-v5-phase8
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 8
related:
  - eval-doc-010
  - test-plan-011
  - test-diff-v5-phase8
spec: docs/spec/channel-server-v5.md §4.2 audit
plan: docs/discuss/plan/v5-refactor-plan.md §Phase-8
---

# Code Diff: V5 Phase 8 — audit 仪表盘扩展 + audit CLI

## 改动摘要

audit plugin 扩展 6 维度指标；新增 `zchat audit` CLI（status / report / export）供 admin-agent 调用。

## 文件清单

**修改（CS）：**
- `src/plugins/audit/plugin.py` — `_compute_aggregates` 输出 `total_takeovers / total_resolved / escalation_resolve_rate / csat_mean`

**新增（zchat 主仓 CLI）：**
- `zchat/cli/audit_cmd.py` — `typer` sub-app `status / report / export`

**修改（zchat 主仓 CLI）：**
- `zchat/cli/app.py` — 注册 `audit_app`

## 关键 aggregates

```python
return {
    "total_channels": ...,
    "total_takeovers": ...,
    "total_resolved": ...,
    "escalation_resolve_rate": round(takeover_then_resolve / total_takeovers, 3),
    "csat_mean": round(sum(scores)/len(scores), 2) if scores else None,
}
```

## CLI 用法

```bash
zchat audit status [--json] [--channel X]
zchat audit report [--json]
zchat audit export --format json > out.json
```

admin-agent 通过 `run_zchat_cli(["audit", "status", "--json"])` 调用。

## 验收

- unit: tests/unit/test_audit_plugin.py — 时间戳跟踪 + aggregates 正确
- e2e: tests/e2e/test_admin_commands_via_cli.py::test_status_command_mapping / test_review_command_mapping
