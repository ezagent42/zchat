---
type: test-diff
id: test-diff-v5-phase1
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 1
related: [eval-doc-010, test-plan-011, code-diff-v5-phase1]
---

# Test Diff: V5 Phase 1

## 修改文件

- `zchat-channel-server/tests/unit/test_agent_mcp.py` — 加 `test_join_channel_tool_registered` + `test_join_channel_handler_calls_irc_join`
- `zchat-channel-server/tests/unit/test_group_manager.py` — 删 is_operator_in_customer_chat 相关 case

## 关键 case

| 测试 | TC | 验证 |
|------|----|------|
| test_join_channel_tool_registered | TC-V5-1.1 | tools list 含 join_channel |
| test_join_channel_handler_joins_channel | TC-V5-1.1 | connection.join("#x") called |
| (deleted) test_is_operator_in_customer_chat | TC-V5-1.2 | 死代码删除 |

## 跑分

phase 1 后 channel-server unit 全过，无 skip。
