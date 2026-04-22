# 001 · zchat 架构总览

> 从外部 IM 到 agent 内部消息流，每个模块负责什么、消息怎么走。

## 1. 三层视角

```
┌──────────────────────────────────────────────────────────────────────┐
│                    外部 IM 平台（飞书 / Slack / ...）                   │
│   用户/客户/operator 在群里发消息、点卡片按钮                           │
└────────────────────┬───────────────────────────┬─────────────────────┘
                     │ WSS 长连接 / Webhook       │ REST API
                     ▼                           ▲
┌──────────────────────────────────────────────────────────────────────┐
│                      bridge 层（业务平台适配）                          │
│   feishu_bridge / slack_bridge / discord_bridge ...                  │
│   职责：平台事件 ↔ zchat WS 协议互译；本层允许业务语义                    │
└────────────────────┬───────────────────────────┬─────────────────────┘
                     │ WS (ws_messages 协议)      │ WS broadcast/event
                     ▼                           ▲
┌──────────────────────────────────────────────────────────────────────┐
│              channel-server (CS) — 中性消息总线                       │
│   ┌──────────┐  ┌──────────┐  ┌────────┐  ┌─────────────────┐        │
│   │ ws_server│→ │  router  │→ │ plugins│  │ irc_connection  │        │
│   │  (注册   │  │ (entry @ │  │ (mode/ │←→│ (PRIVMSG + NAMES│        │
│   │   bridge)│  │ NAMES熔断)│  │ sla/   │  │  缓存 + reactor)│        │
│   └──────────┘  └──────────┘  │ csat/..│  └─────────────────┘        │
│                                └────────┘                            │
│   核心红线：本层不写业务名（customer/operator/feishu 等）                  │
└────────────────────┬───────────────────────────┬─────────────────────┘
                     │ IRC PRIVMSG (含前缀)        │
                     ▼                           ▲
┌──────────────────────────────────────────────────────────────────────┐
│                     IRC server (ergo)                                │
│   纯 IRC 协议中转 — channel JOIN/PART, PRIVMSG, NAMES                  │
│   zchat 自带 ergo 子进程，也可指向外部 IRC                              │
└────────────────────┬─────────────────────────────────────────────────┘
                     │ IRC client (irc lib)
                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│            agent (Claude Code session × N) + agent_mcp               │
│   每个 agent = 1 个 Claude Code 进程 + 1 个 zchat-agent-mcp stdio     │
│   ┌─────────────────────┐    ┌────────────────────────────────────┐  │
│   │ Claude Code         │←───│ agent_mcp (stdio MCP server)       │  │
│   │  - CLAUDE.md (人格)│    │  - 收 IRC 消息 → 注入为 user msg   │  │
│   │  - .claude/skills/ │    │  - 暴露 tools: reply / list_peers /│  │
│   │  - settings.local  │ → │    join_channel / run_zchat_cli    │  │
│   └─────────────────────┘    │  - 维护本 agent IRC 长连接          │  │
│                              └────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
                     ▲
                     │ tmux/zellij sessions（不是消息层，仅进程编排）
┌────────────────────┴─────────────────────────────────────────────────┐
│           zchat CLI（zchat/cli/） — orchestration                     │
│   zchat up/down/agent/channel/bot/audit/project/...                  │
│   写 routing.toml；起 ergo + WeeChat + CS + bridges + agents 子进程   │
└──────────────────────────────────────────────────────────────────────┘
```

## 2. 一条消息的完整生命周期（客户群发问 → agent 回复）

```
1. 飞书客户在 cs-customer 群发: "你好，发货时间多久"
   │
2. customer bridge (feishu_bridge) 收 WSS event im.message.receive_v1
   │ - chat_id → channel_id 映射查询 (ChannelMapper)
   │ - 首次见此 chat_id 时调 get_chat_info 拉群名 → emit chat_info event
   │
3. bridge 通过 WS 发 ws_messages.build_message(channel="conv-001",
                                               source="ou_xxxx",
                                               content="你好，发货时间多久")
   │
4. CS ws_server 收到 → forward_inbound_ws → router._handle_message
   │
5. router:
   │ - 包装为 IRC 编码: __msg:<uuid>:你好，发货时间多久
   │ - 查 mode plugin (copilot/takeover) → copilot 模式
   │ - 查 routing.toml entry_agent → "yaosh-fast-001"
   │ - check IRC NAMES：fast-001 是否在 #conv-001 → 在
   │ - irc_connection.privmsg("#conv-001", "@yaosh-fast-001 __msg:...")
   │ - 同时 plugin_registry.broadcast_message(msg) → 所有 plugin 订阅 (audit/csat/sla...)
   │   （注：plugin 是 in-process 订阅，不走 WS；bridge 入站的 msg 不回广播给 WS）
   │
6. ergo IRC server 转发 PRIVMSG 给 #conv-001 channel
   │
7. yaosh-fast-001 的 agent_mcp（在 IRC reactor 线程）收到 PRIVMSG
   │ - 检测到 @yaosh-fast-001 前缀 → mention
   │ - 解析 __msg:<uuid>:<text>
   │ - 通过 stdio 注入 Claude Code 为 user message
   │
8. Claude Code 处理：
   │ - 读 CLAUDE.md (persona)
   │ - 按 message description 自动加载相关 SKILL.md
   │   ("发货时间" 是 FAQ → 直接 reply，无需 delegate-to-deep)
   │ - 调 reply tool: reply(chat_id="#conv-001", text="您好，发货时间是...")
   │
9. agent_mcp 收 reply tool call:
   │ - 编码为 __msg:<new_uuid>:您好，发货时间是...
   │ - irc_connection.privmsg("#conv-001", "__msg:...")
   │
10. ergo 转发 PRIVMSG → CS irc_connection on_pubmsg → router.forward_inbound_irc
    │ - ws_server.broadcast → 所有 bridge 订阅
    │ - plugin_registry.broadcast_message → 所有 plugin 订阅
    │
11. customer bridge 收 WS message (kind=msg) → outbound.route → 
    │ sender.send_text(customer_chat_id, "您好，发货时间是...")
    │
12. 飞书客户群显示 bot 回复 ✓

并行: squad bridge 同样收到此 WS message，但 channel="conv-001" 不在自己 own
但在 supervises 列表 → _handle_supervised_message → 在 cs-squad 群的 conv-001
卡片 thread 内镜像这条 [AI] 您好，发货时间是...
```

## 3. 各模块职责速查

### CLI 层 `zchat/cli/`

| 模块 | 职责 |
|---|---|
| `app.py` | Typer 根 + 全部子命令（`up/down/agent/channel/bot/audit/project/...`） |
| `agent_manager.py` | Agent lifecycle：create/stop/restart + workspace + zellij tab + ready marker |
| `irc_manager.py` | ergo daemon 进程管理 + WeeChat zellij tab 启停 + SASL auth |
| `routing.py` | routing.toml 读写 (V6 schema: bots + channels + entry_agent) |
| `project.py` | project CRUD + paths + global config |
| `zellij.py` | zellij subprocess 封装 + KDL layout 生成 |
| `runner.py` | template 解析 + env 渲染（agent 启动） |
| `template_loader.py` | template 列表 + 内置 5 个 template 加载 |
| `auth.py` | OIDC device-code flow + SASL token |
| `doctor.py` | 环境依赖诊断 |

### channel-server `zchat-channel-server/src/channel_server/`

| 模块 | 职责 |
|---|---|
| `__main__.py` | CS 进程入口：起 IRC reactor + WS server + 注册 plugin |
| `router.py` | 中枢路由：IRC ↔ WS 双向翻译 + 命令 (`/`) 分派 + NAMES 熔断 + emit_event 三路广播 |
| `irc_connection.py` | IRC 长连接：PRIVMSG 发送 + NAMES/JOIN/PART/QUIT/NICK 维护成员缓存 |
| `ws_server.py` | bridge ↔ CS WebSocket server (注册 + 双向消息) |
| `routing.py` | routing.toml 加载 + watch reload + RoutingTable 查询（CS 端 only） |
| `plugin.py` | PluginRegistry：plugin 注册 + 命令分派 + 事件 broadcast |

### channel-server bridge 层 `feishu_bridge/`

| 模块 | 职责 |
|---|---|
| `bridge.py` | 飞书 WSS 事件入站 + 出站消息 dispatch + supervise 卡片+thread 镜像 |
| `outbound.py` | 出站路由：WS msg/side/edit kind → sender API（含 reply-to-placeholder 语义） |
| `sender.py` | 飞书 REST API 封装：send_text/send_card/update_card/reply_in_thread/recall/get_chat_info |
| `feishu_renderer.py` | 卡片 JSON 构建：build_conv_card / csat_card / thank_you_card |
| `group_manager.py` | ChannelMapper：channel_id ↔ chat_id 双向映射 |
| `routing_reader.py` | 独立解析 routing.toml 给 bridge（不依赖 CS 模块） |

### plugins `src/plugins/`

| Plugin | 触发 | 副作用 |
|---|---|---|
| `mode` | `/hijack /release /copilot` 命令 | emit `mode_changed` event |
| `sla` | `mode_changed=takeover` / side 中含 `@operator/@人工/...` | takeover 超时自动 `/release`；help 求助 180s timer + emit `help_requested/help_timeout` |
| `resolve` | `/resolve` 命令 | emit `channel_resolved` |
| `audit` | 所有 message + 关键 event | 写 audit.json：takeover 次数、CSAT、message_count、首响时间 |
| `activation` | dormant channel 上的 message | emit `customer_returned` 事件 |
| `csat` | `channel_resolved` event | emit `csat_request`；订阅 `csat_score` event → audit.record_csat |

### protocol `zchat-protocol/zchat_protocol/`

| 模块 | 职责 |
|---|---|
| `irc_encoding.py` | IRC 前缀编解码：`__msg:<uuid>:<text>` / `__side:` / `__edit:<uuid>:<text>` / `__zchat_sys:<json>` |
| `ws_messages.py` | bridge↔CS WebSocket 消息 schema：`build_message/event/register` + `parse` |
| `naming.py` | scoped_name (`{username}-{name}`) + AGENT_SEPARATOR ("-" 兼容 IRC RFC 2812) |

## 4. 红线（架构隔离）

| 层 | 允许 import | 禁止 |
|---|---|---|
| `agent_mcp.py` | zchat-protocol | channel_server / feishu_bridge |
| `feishu_bridge/` | zchat-protocol | channel_server (除非通过 bridge_reader 单独读 routing) |
| `channel_server/` | zchat-protocol | feishu_bridge / 任何业务模块名 |
| `zchat-protocol/` | 标准库 only | 任何外部 |

**业务术语红线**：`channel_server/` + `zchat-protocol/` + `zchat/cli/`（除 templates/）禁止出现 `customer / operator / admin / squad / feishu` 等业务命名。bridge / templates 是业务层，允许。

## 5. 数据流方向

| 入站 | 出站 |
|---|---|
| 平台 → bridge → CS WS → CS router → IRC PRIVMSG → agent_mcp → Claude | Claude reply tool → agent_mcp → IRC PRIVMSG → CS router → CS WS broadcast → bridge → 平台 API |

**事件流（plugin emit）**：
```
plugin.emit_event(channel, "name", data) →
  ├── ws_server.broadcast (所有 bridge 订阅)
  ├── plugin_registry.broadcast_event (其它 plugin 订阅)
  └── irc_connection.privmsg(channel, encode_sys(slim_payload))   ← agent 通过 __zchat_sys: 感知
```

## 6. 进程编排（不在消息层）

`zchat up` 启动所有进程，每个独立 zellij tab：

```
zellij session: zchat-<project>
├── tab: ctl            — 空 CLI pane (session 初始化时创建)
├── tab: chat           — 内含 pane name=weechat (IRC 客户端，用户监控)
├── tab: cs             — channel-server 进程
├── tab: bridge-customer — feishu_bridge --bot customer
├── tab: bridge-admin    — feishu_bridge --bot admin  
├── tab: bridge-squad    — feishu_bridge --bot squad
├── tab: yaosh-fast-001  — Claude Code + agent_mcp
├── tab: yaosh-admin-0   — Claude Code + agent_mcp
└── tab: yaosh-squad-0   — Claude Code + agent_mcp

ergo IRC server 单独后台进程，不占 zellij tab
```

## 7. 关键设计决策

- **IRC 作消息总线** — 用成熟协议解决 multi-process pub/sub + presence；不自造协议
- **plugin 不互相 import** — 通过 emit_event 事件总线解耦；只能 import channel_server.plugin 基类
- **bridge 不依赖 CS** — bridge 通过 routing_reader 独立解析 routing.toml（spec §2.2 红线 2）
- **routing.toml 是唯一动态持久化** — CLI 写、CS watch reload、bridge 读
- **agent 之间不直接 DM** — 协同走 channel + `@nick` 前缀（`__side:@yaosh-deep-001 ...`），不用 IRC PRIVMSG-to-nick

## 关联文档

- 详细 V5 spec: `docs/discuss/005-v5-channel-server-spec/`
- V6 收尾方案: `docs/discuss/008-v6-finalize-plan.md`
- 测试计划: `docs/discuss/006-v6-pre-release-test-plan.md`
- Quick start: `002-quick-start.md`
