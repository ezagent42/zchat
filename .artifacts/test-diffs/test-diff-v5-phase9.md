---
type: test-diff
id: test-diff-v5-phase9
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 9
related: [eval-doc-010, test-plan-011, code-diff-v5-phase9]
---

# Test Diff: V5 Phase 9

## 新增文件

- `tests/unit/test_csat_plugin.py`
- `tests/e2e/test_csat_lifecycle.py`

## 关键 case

| 测试 | TC | 验证 |
|------|----|------|
| test_resolved_emits_csat_request | TC-V5-9.1 | emit_event 调用参数 = ("csat_request", channel, {}) |
| test_score_recorded_to_audit | TC-V5-9.2 | audit.record_csat 被调用 |
| test_invalid_score_ignored | TC-V5-9.3 | "__csat_score:abc" 不抛 + 不写 |
| test_resolve_to_score_lifecycle | TC-V5-9.4 | resolve → csat_request → score → audit.json csat_score |

## 跑分

unit + e2e 全过。
