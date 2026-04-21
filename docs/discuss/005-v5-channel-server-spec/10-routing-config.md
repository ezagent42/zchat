# Channel-Server v1.0 — Routing 配置规范

> Agent 编排策略的外部配置 + channel-server 执行逻辑
> 基于架构决策 #6（Agent 编排 = 外部配置 + channel-server 执行）

---

## 1. 设计原则

编排策略在**外部配置文件**（routing.toml），不在 channel-server 代码里，也不在 soul.md 里。channel-server 只负责**读取配置并执行**。

- v1.0: routing.toml 定义 default_agents + escalation_chain + available_agents
- v1.0: agent 之间通过 IRC side message + @mention 自由协作（channel-server 不干预）
- v1.1: 新增 [pipeline] 段，channel-server 拦截消息按配置顺序路由

---

## 2. 配置格式

```toml
# routing.toml — channel-server 启动时加载

[routing]
# 新 conversation 创建时自动 dispatch 的 agent 列表（按顺序 JOIN #conv-{id}）
default_agents = ["fast-agent"]

# 收到 escalation event 时按顺序尝试 dispatch
# "operator" 表示通知 operator（通过 squad群 告警）
escalation_chain = ["deep-agent", "operator"]

# /dispatch 命令的白名单（只有在此列表中的 agent 才允许被 dispatch）
available_agents = ["fast-agent", "deep-agent", "translation-agent", "audit-agent"]

# --- v1.1 预留 ---
# [pipeline]
# incoming = ["translation-agent", "fast-agent"]   # 入站管线
# outgoing = ["translation-agent"]                  # 出站管线
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `default_agents` | `list[str]` | 是 | 新 conversation 自动 dispatch 的 agent nick 列表 |
| `escalation_chain` | `list[str]` | 否 | escalation event 时的 dispatch 顺序。`"operator"` 是特殊值，表示通知 operator |
| `available_agents` | `list[str]` | 否 | `/dispatch` 命令的白名单。未配置时允许所有已注册 agent |

---

## 3. channel-server 加载行为

### 启动时加载

```python
# server.py main() 中:
routing_config = load_routing_config(config.get("routing_config_path", "routing.toml"))

# 如果 routing.toml 不存在，使用默认值:
# default_agents = []
# escalation_chain = []
# available_agents = []（表示不限制）
```

**配置路径优先级**:
1. 环境变量 `ROUTING_CONFIG=/path/to/routing.toml`
2. config.toml 中的 `[channel_server] routing_config = "routing.toml"`
3. 默认: 当前工作目录下的 `routing.toml`

### 热加载（v1.0 不支持）

v1.0 不支持运行时重新加载 routing.toml。修改配置后需重启 channel-server。

---

## 4. Auto-dispatch 执行逻辑

### 新 conversation 创建时

```python
async def _on_conversation_created(self, event: Event):
    conv_id = event.conversation_id
    for agent_nick in self.routing_config.default_agents:
        # 验证 agent 是否在线（IRC WHOIS 或 ParticipantRegistry）
        if self.participant_registry.is_online(agent_nick):
            # 让 agent JOIN #conv-{id}
            self._dispatch_agent(conv_id, agent_nick)
        else:
            log.warning(f"Default agent {agent_nick} offline, skipping")
```

**行为**:
- 按 `default_agents` 列表顺序依次 dispatch
- agent 不在线时跳过（记录警告），不阻塞后续 agent
- dispatch = 向 IRC 发送系统消息通知 agent JOIN 对应频道

### Escalation event 处理

```python
async def _on_escalation(self, event: Event):
    conv_id = event.conversation_id
    for target in self.routing_config.escalation_chain:
        if target == "operator":
            # 通知 operator: 通过 Bridge API 发告警到 squad群
            await self.bridge_api.send_event(conv_id, {
                "type": "escalation",
                "conversation_id": conv_id,
                "message": f"Agent 请求人工协助: {event.data.get('reason', '')}"
            })
            break
        else:
            # dispatch agent
            if self.participant_registry.is_online(target):
                self._dispatch_agent(conv_id, target)
                break
            # agent 不在线，尝试下一个
            log.warning(f"Escalation target {target} offline, trying next")
```

**行为**:
- 按 `escalation_chain` 顺序尝试
- 找到第一个可用目标后 dispatch 并停止（不会同时 dispatch 多个）
- `"operator"` 是特殊值：不 dispatch agent，而是通过 Bridge API 通知 operator
- 所有目标都不可用时，记录错误日志 + 发 system 消息到 #admin

### Escalation event 的触发方式

agent 通过 IRC 发送带特殊前缀的消息触发 escalation:
```
PRIVMSG #conv-xxx :__escalation:reason text here
```

channel-server IRC bot 解析 `__escalation:` 前缀 → 发布 EventBus escalation event → 执行 escalation_chain。

---

## 5. /dispatch 白名单验证

```python
async def _handle_dispatch(self, conv_id: str, agent_nick: str, admin_id: str):
    # 白名单验证
    if self.routing_config.available_agents:
        if agent_nick not in self.routing_config.available_agents:
            return f"Agent {agent_nick} 不在可用列表中。可用: {', '.join(self.routing_config.available_agents)}"
    
    # 验证 agent 在线
    if not self.participant_registry.is_online(agent_nick):
        return f"Agent {agent_nick} 当前离线"
    
    # dispatch
    self._dispatch_agent(conv_id, agent_nick)
    return f"已 dispatch {agent_nick} 到 {conv_id}"
```

**行为**:
- `available_agents` 为空列表时不限制（允许所有已注册 agent）
- agent 不在线时返回错误消息，不 dispatch
- 成功 dispatch 后发出 `agent.dispatched` event

---

## 6. v1.1 Pipeline 升级路径

v1.0 的 pipeline 接力逻辑分散在各 agent soul.md 中（agent 自行 @mention 下一个）。v1.1 将 pipeline 逻辑提升到 channel-server：

```toml
# v1.1 routing.toml 新增
[pipeline]
incoming = ["translation-agent", "fast-agent"]   # 入站管线
outgoing = ["translation-agent"]                  # 出站管线
```

**v1.1 行为变化**:
- channel-server 拦截入站客户消息，按 `incoming` 顺序依次路由给每个 agent
- 每个 agent 处理完后回复，channel-server 将结果传递给下一个
- 出站（agent → 客户）同理，按 `outgoing` 顺序过滤
- agent 不需要知道"下一个是谁"——channel-server 控制流转

**Socialwares 编译器**: Socialwares compiler 可从 `socialware.py` 的 Flow 定义编译出 pipeline 配置段，自动生成 routing.toml。

**v1.0 → v1.1 迁移**: 只需在 routing.toml 中添加 `[pipeline]` 段，channel-server 自动启用 pipeline 模式。现有 `[routing]` 段保持兼容。

---

*End of Routing Config Spec v1.0*
