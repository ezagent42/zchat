---
type: test-diff
id: test-diff-005
status: merged
producer: skill-3
created_at: "2026-04-13T18:17:00Z"
related:
  - test-plan: test-plan-008
  - eval-doc: eval-doc-007
---

# Test Diff: Ctrl+C 中断清理单元测试

## 来源
- test-plan: `test-plan-008`（TC-001 ~ TC-006）
- 新增至: `tests/unit/test_agent_manager.py`（+6 个测试）

## 新增测试

| 测试函数 | 覆盖 TC | 阶段 | 修复前 | 修复后 |
|---------|---------|------|--------|--------|
| test_create_calls_force_stop_on_keyboard_interrupt | TC-001 | P0 | FAIL | PASS |
| test_create_writes_offline_status_on_keyboard_interrupt | TC-002 | P0 | FAIL | PASS |
| test_create_blocked_when_status_is_starting | TC-003 | P0 | FAIL | PASS |
| test_create_cleans_ready_marker_on_keyboard_interrupt | TC-004 | P1 | FAIL | PASS |
| test_create_succeeds_on_second_attempt_after_interrupt | TC-005 | P1 | PASS | PASS |
| test_auto_confirm_thread_exits_when_pane_not_found | TC-006 | P1 | PASS | PASS |

## 全量回归

原有 13 个测试（test_scope_agent_name 等）修复后全部保持 PASS，无回归。

## 运行结果（修复后）

```
uv run --no-sync pytest tests/unit/test_agent_manager.py -v
19 passed in 5.20s
```

验证时间：2026-04-14，Python 3.13.12
