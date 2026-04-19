# zchat Channel Server 规范 v5

> 2026-04-20 · 基于代码现状审阅 + PRD AutoService v1.0 覆盖
>
> 本文档反映**目标状态**。差距见 `docs/discuss/plan/v5-refactor-plan.md`。

## 0. 总则

zchat 把外部客服平台（飞书 / Web / Slack）接入到 IRC 消息总线，让多个 AI agent + 人工 operator 协同工作。

**四个红线：**
1. agent-mcp 不 import CS / bridge 代码
2. bridge 不 import CS 代码（只 import protocol + tomllib）
3. CS / plugin 核心不含任何外部平台业务语义（如 admin/squad/customer 字样）
4. routing.toml 是整个系统唯一的动态运行时持久化；CLI 是唯一写入方

## 1. 组件与连接

```
┌──────────┐
│ 飞书/Web  │  外部平台
└────┬─────┘
     │ 平台 API
┌────▼─────┐
│  Bridge  │  每个外部平台一个 bridge 进程
│          │  依赖：protocol + subprocess CLI
└────┬─────┘
     │ WebSocket (ws_messages)
┌────▼──────────────────────────────┐
│  Channel Server (CS)              │
│  唯一连 IRC 的 WS↔IRC 翻译 + plugin │
│                                   │
│  WSServer / IRCConnection          │
│  Router + RoutingTable(watch)      │
│  PluginRegistry                    │
│    官方 plugin:                    │
│      mode, sla, resolve            │
│      audit, activation, csat       │
└────┬──────────────────────────────┘
     │ IRC (nick: cs-bot)
┌────▼─────┐
│   ergo   │  IRC server（第三方）
└─┬──┬──┬──┘
  │  │  │ IRC
┌─▼─┐┌▼─┐┌▼───────┐
│A0 ││A1││WeeChat │  agent-mcp 直连 IRC（每 agent 一个进程）
│MCP││MCP││        │  MCP Tools: reply / join_channel / run_zchat_cli
│ ↕ ││ ↕││        │  Commands: /zchat:reply /:dm /:join /:broadcast
│CC ││CC││        │  soul.md 定义角色行为
└───┘└──┘└────────┘
```

| 进程 | 数量 | 连接 | 依赖 |
|------|------|------|------|
| ergo | 1 | — | — |
| CS | 1 | IRC（cs-bot）+ WS server | protocol |
| agent-mcp | 每 agent 1 | IRC 直连 + MCP stdio | protocol |
| bridge | 每外部平台 1 | WS client → CS + subprocess CLI | protocol |
| CLI | 一次性 | subprocess | protocol |

## 2. routing.toml — 系统唯一的运行时状态

### 2.1 Schema

```toml
[project]
name = "prod"

# 客户对话 channel
[channels."conv-xxx12345"]
external_chat_id = "oc_客户A"         # 外部平台群 ID（bridge 用）
bot_id = "cli_a1b2c3d4"                # 外部平台 app_id（bridge 过滤自己的用）
entry_agent = "yaosh-fast-xxx"         # router 唯一 @ 的 agent（copilot 模式）
agents = ["yaosh-fast-xxx"]             # channel 里所有 agent（CS JOIN 用）
role_map = { fast = "yaosh-fast-xxx" } # 可选：role → nick

# 客服监管 channel
[channels."squad-001"]
external_chat_id = "oc_客服队"
bot_id = "cli_a1b2c3d4"
entry_agent = "yaosh-squad-0"
agents = ["yaosh-squad-0"]

# 管理 channel
[channels."admin"]
external_chat_id = "oc_管理群"
bot_id = "cli_admin_appid"
entry_agent = "yaosh-admin-0"
agents = ["yaosh-admin-0"]

# 纯 IRC channel（无外部群）
[channels."internal-debug"]
entry_agent = "yaosh-debugger"
agents = ["yaosh-debugger"]
```

### 2.2 字段职责

| 字段 | CS 用 | bridge 用 | CLI 管 |
|------|-------|----------|-------|
| `channel_id` (key) | JOIN `#channel_id` | 不用 | 创建/删除 |
| `entry_agent` | router @ 此 nick | 不用 | 创建时指定 |
| `agents` | JOIN 时的成员预期 | 不用 | agent join 时更新 |
| `external_chat_id` | **不解析** | 双向映射 | 创建时记录 |
| `bot_id` | **不解析** | 过滤属于自己的 channel | 创建时记录 |
| `role_map` | 不用 | 不用 | 辅助查询 |

**CS 对 `external_chat_id` 和 `bot_id` 是透明的**——这两个字段只做存储，router 不查询它们。业务语义完全封装在 bridge。

### 2.3 读写规则

- **写入**：只有 CLI（`zchat channel create / remove / set-entry`、`zchat agent join`）
- **读取**：CS（启动 + file watch reload）、bridge（启动 + 按需 reload，用 `tomllib` 直读）
- **原子写**：CLI 用 tmp + rename（已实现）
- **新增 CLI 命令**：
  - `zchat channel remove <name> [--stop-agents]` —— 删条目 + 可选停 agent 进程
  - `zchat channel set-entry <channel> <nick>` —— 改 entry_agent

## 3. Channel Server 内部

### 3.1 Router — WS↔IRC 翻译核心

**WS → IRC（入站）** `router.forward_inbound_ws`：

```
收到 {type, channel, content, source, message_id?}

if type == "message":
    if content 以 "/" 开头 且有 plugin 注册该命令:
        → plugin.on_command()
        → broadcast_message 给其他 plugin
        → return（不转 IRC）
    else:
        _route_to_irc()
        broadcast_message

if type == "event":
    broadcast_event 给所有 plugin

if type == "register":
    ws_server 层处理（不到 router）

_route_to_irc:
    mode = _query_mode(channel)  # 查 mode plugin，默认 "copilot"
    parsed = irc_encoding.parse(content)
    if parsed.kind == "plain":
        encoded = __msg:<uuid>:<content>
    else:
        encoded = content  # 已有前缀（bridge 或 agent 自己加的）

    entry = routing.entry_agent(channel)
    if mode in ("copilot", "auto") and entry:
        IRC PRIVMSG #channel :@entry encoded
    elif mode == "takeover":
        IRC PRIVMSG #channel :encoded  # 不加 @
    else:
        log warning（无 entry_agent 或无 channel）
```

**IRC → WS（出站）** `router.forward_inbound_irc`：

```
收到 channel, nick, body

parsed = irc_encoding.parse(body)
if parsed.text 以 "/" 开头 且有 plugin 注册:
    plugin.on_command()
    broadcast_message
    return（不 WS broadcast）

ws_msg = build_message(channel, source=nick, content=body, message_id=parsed.message_id)
ws_server.broadcast(ws_msg)
broadcast_message(ws_msg)
```

**emit_event（CS 内部事件 → 三路广播）**：

```
1. ws_server.broadcast(build_event)      → bridge 收到 WS event
2. plugin_registry.broadcast_event       → plugin 订阅
3. IRC PRIVMSG #channel :__zchat_sys:{...}  → agent 感知
```

### 3.2 Mode 精确行为

| mode | router 行为 | agent 能否收到外部消息 |
|------|-----------|--------------------|
| copilot（默认） | `@entry_agent <encoded>` | 能 |
| takeover | `<encoded>`（不加 @） | 不能 |
| auto | 同 copilot | 能 |

`mode_changed` 事件通过 `__zchat_sys:` 消息通知 agent，agent 由 soul.md 指导后续行为（takeover 后主要发 side 建议 / 整理 context）。

### 3.3 RoutingTable 动态 reload

CS 启动后 watch `routing.toml` 文件 mtime（每 2 秒检查）：

- 检测到变化 → `load()` 新表 → `router.update_routing(new_routing)`
- 新增 channel → `irc_conn.join(#name)`
- 删除 channel → `irc_conn.part(#name)`
- 已有 channel 字段变化（entry_agent 等）→ 下条消息按新表路由

### 3.4 Plugin 框架

```python
class Plugin(Protocol):
    name: str
    def handles_commands() -> list[str]
    async def on_ws_message(msg) -> None
    async def on_ws_event(event) -> None
    async def on_command(cmd, msg) -> None
    def query(key, args) -> Any
```

- 命令冲突注册时抛 ValueError
- `broadcast_message` / `broadcast_event` 容错
- plugin 通过构造注入 `emit_event` / `emit_command` callback 主动发消息

## 4. 官方 Plugin（按能力层分组）

### 4.1 路由行为层（影响消息流转）

**mode** — 模式状态

| 项 | 值 |
|---|---|
| commands | `hijack` `release` `copilot` |
| query | `"get"(channel)` → mode |
| emit | `mode_changed {from, to, triggered_by, cmd}` |

**sla** — SLA timer

| 项 | 值 |
|---|---|
| 订阅 | `mode_changed`（takeover）、`on_ws_message`（side 求助检测） |
| timer 1：takeover 超时 | to=takeover → 启动 180s；超时 emit `sla_breach` + 发 `/release` |
| timer 2：求助等待 | 检测 `__side:` 内容含 `@operator` 或 `@人工`/`@admin` → 启动 180s；超时 emit `help_timeout` + 通知 agent 发安抚消息 |

**resolve** — 对话结束

| 项 | 值 |
|---|---|
| commands | `resolve` |
| emit | `channel_resolved {resolved_by, timestamp}` |

### 4.2 数据层（运行时统计 + 业务数据持久化）

**audit** — 运营数据统计

| 项 | 值 |
|---|---|
| 持久化 | `audit.json`（项目目录下） |
| 订阅 | `mode_changed`、`channel_resolved`、`on_ws_message`（记录时间戳）|
| 跟踪 | per-channel 状态（active/takeover/resolved）、takeover 次数、takeover→resolve 配对（升级转结案率）、每 channel 首次回复时间、会话时长、接单等待 |
| query | `status()` → 全局统计；`status(channel)` → 单 channel 状态；`history()` → 最近事件 |
| CLI 暴露 | `zchat audit status` / `zchat audit report [--channel X]` / `zchat audit export --format json` |

audit 数据结构（示例）：

```json
{
  "channels": {
    "conv-xxx": {
      "state": "active",
      "created_at": "2026-04-20T10:00:00Z",
      "first_reply_at": "2026-04-20T10:00:03Z",
      "takeovers": [
        {"at": "2026-04-20T10:15:00Z", "triggered_by": "operator", "released_at": "2026-04-20T10:17:00Z", "released_by": "operator"}
      ],
      "resolved_at": null,
      "message_count": 24,
      "csat_score": null
    }
  },
  "aggregates": {
    "total_takeovers": 42,
    "total_resolved": 38,
    "escalation_resolve_rate": 0.89
  }
}
```

**activation** — 客户回访检测

| 项 | 值 |
|---|---|
| 持久化 | `activation-state.json` |
| 订阅 | `on_ws_message` → 更新 last_activity；`channel_resolved` → 标记 last_closed |
| emit | 客户在已关闭 channel 发言 → `customer_returned` event |
| query | `last_activity(channel)` / `last_closed(channel)` / `is_dormant(channel)` |

**csat** — 客户满意度

| 项 | 值 |
|---|---|
| 持久化 | 数据存 audit.json 里对应 channel 的 `csat_score` |
| 订阅 | `channel_resolved` → 发 WS message `{type:"csat_request", channel:conv_id}` 触发 bridge 发评分卡片 |
| 订阅 | `on_ws_message` 检测 `content == "__csat_score:N"`（bridge 从 card action 转发回来的）→ 记录分数 → emit `csat_recorded` event |
| 事件流 | resolve → bridge 发评分卡片 → 客户评分 → card.action → bridge 转发 WS → CSAT plugin 入库 |

## 5. IRC 消息前缀

| 前缀 | 格式 | 谁产生 | bridge 渲染 |
|------|------|-------|-----------|
| `__msg:` | `__msg:<uuid>:<text>` | agent reply / router 自动包装入站 plain | 客户群发送 + 客服群镜像到该 conv 卡片 thread |
| `__edit:` | `__edit:<uuid>:<text>` | agent reply(edit_of=uuid) | 客户群 update_message + 客服群 thread 标 [edited] |
| `__side:` | `__side:<text>` | agent reply(side=true) / bridge 把 operator thread 回复加前缀 | **仅客服群 thread**（客户不可见） |
| `__zchat_sys:` | `__zchat_sys:<json>` | router.emit_event | 不发外部；bridge 可监听更新 UI |
| plain | `<text>` | — | 客户群发送（同 `__msg:`） |

## 6. 飞书 UI ↔ IRC channel（bridge 业务）

### 6.1 双层映射

**CS 层 routing.toml**：channel_id ↔ external_chat_id（1:1，扁平的路由表）

**bridge 层业务配置**（bridge 自己的 config.yaml 或内存）：

```yaml
supervision:
  squad-001:             # 客服 IRC channel
    supervises:          # 监管哪些客户 IRC channel
      - conv-001
      - conv-002
```

### 6.2 bridge 的入站路由

```
飞书消息 chat_id 对应 #conv-xxx:
  普通 → __msg:... → WS → #conv-xxx
  (无 thread 概念)

飞书消息 chat_id 对应 #squad-xxx:
  普通发言（不在 thread 里）→ __msg:... → WS → #squad-xxx（operator ↔ squad-agent 正常对话）
  在客户会话卡片的 thread 里回复:
    bridge 从卡片 value 得知对应 conv-xxx
    → 加 __side: → WS → #conv-xxx
    （operator 给 conv-xxx 的 agent 的建议）
```

### 6.3 bridge 的出站路由

```
#conv-xxx 的消息 WS 广播到 bridge:
  kind=msg → 客户群 send_text + 客服群对应卡片 thread 镜像
  kind=edit → 客户群 update_message + 客服群 thread 标 [edited]
  kind=side → 仅客服群对应卡片 thread
  kind=sys → 不发外部；bridge 按 sys event 类型更新 UI
              mode_changed → 更新客服群卡片状态（copilot/takeover）
              channel_resolved → 更新客服群卡片状态（已结案）

#squad-xxx 的消息 WS 广播到 bridge:
  kind=msg → 客服群直接发送（不挂卡片 thread）

csat_request 事件 WS 广播:
  bridge 向 conv-xxx 对应的客户群发评分卡片

sla_breach / help_timeout 事件 WS 广播:
  bridge 可选：在客服群对应卡片发告警（不是 PRD 硬性需求）
```

## 7. Agent-MCP

### 7.1 MCP Tools

| Tool | 参数 | 行为 |
|------|-----|------|
| `reply` | chat_id, text, edit_of?, side? | 按 edit_of/side 加前缀，IRC PRIVMSG |
| `join_channel` | channel_name | IRC JOIN `#channel_name` |
| `run_zchat_cli` | args[], timeout? | subprocess `zchat <args>` |

### 7.2 消息注入逻辑

```
IRC _on_pubmsg(body):
  parsed = irc_encoding.parse(body)
  if parsed.kind == "sys":
    inject as system event（让 Claude 知道 mode_changed 等）
    return
  if detect_mention(body, AGENT_NAME):
    clean = clean_mention(body)
    inject as regular message
  else:
    ignore
```

### 7.3 Claude Code Plugin 文件

start.sh 从 `zchat-channel-server/` 复制到 workspace：

```
workspace/
├── .claude-plugin/plugin.json
├── commands/
│   ├── reply.md         /zchat:reply -c X -t Y
│   ├── dm.md            /zchat:dm -u N -t Y
│   ├── join.md          /zchat:join -c X
│   └── broadcast.md     /zchat:broadcast -t Y
├── instructions.md       agent system prompt
└── soul.md              角色行为（从 templates/<type>/soul.md 复制）
```

### 7.4 Agent 间协同

fast-agent 委托 deep-agent / 求助 operator，都用 **side + @mention**：

```
reply(chat_id="#conv-001", text="@deep-agent 查询订单 #12345", side=true)
  → __side:@deep-agent 查询订单 #12345
  → deep-agent 检测 @mention → 处理
  → bridge: kind=side → 仅客服群 thread（operator 能看到协作）

reply(chat_id="#conv-001", text="@operator 这个问题需要您确认", side=true)
  → __side:@operator 这个问题需要您确认
  → sla plugin 检测到 @operator → 启动 180s 求助 timer
  → bridge: kind=side → 客服群 thread（operator 看到）
  → 超时 operator 没回复 → sla emit help_timeout event + agent 感知 → agent 发安抚消息
```

## 8. 命令分类

### 8.1 Plugin 拦截的命令

| 命令 | Plugin |
|------|-------|
| `/hijack` `/release` `/copilot` | mode |
| `/resolve` | resolve |

CS 收到这些命令直接分派给 plugin，**不转发 IRC**。

### 8.2 Plugin 不拦截的命令（由 agent 处理）

| 命令 | 处理者 | 实现 |
|------|-------|------|
| `/status` | admin-agent | `run_zchat_cli(["audit", "status"])` → reply 结果 |
| `/review` | admin-agent | `run_zchat_cli(["audit", "report"])` → reply 结果 |
| `/dispatch <agent-type> <channel>` | admin-agent | `run_zchat_cli(["agent", "create", ..., "--channel", ch])` |

CS 无 plugin handler → router 当普通消息，包装 `__msg:` → `@entry_agent`（admin channel 的 entry 是 admin-agent）→ admin-agent 按 soul.md 解析处理。

## 9. PRD 场景对齐（本次重构覆盖）

| PRD US | 核心需求 | 实现方式 | 状态 |
|--------|---------|---------|------|
| US-2.1 | 3 秒问候 | bridge 收消息 → CS @ entry_agent → agent 回复 | 架构支持 |
| US-2.2 | 占位 + 编辑 | `__msg:<uuid>` 占位 + `__edit:<uuid>` 替换 | 架构支持 |
| US-2.3 | 客服群卡片 + thread 镜像 | bridge 首消息发卡 + 后续 reply_in_thread | bridge 已实现（保留现状）|
| US-2.4 | 草稿模式 | **不做**（未来可通过 soul.md 调整）| 跳过 |
| US-2.5 | Agent @人求助 + 180s timer | side + @operator/@人 → sla plugin 求助 timer | 本次做 |
| US-2.5 | operator /hijack 抢单 | mode plugin | 已实现 |
| US-2.6 | 角色翻转 + context 带入 | mode plugin（已实现）；context 带入通过 operator soul.md 工作流 | 后续 |
| US-3.1 | 双账本仪表盘 | audit plugin 扩展跟踪 6 指标 + 可选 web 仪表盘 | 本次做（数据层） |
| US-3.2 | /status /dispatch /review | admin-agent soul.md + run_zchat_cli + audit CLI | 本次做 |
| US-3.3 | 5 分钟滚动平均告警 | **不做** | 跳过 |
| CSAT | 评分链路 | csat plugin + bridge 卡片 | 本次做 |
| 老客户回访 | channel 活跃度检测 | activation plugin | 本次做 |

## 10. 完整消息流转（关键场景）

### 10.1 新飞书群 → 懒创建

```
bot_added(oc_xxx)
  → bridge subprocess:
       zchat channel create conv-xxx --external-chat oc_xxx --bot-id <self.app_id>
       zchat agent create fast-xxx --type fast-agent --channel conv-xxx --entry
  → CLI 写 routing.toml（含 entry_agent）
  → CS watch 2s 内 reload → IRC JOIN #conv-xxx
  → agent 启动 → IRC JOIN #conv-xxx
  → 就绪
```

### 10.2 客户消息 → agent 回复

```
客户在 oc_xxx 发 "你好"
  → bridge tomllib 读 routing.toml 过滤 bot_id → 找到 conv-xxx
  → WS: {channel:"conv-xxx", content:"你好"}
  → CS router: copilot mode + entry_agent=fast-xxx
  → IRC #conv-xxx :@fast-xxx __msg:<uuid>:你好
  → fast-agent 收到 → reply(text="您好！")
  → IRC #conv-xxx :__msg:<uuid2>:您好！
  → CS → WS broadcast
  → bridge: kind=msg → 客户群 send_text + 客服群 thread 镜像
```

### 10.3 复杂查询（US-2.2）

```
客户发复杂问题 → fast-agent 收到
fast-agent:
  reply(text="稍等...") → __msg:uuid-100 → 客户群 + 客服群 thread
  reply(text="@deep-agent 请查", side=true) → __side: → 仅客服群 thread
    → deep-agent 检测 @mention → 处理
deep-agent:
  reply(text="已发货", edit_of="uuid-100") → __edit:uuid-100
    → 客户群 update_message + 客服群 thread 标 [edited]
```

### 10.4 Agent 求助 operator（US-2.5）

```
fast-agent 遇到处理不了:
  reply(text="@operator 此问题需要您确认：...", side=true)
  → __side:@operator ...
  → bridge: side → 客服群 thread
  → sla plugin 检测到 side 中的 @operator → 启动 180s 求助 timer

情况 A：operator 180s 内回复
  → operator 在客服群 thread 写建议 → bridge 加 __side: → #conv-xxx
  → sla plugin 检测到该 channel 内 operator 的 __side: → cancel timer
  → agent 采纳建议

情况 B：180s 超时
  → sla emit help_timeout event
  → 发 __zchat_sys: help_timeout → agent 感知
  → agent 按 soul.md 向客户发安抚消息：reply(text="抱歉让您久等...")
  → bridge 可选：客服群卡片高亮 "求助超时"
```

### 10.5 人工接管（US-2.5 /hijack 路径）

```
operator 点客服群卡片"接管"按钮
  → bridge card.action.trigger → WS: {channel:"conv-xxx", content:"/hijack"}
  → CS router: "/" → mode plugin
     mode[conv-xxx] = takeover
     emit_event("mode_changed", {from:copilot, to:takeover})
       → WS broadcast → bridge 更新客服群卡片 UI
       → plugin broadcast → sla plugin 启动 takeover timer（180s 自动 release）
       → plugin broadcast → audit plugin 记录 takeover 次数 + 时间戳
       → IRC __zchat_sys:mode_changed → fast-agent 感知

客户继续发消息 → CS takeover 模式不加 @ → agent 收不到（但 bridge 仍镜像到客服群）
operator 直接回复客户 → bridge → WS → CS takeover 不加 @ → IRC → bridge 广播 → 客户群
agent 根据 soul.md 通过 __side: 提供副驾驶建议

180s 内 operator 未回复:
  sla 超时 → emit sla_breach event（bridge 可选告警）+ 发 /release → mode plugin → copilot
  → agent 恢复
```

### 10.6 对话结束 + CSAT（US-3.1 CSAT 指标）

```
/resolve（operator 点"结案"按钮或手动）
  → resolve plugin → emit channel_resolved
     → audit plugin 记录 resolved_at + 升级转结案配对
     → activation plugin 标记 last_closed
     → csat plugin 订阅到 → 发 WS: {type:"csat_request", channel:"conv-xxx"}

bridge 收到 csat_request
  → sender.send_card(客户群, csat_card(conv_id))
  → 客户群出现 5 星评分卡片

客户点击 4 星
  → bridge card.action.trigger → WS: {channel:"conv-xxx", content:"__csat_score:4"}
  → CS router: __side:/非 / 命令 → broadcast_message
  → csat plugin on_ws_message 检测 "__csat_score:" → 记录分数到 audit.json
  → emit csat_recorded event
  → bridge 可选：向客户群发"感谢您的评价"
```

### 10.7 管理命令（US-3.2）

```
admin 发 "/status" 在飞书管理群
  → bridge → WS: {channel:"admin", content:"/status"}
  → CS router: "/" 无 plugin handler → 当普通消息 → 包装 __msg: → @admin-agent → IRC
  → admin-agent 收到 → soul.md 指导:
     run_zchat_cli(["audit", "status"])
     → CLI 读 audit.json → 返回所有 active channel 列表
     → reply(text=格式化结果)
  → IRC → CS → WS → bridge → 飞书管理群

admin 发 "/dispatch deep-agent conv-xxx"
  → 同路径 → admin-agent
  → run_zchat_cli(["agent", "create", "deep-xxx", "--type", "deep-agent", "--channel", "conv-xxx"])
  → CLI 启动 agent + 更新 routing.toml
  → CS watch reload → deep-xxx 加入 #conv-xxx

admin 发 "/review"
  → admin-agent
  → run_zchat_cli(["audit", "report"])
  → 返回昨日统计：takeover 次数 / CSAT 均分 / 升级转结案率 / SLA 达成率
```

### 10.8 老客户回访

```
客户在已 resolve 的 oc_xxx 发新消息
  → bridge → WS → CS
  → activation plugin on_ws_message 检测 channel state == resolved
     → emit customer_returned event
  → bridge / admin-agent 决定策略（本次不指定，留给 plugin/bridge 扩展）
```

## 10.9 飞书 SDK 集成要求

**Bridge 必须通过飞书真机验证的能力（pre-release 阻塞项）：**

### 连接层

- `lark_oapi.Client` 凭证加载成功（app_id + app_secret）
- WSS 长连接稳定：`CardAwareClient` 启动后持续保持
- 断线自动重连（网络恢复后 bridge 能重新接收事件）

### 事件订阅（6 种）

| 事件 | bridge handler | 测试场景 |
|------|---------------|---------|
| `im.message.receive_v1` | `_on_message` | 飞书发消息 → bridge 收到 |
| `im.chat.member.bot.added_v1` | `_on_bot_added` | 拉 bot 进群 → 懒创建触发 |
| `im.chat.member.user.added_v1` | `_on_user_added` | 人加入 → 权限更新 |
| `im.chat.member.user.deleted_v1` | `_on_user_deleted` | 人退出 → 权限撤销 |
| `im.chat.disbanded_v1` | `_on_disbanded` | 群解散 → channel remove |
| `card.action.trigger` | `_on_card_action` | 卡片按钮点击 → WS 消息 |

### API 调用（5 种）

| API | 用途 | 验证点 |
|-----|-----|-------|
| `im.v1.message.create` (send_text) | 发公开消息 | 客户群看到消息 |
| `im.v1.message.create` (send_card) | 发 interactive card | 卡片正确渲染 |
| `im.v1.message.patch` (update_message) | 编辑消息 | 客户看到内容变化 |
| `im.v1.message.reply` (reply_in_thread) | thread 回复 | 客服群 thread 镜像 |
| `im.v1.message.patch` (update_card) | 更新卡片 | 卡片 UI 刷新 |

### UI 渲染

- `build_conv_card` 生成的卡片含正确的 title/mode/按钮
- `csat_card` 5 星按钮可点击
- mode 变化时卡片 UI 刷新（takeover 状态可见）
- resolve 时卡片切到已结案状态

## 11. 扩展原则

**PRD 剩余未实现功能都通过 plugin 扩展，不改核心。**

| 未实现功能 | 未来 plugin |
|----------|-----------|
| 实时卡片刷新（US-2.3 强化）| bridge 业务或 summary-plugin |
| Dream Engine | dream-plugin |
| 知识库 RAG | kb-plugin（query 接口给 agent） |
| 合规预检 | compliance-plugin |
| 5min 滚动平均告警（US-3.3）| metrics-plugin |

## 12. 代码依赖（严格单向）

```
zchat-protocol ← 所有人 import（Layer 0）

CS core
  import: protocol
  不 import: bridge / agent-mcp / CLI

plugins (mode/sla/resolve/audit/activation/csat)
  import: CS plugin.BasePlugin + protocol
  不 import: bridge / agent-mcp / CLI

agent-mcp
  import: protocol
  IRC 直连
  不 import: CS / bridge / CLI

bridge
  import: protocol + tomllib
  WS 连 CS
  subprocess 调 CLI（运行时）
  不 import: CS / agent-mcp

CLI
  import: protocol
  写 routing.toml / 启停 agent 进程
  不 import: CS / bridge / agent-mcp
```

Ralph-loop 每 Phase 后验证：
- `grep "channel_server" src/feishu_bridge/` 无匹配
- `grep "feishu_bridge" src/channel_server/` 无匹配
- 没有死代码（删除后的符号再没人 import）
- routing.toml 写入方只有 CLI
