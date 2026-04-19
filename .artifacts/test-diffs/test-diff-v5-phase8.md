---
type: test-diff
id: test-diff-v5-phase8
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 8
related: [eval-doc-010, test-plan-011, code-diff-v5-phase8]
---

# Test Diff: V5 Phase 8

## 修改/新增文件

- `tests/unit/test_audit_plugin.py` — 加 6 维度指标 case
- `tests/unit/test_audit_cmd.py`（zchat 主仓）— audit CLI

## 关键 case

| 测试 | TC | 验证 |
|------|----|------|
| test_aggregates_escalation_resolve_rate | TC-V5-8.1 | (takeover_then_resolve / total_takeovers) 正确 |
| test_aggregates_csat_mean | TC-V5-8.1 | mean 计算正确 + 无样本时 None |
| test_audit_status_cli_outputs_json | TC-V5-8.2 | --json 输出含 channels + aggregates |
| test_audit_report_cli_outputs_aggregates | TC-V5-8.3 | --json 输出聚合 |

## 跑分

unit 全过。
