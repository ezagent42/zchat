---
type: test-diff
id: test-diff-v5-phase3
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 3
related: [eval-doc-010, test-plan-011, code-diff-v5-phase3]
---

# Test Diff: V5 Phase 3

## 修改/新增文件

- `zchat-channel-server/tests/unit/test_routing.py` — entry_agent / bot_id 字段解析 + 兼容
- `zchat-channel-server/tests/unit/test_router.py` — `make_routing_with_agents` helper 默认 entry = first agent；新 case `test_copilot_mode_only_ats_entry_agent` 替代旧 `test_copilot_mode_with_multiple_agents`
- `tests/unit/test_routing_cli.py` — `--entry-agent --bot-id` 写入 routing.toml
- `tests/unit/test_channel_cmd.py` — `channel remove [--stop-agents]` + `channel set-entry`

## 关键 case

| 测试 | TC | 验证 |
|------|----|------|
| test_load_route_with_entry_agent | TC-V5-3.1 | entry_agent 字段解析 |
| test_load_route_without_entry_agent | TC-V5-3.2 | 向后兼容降级 None |
| test_copilot_mode_only_ats_entry_agent | TC-V5-3.3 | 1 条 IRC PRIVMSG，@entry_agent |
| test_takeover_mode_no_at | TC-V5-3.4 | 无 @ 前缀 |
| test_add_channel_with_entry_and_bot_id | TC-V5-3.5 | CLI 写入 |
| test_channel_remove_clears_entry | TC-V5-3.6 | CLI remove 清理 |

## 跑分

unit 全过。
