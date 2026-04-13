---
type: test-diff
id: test-diff-001
status: draft
producer: skill-3
created_at: "2026-04-10"
updated_at: "2026-04-10"
related:
  - test-plan-004
evidence: []
---

# Test Diff: Agent DM (PRIVMSG) E2E 测试

## Source

- Test plan: test-plan-004 (.artifacts/test-plans/plan-agent-dm-004.md)
- Status: confirmed → executed

## Changes

### New test cases

| File | Function | Order | Domain | Validates (TC) |
|------|----------|-------|--------|-----------------|
| tests/e2e/test_agent_dm.py | test_create_agent_for_dm | 100 | setup | DM 测试套件的 agent 创建 |
| tests/e2e/test_agent_dm.py | test_send_dm_agent_to_nick | 101 | agent-dm | TC-001: agent 发送 DM 到 nick |
| tests/e2e/test_agent_dm.py | test_receive_dm_from_user | 102 | agent-dm | TC-002: agent 接收 DM 后仍正常运行 |
| tests/e2e/test_agent_dm.py | test_send_dm_cross_user | 103 | agent-dm | TC-003: 跨用户 DM |
| tests/e2e/test_agent_dm.py | test_send_dm_long_message | 104 | agent-dm | TC-006: 超 512 字节长消息分片 |
| tests/e2e/test_agent_dm.py | test_dm_mention_no_notification | 105 | agent-dm | TC-011: DM 中 @mention 不触发第三方通知 |
| tests/e2e/test_agent_dm.py | test_shutdown_dm_agents | 109 | cleanup | DM 测试套件的 agent 清理 |

### New fixtures

无 — 全部复用 conftest.py 中现有 fixture (zchat_cli, irc_probe, bob_probe)。

### Modified files

- `tests/e2e/test_agent_dm.py`: **新文件**，7 个 E2E test case

### Deferred TCs

| TC | Reason |
|----|--------|
| TC-004 | 需新增 list_agents MCP tool |
| TC-005 | 需修复 _handle_reply 离线错误处理 |
| TC-007 | 需 WeeChat + agent 协调区分人类 vs agent DM |
| TC-008 | 需新增 send_sys_message MCP tool |
| TC-009 | 多轮 DM 对话上下文保持 — 验证复杂度高 |
| TC-010 | 跨 agent 任务委派 — 验证复杂度高 |

## Adaptation Notes

test-plan-004 的 TC 设计基于两个真实 agent 间的 DM 交互，但 E2E 中 agent 间 PRIVMSG 无法被第三方观测。
适配策略：使用 IrcProbe / bob_probe 作为 DM 对端。IRC PRIVMSG 机制不区分 agent 与普通客户端，
因此 reply tool → connection.privmsg() → on_privmsg() 的代码路径完全一致。

## Validation

- Syntax: `ast.parse()` 通过
- Imports: time, pytest — 全部可解析
- Fixture graph: 无循环依赖，全部引用 conftest.py 中已有 fixture
- Naming: 全部符合 `test_{action}_{target}` 规范
- Ordering: 使用 100-109 范围，与现有 1-9 无冲突
