---
type: test-diff
id: test-diff-v5-phase10
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 10
related: [eval-doc-010, test-plan-011, code-diff-v5-phase10]
---

# Test Diff: V5 Phase 10

## 修改/新增文件

- `tests/unit/test_sla_plugin.py` — 新增 7 个 help timer case
- `tests/e2e/test_help_request_lifecycle.py` — 3 个 e2e 场景

## 关键 case（unit）

| 测试 | TC | 验证 |
|------|----|------|
| test_side_operator_mention_starts_help_timer | TC-V5-10.1 | __side:@operator → _help_timers[ch] 存在 |
| test_side_admin_mention_also_triggers | TC-V5-10.2 | @admin / @人工 同样触发 |
| test_non_side_msg_ignored_for_help | TC-V5-10.3 | 无 __side: 前缀不触发 |
| test_operator_side_cancels_help_timer | TC-V5-10.4 | source 含 operator → cancel |
| test_help_timer_expiry_emits_help_timeout | TC-V5-10.5 | timeout → emit help_timeout event |
| test_release_to_copilot_cancels_help_timer | TC-V5-10.5 | mode 切回 copilot 一并清理 help timer |

## 关键 case（e2e）

- test_operator_responds_in_time
- test_operator_no_response_emits_timeout
- test_help_and_takeover_timers_independent

## 跑分

unit + e2e 全过。
