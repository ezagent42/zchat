---
type: test-diff
id: test-diff-v5-phase5
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 5
related: [eval-doc-010, test-plan-011, code-diff-v5-phase5]
---

# Test Diff: V5 Phase 5

## 修改文件

- `tests/unit/test_router.py` — emit_event 三路广播 case
- `tests/unit/test_agent_mcp.py` — sys 注入 case + 不被 mention 误匹配

## 关键 case

| 测试 | TC | 验证 |
|------|----|------|
| test_emit_event_broadcasts_to_irc_sys | TC-V5-5.1 | irc.privmsg("#x", "__zchat_sys:...") 被调用 |
| test_emit_event_broadcasts_to_ws_and_plugin | TC-V5-5.1 | ws + registry broadcast 都触发 |
| test_pubmsg_sys_injects_sys_message | TC-V5-5.2 | 队列拿到 type="sys" 消息 |
| test_pubmsg_sys_does_not_trigger_mention | TC-V5-5.3 | 不死循环 |

## 跑分

unit 全过。
