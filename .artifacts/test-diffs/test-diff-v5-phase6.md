---
type: test-diff
id: test-diff-v5-phase6
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 6
related: [eval-doc-010, test-plan-011, code-diff-v5-phase6]
---

# Test Diff: V5 Phase 6

## 新增文件

- `tests/unit/test_routing_reader.py`
- `tests/e2e/test_bridge_lazy_create.py`

## 关键 case

| 测试 | TC | 验证 |
|------|----|------|
| test_filter_by_bot_id | TC-V5-6.1 | 多 bot_id 时只返回本 bot 的 mapping |
| test_empty_routing_returns_empty | TC-V5-6.1 | 文件不存在 / 空时返回 {} |
| test_bot_added_triggers_subprocess | TC-V5-6.2 | mock subprocess，确认 channel create + agent create |
| test_disbanded_triggers_remove | TC-V5-6.3 | mock subprocess，确认 channel remove --stop-agents |

## 红线 grep（CI lint）

- `grep -rn "from channel_server" src/feishu_bridge/` 仅 docstring 提及
- `grep -rn "import channel_server" src/feishu_bridge/` 无匹配

## 跑分

unit + e2e 全过。
