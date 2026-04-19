---
type: test-plan
id: test-plan-011
status: confirmed
producer: skill-2
created_at: "2026-04-20T00:00:00Z"
trigger: "eval-doc-010"
related:
  - eval-doc-010
  - test-diff-v5-phase1
  - test-diff-v5-phase2
  - test-diff-v5-phase3
  - test-diff-v5-phase4
  - test-diff-v5-phase5
  - test-diff-v5-phase6
  - test-diff-v5-phase7
  - test-diff-v5-phase8
  - test-diff-v5-phase9
  - test-diff-v5-phase10
  - test-diff-v5-phase11
  - e2e-report-v5-final-001
spec: docs/spec/channel-server-v5.md
---

# Test Plan: V5 Channel Server 重构

## 触发原因

eval-doc-010 列出 V5 重构 11 phase 的覆盖范围与红线；此 plan 把每个 phase 拆成可执行的测试用例。

## 测试策略

| 层级 | 工具 | 范围 |
|------|------|------|
| Unit | pytest + AsyncMock | 单 plugin/单文件函数行为；router 路由路径；CLI 命令解析 |
| E2E（CI 可跑） | pytest-asyncio + 假 subprocess | 完整 plugin pipeline、bridge lazy create、CSAT lifecycle、help request lifecycle |
| E2E（pre-release 真机） | 手动 + walkthrough | 飞书 SDK 6.3 节真机断言（不在 CI） |
| Ralph-loop | grep + import audit | 红线 + 死代码 + 悬空引用 |

## 用例索引（按 phase 分组）

### Phase 1 — A 类清理（5 TC）

| TC | 优先级 | 文件 | 验证点 |
|----|--------|-----|--------|
| TC-V5-1.1 | P0 | tests/unit/test_agent_mcp.py | join_channel tool 存在 + handler 调 connection.join("#x") |
| TC-V5-1.2 | P0 | tests/unit/test_group_manager.py | is_operator_in_customer_chat 已删 |
| TC-V5-1.3 | P0 | manual grep | commands/ 含 reply.md / dm.md / join.md / broadcast.md |
| TC-V5-1.4 | P1 | tests/unit/test_router.py | bridge._processed_msg_ids 用 deque(maxlen=10000) |
| TC-V5-1.5 | P1 | tests/unit/test_config_channel_server.py | agent_nick_pattern 字段已移除 |

### Phase 2 — soul.md 对齐（4 TC）

| TC | 优先级 | 文件 | 验证点 |
|----|--------|-----|--------|
| TC-V5-2.1 | P0 | tests/e2e/test_admin_commands_via_cli.py::test_soul_md_only_references_existing_tools | 4 个 soul.md 不含 send_side_message / query_status / query_review / query_squad / assign_agent / reassign_agent |
| TC-V5-2.2 | P0 | 同上 | start.sh 白名单只含 reply / join_channel / run_zchat_cli |
| TC-V5-2.3 | P1 | manual grep | admin-agent soul.md 三命令均通过 run_zchat_cli |
| TC-V5-2.4 | P1 | instructions.md | 列出 3 tool + 提到 __zchat_sys: 注入 |

### Phase 3 — entry_agent + CLI 扩展（6 TC）

| TC | 优先级 | 文件 | 验证点 |
|----|--------|-----|--------|
| TC-V5-3.1 | P0 | tests/unit/test_routing.py | ChannelRoute 加载 entry_agent / bot_id 字段 |
| TC-V5-3.2 | P0 | tests/unit/test_routing.py | 无 entry_agent 字段降级为 None（向后兼容） |
| TC-V5-3.3 | P0 | tests/unit/test_router.py::test_copilot_mode_only_ats_entry_agent | copilot 只发 1 条 IRC（@entry_agent） |
| TC-V5-3.4 | P0 | tests/unit/test_router.py | takeover 不加 @ |
| TC-V5-3.5 | P0 | tests/unit/test_routing_cli.py | --entry-agent --bot-id 写入 routing.toml |
| TC-V5-3.6 | P0 | tests/unit/test_channel_cmd.py | channel remove + set-entry 行为 |

### Phase 4 — CS watch routing.toml（3 TC）

| TC | 优先级 | 文件 | 验证点 |
|----|--------|-----|--------|
| TC-V5-4.1 | P0 | tests/unit/test_routing_watcher.py | mtime 变化触发 reload |
| TC-V5-4.2 | P0 | 同上 | 新增 channel → JOIN；删除 channel → PART |
| TC-V5-4.3 | P1 | 同上 | mtime 不变 → 不 reload；reload 异常不 crash watcher |

### Phase 5 — emit_event IRC sys（3 TC）

| TC | 优先级 | 文件 | 验证点 |
|----|--------|-----|--------|
| TC-V5-5.1 | P0 | tests/unit/test_router.py | emit_event 同时触发 WS + plugin + IRC __zchat_sys: |
| TC-V5-5.2 | P0 | tests/unit/test_agent_mcp.py | sys 消息识别 + 注入 queue（type="sys"） |
| TC-V5-5.3 | P0 | 同上 | sys 不被 detect_mention 误匹配（不死循环） |

### Phase 6 — bridge 去跨层 + lazy create（4 TC）

| TC | 优先级 | 文件 | 验证点 |
|----|--------|-----|--------|
| TC-V5-6.1 | P0 | tests/unit/test_routing_reader.py | 多 bot_id 过滤 + 空文件兜底 |
| TC-V5-6.2 | P0 | tests/e2e/test_bridge_lazy_create.py | bot_added → 两次 subprocess 调用（channel create + agent create） |
| TC-V5-6.3 | P0 | 同上 | disbanded → channel remove --stop-agents |
| TC-V5-6.4 | P0 | grep 红线 | bridge.py 不 import channel_server.* |

### Phase 7 — audit + activation 恢复（4 TC）

| TC | 优先级 | 文件 | 验证点 |
|----|--------|-----|--------|
| TC-V5-7.1 | P0 | tests/unit/test_audit_plugin.py | mode_changed / channel_resolved 入 audit.json |
| TC-V5-7.2 | P0 | 同上 | query("status") / query("report") 返回正确数据 |
| TC-V5-7.3 | P0 | tests/unit/test_activation_plugin.py | 客户在已 resolved channel 发消息 → emit customer_returned |
| TC-V5-7.4 | P0 | __main__.py | 6 plugin 均注册 |

### Phase 8 — audit 仪表盘扩展（4 TC）

| TC | 优先级 | 文件 | 验证点 |
|----|--------|-----|--------|
| TC-V5-8.1 | P0 | tests/unit/test_audit_plugin.py | first_reply / takeover 时间戳跟踪 |
| TC-V5-8.2 | P0 | tests/unit/test_audit_cmd.py | zchat audit status 输出 active channels |
| TC-V5-8.3 | P0 | 同上 | zchat audit report 输出聚合指标（escalation_resolve_rate / csat_mean） |
| TC-V5-8.4 | P0 | tests/e2e/test_admin_commands_via_cli.py | admin-agent 三命令 → CLI 路径正确 |

### Phase 9 — CSAT plugin（4 TC）

| TC | 优先级 | 文件 | 验证点 |
|----|--------|-----|--------|
| TC-V5-9.1 | P0 | tests/unit/test_csat_plugin.py | channel_resolved → emit csat_request |
| TC-V5-9.2 | P0 | 同上 | __csat_score:N → audit.record_csat |
| TC-V5-9.3 | P1 | 同上 | 非数字 score 容错 |
| TC-V5-9.4 | P0 | tests/e2e/test_csat_lifecycle.py | resolve → csat_request → score → audit.json csat_score |

### Phase 10 — sla help timer（5 TC）

| TC | 优先级 | 文件 | 验证点 |
|----|--------|-----|--------|
| TC-V5-10.1 | P0 | tests/unit/test_sla_plugin.py | __side:@operator → 启动 help timer |
| TC-V5-10.2 | P0 | 同上 | __side:@admin / @人工 也触发 |
| TC-V5-10.3 | P0 | 同上 | 非 __side: 内容不触发 |
| TC-V5-10.4 | P0 | 同上 | operator 在 channel 内 __side: → 取消 timer |
| TC-V5-10.5 | P0 | tests/e2e/test_help_request_lifecycle.py | 超时 emit help_timeout event；多 channel 独立 timer |

### Phase 11 — admin-agent 命令（5 TC）

| TC | 优先级 | 文件 | 验证点 |
|----|--------|-----|--------|
| TC-V5-11.1 | P0 | tests/e2e/test_admin_commands_via_cli.py::test_status_command_mapping | /status → audit status 路径 |
| TC-V5-11.2 | P0 | ::test_review_command_mapping | /review → audit report 路径 |
| TC-V5-11.3 | P0 | ::test_dispatch_command_args_parse | /dispatch → agent create 参数解析 |
| TC-V5-11.4 | P0 | ::test_channel_list_command | channel CLI 子命令完整 |
| TC-V5-11.5 | P1 | start.sh 白名单 | 5 个 start.sh 都白名单 reply / join_channel / run_zchat_cli |

## Ralph-loop 静态校验（每 phase 后跑）

```bash
# 红线 1: agent-mcp 无 CS/bridge import
grep -rn "from channel_server\|from feishu_bridge" agent_mcp.py

# 红线 2: bridge 无 CS import
grep -rn "from channel_server" src/feishu_bridge/

# 红线 3: CS 无外部平台业务语义
grep -rE "admin|squad|customer|feishu" src/channel_server/

# 红线 4: routing.toml 写入方
grep -rln "routing.toml" src/  # 确认只有 watcher / reader 读，无写

# 死代码
grep -rE "is_operator_in_customer_chat|agent_nick_pattern|send_side_message|query_status|query_review|query_squad|assign_agent|reassign_agent" src/ tests/ ../zchat/
```

## 总结

- 共 47 unit/e2e TC（不含 ralph-loop 静态校验）
- 全部 P0 优先级，pre-release 阻塞项
- 每 phase 测试落点明确（见上表"文件"列）
- 飞书 SDK 真机部分（spec §6.3）由 pre-release 手动 walkthrough 覆盖，不在本 plan 范围
