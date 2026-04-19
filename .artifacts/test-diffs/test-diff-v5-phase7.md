---
type: test-diff
id: test-diff-v5-phase7
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 7
related: [eval-doc-010, test-plan-011, code-diff-v5-phase7]
---

# Test Diff: V5 Phase 7

## 新增文件

- `tests/unit/test_audit_plugin.py`
- `tests/unit/test_activation_plugin.py`

## 关键 case

| 测试 | TC | 验证 |
|------|----|------|
| test_mode_changed_records_takeover | TC-V5-7.1 | takeover 计数 + 时间戳 |
| test_channel_resolved_marks_state | TC-V5-7.1 | resolved_at 写入 |
| test_query_status_returns_aggregates | TC-V5-7.2 | aggregates 字段齐全 |
| test_query_status_for_channel | TC-V5-7.2 | 单 channel 详情 |
| test_persistence_roundtrip | TC-V5-7.1 | audit.json 写盘 + reload |
| test_customer_returned_emits_event | TC-V5-7.3 | activation 检测正确 |

## 跑分

unit 全过。
