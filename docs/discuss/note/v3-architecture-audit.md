# V3 架构审计结论

日期: 2026-04-17

## 三个仓库审计结果

### zchat-protocol（基本干净，2 处需清理）

| 文件 | 状态 | 动作 |
|------|------|------|
| naming.py | ✅ | 保持 |
| sys_messages.py | ✅ | 保持 |
| conversation.py | ✅ | 保持 |
| mode.py | ✅ | 保持 |
| message_types.py | ✅ | 保持 |
| timer.py | ✅ | 保持 |
| participant.py | ✅ | 保持 |
| gate.py | ✅ | 保持（机制级，不可配置） |
| **event.py** | ⚠️ | 删除 `SLA_BREACH`, `SQUAD_ASSIGNED`, `SQUAD_REASSIGNED`（业务事件不属于协议） |
| **commands.py** | ⚠️ | 只保留核心命令 hijack/release/copilot/resolve，移除 squad/review/assign/reassign/dispatch（业务命令由 agent skill 处理） |

### zchat-channel-server（5 个文件需重构）

| 文件 | 状态 | 动作 |
|------|------|------|
| server.py (201行) | ✅ | 保持 |
| transport/ | ✅ | 保持 |
| bridge_api/ws_server.py | ✅ | 保持 |
| engine/event_bus.py | ✅ | 保持 |
| engine/message_store.py | ✅ | 保持 |
| engine/conversation_manager.py | ✅ | 保持 |
| engine/mode_manager.py | ✅ | 保持 |
| engine/timer_manager.py | ✅ | 保持 |
| engine/participant_registry.py | ✅ | 保持 |
| **engine/command_handler.py** | ⚠️ | 拆分：保留 hijack/release/copilot/resolve（协议级）→ 移除 status/dispatch/review/assign/reassign/squad（业务级 → agent skill） |
| **engine/message_router.py** | ⚠️ | 依赖 CommandHandler 拆分后调整 |
| **feishu_bridge/bridge.py** | ⚠️ | 移除 auto-hijack 业务逻辑，简化为纯协议转换 |
| **feishu_bridge/visibility_router.py** | ⚠️ | 拆分：visibility 路由规则 → engine/；card/thread 渲染 → 保留 |
| **plugins/sla_app.py** | ⚠️ | SLA 策略移到 agent skill 配置，不硬编码在 plugin 中 |

### zchat 主库（3 个关键缺失 + 2 处重构）

| 问题 | 影响 | 动作 |
|------|------|------|
| **缺 CustomerManager** | v3 多租户核心 | 新建 zchat/cli/customer_manager.py |
| **缺 customer CLI 命令** | 无法按客户管理 agent | app.py 加 `zchat customer create/delete/list` |
| **缺动态 channel 解析** | channel 列表是静态的 | irc_manager.py + agent_manager.py 改为 per-customer |
| agent_manager.py | ⚠️ | create() 加 customer_id 参数 |
| app.py | ⚠️ | agent create 需要 customer context |

## 核心架构 gap

```
当前:
  Project → AgentManager → Agent（全局 fast-agent/deep-agent）

v3:
  Project → CustomerManager → Customer A → AgentManager-A → fast-agent-A + deep-agent-A
                             → Customer B → AgentManager-B → fast-agent-B + deep-agent-B
```

## 业务/基础设施分离检查

| 类别 | 纯基础设施 | 混合（需拆分） | 纯业务（应在 skill） |
|------|:-:|:-:|:-:|
| channel-server | 15 文件 | 5 文件 | 1 文件（sla_app） |
| zchat-protocol | 8 文件 | 2 文件 | 0 |
| zchat 主库 | 4 文件 | 2 文件 | 0 |

## 执行优先级

### Phase 1: 协议清理（小改，不破坏）
1. zchat-protocol event.py 删除业务事件
2. zchat-protocol commands.py 只保留核心命令
3. channel-server command_handler.py 拆分

### Phase 2: 多租户（大改）
4. zchat 主库新建 customer_manager.py
5. agent_manager.py 加 customer_id
6. 动态 channel 解析
7. CLI customer 子命令

### Phase 3: Bridge 清理
8. bridge.py 移除 auto-hijack
9. visibility_router.py 拆分
10. sla_app.py 移到 skill 配置
