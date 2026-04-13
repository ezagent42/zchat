# 02-架构设计：zchat 消息总线 × AutoService 多 Agent 平台

> zchat 作为消息总线和 agent 基础设施底座，AutoService 作为业务层应用。

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    AutoService 业务层                      │
│  ┌──────────┐  ┌──────────┐  ┌───────┐  ┌───────────┐   │
│  │ Feishu   │  │ Web Chat │  │ Voice │  │ 业务插件   │   │
│  │ Adapter  │  │ Adapter  │  │Adapter│  │ CRM/KB/...│   │
│  └────┬─────┘  └────┬─────┘  └───┬───┘  └─────┬─────┘   │
│       │              │            │            │          │
│  ┌────┴──────────────┴────────────┴────────────┘         │
│  │         zchat-bridge (通用 bridge 框架)                │
│  │   adapter 层: 渠道协议 ↔ IRC PRIVMSG 转换              │
│  └────────────────────┬──────────────────────────        │
└───────────────────────┼──────────────────────────────────┘
                        │ IRC
┌───────────────────────┼──────────────────────────────────┐
│                  zchat 基础设施层                          │
│                       │                                   │
│  ┌────────────────────▼───────────────────────┐          │
│  │              ergo IRC Server                │          │
│  │  #general  #cust-001  #cust-002  #admin     │          │
│  └──┬──────────┬──────────┬──────────┬────────┘          │
│     │ IRC      │ IRC      │ IRC      │ IRC               │
│     ▼          ▼          ▼          ▼                    │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐                 │
│  │fast  │  │deep  │  │sched │  │admin │                  │
│  │agent │  │agent │  │agent │  │agent │                  │
│  │(chan- │  │(chan- │  │(chan- │  │(chan- │                 │
│  │ nel- │  │ nel- │  │ nel- │  │ nel- │                  │
│  │server)  │server)  │server)  │server)                  │
│  └──┬───┘  └──┬───┘  └──┬───┘  └──┬───┘                 │
│     │MCP      │MCP      │MCP      │MCP                   │
│     ▼         ▼         ▼         ▼                      │
│   claude    claude    claude    claude                    │
│   (fast)    (opus)    (sonnet)  (sonnet)                 │
└──────────────────────────────────────────────────────────┘
```

## 2. 核心设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 消息协议 | IRC（ergo） | zchat 已有完整 IRC 基础设施，天然支持 channel/nick/presence |
| 渠道接入 | Bridge 模式（每渠道一个 IRC bot） | 保持 channel-server 单一职责，bridge 独立开发部署 |
| 多租户 | 每租户一个 zchat project（独立 ergo） | 天然隔离，匹配 zchat project 模型 |
| Agent 生命周期 | 全部常驻 | 简化初期实现，后续优化为混合模式 |
| 客户对话 | 每客户一个 IRC channel | 支持多 agent 协作（copilot/takeover） |
| Channel 持久化 | 管理 agent 负责消息存储 + channel 状态管理 | active → idle → reactivate |
| 会话历史 | 管理 agent 查询接口 | 管理员可查看任意租户历史，不需要实时监控 |

## 3. 组件设计

### 3.1 zchat-bridge（新模块）

**职责**：渠道协议 ↔ IRC 的双向转换。

```
zchat-bridge/
├── bridge_core.py          # 通用框架：IRC 连接 + 消息格式 + 生命周期
├── adapters/
│   ├── feishu.py           # 飞书 WebSocket/回调 → IRC PRIVMSG
│   ├── web.py              # HTTP/WebSocket → IRC PRIVMSG
│   └── voice.py            # PSTN/WebRTC → IRC PRIVMSG（预留）
├── channel_mapper.py       # 客户 ID ↔ IRC channel 映射
│                           #   客户首次接入 → 创建 #cust-{id}
│                           #   客户再次接入 → 重用 #cust-{id}
└── presence.py             # 客户在线状态 → IRC JOIN/PART
```

**bridge_core 行为**：
1. 以 IRC bot 身份连接 ergo（nick: `feishu-bridge`、`web-bridge`）
2. 收到渠道消息 → 查找/创建对应 IRC channel → IRC PRIVMSG
3. 收到 IRC 消息（agent 回复）→ 转换为渠道格式 → 发送给客户
4. 管理客户 ↔ channel 映射的持久化

**消息格式**：
```
# 渠道 → IRC（bridge 发送）
PRIVMSG #cust-001 :__zchat_bridge:{"source":"feishu","user_id":"ou_xxx","user_name":"张三","text":"你好","media":[]}

# IRC → 渠道（bridge 接收 agent 回复）
PRIVMSG #cust-001 :你好！我是智能客服，有什么可以帮您？
```

- 客户消息用 `__zchat_bridge:` 前缀 + JSON 包裹（携带渠道元数据）
- Agent 回复是纯文本（channel-server 的 MCP reply tool 输出）
- 富媒体（图片/文件）通过 JSON 的 `media` 字段传递 URL

**消息来源区分**（多 agent 场景的关键）：
- 有 `__zchat_bridge:` 前缀 → 客户消息（来自 bridge）
- 有 `__zchat_sys:` 前缀 → 系统控制消息
- 无前缀 → 其他 agent 的回复或 @mention
- 每个 agent 的 instructions 中需要明确这个区分规则，避免 agent 对其他 agent 的回复产生不必要的反应

### 3.2 Channel-Server 改造

zchat 的 channel-server 需要增加**多 agent 路由**能力：

**当前**：一个 channel-server 实例 = 一个 agent。@mention 触发。

**改造后**：channel-server 感知 agent 角色，实现路由策略：

```python
# 路由规则（在 channel-server 配置中定义）
routing_rules:
  # 新客户消息默认路由到 fast-agent
  default: fast-agent
  
  # 复杂查询（关键词/意图检测）路由到 deep-agent
  complex_query:
    trigger: intent_detection  # 或关键词匹配
    target: deep-agent
    fallback: fast-agent       # deep-agent 未就绪时
  
  # 人工接管请求
  takeover:
    trigger: "@admin" or "/hijack"
    target: admin-agent
  
  # agent 间协作
  agent_to_agent:
    trigger: "@{agent-nick}"   # 已有的 @mention 机制
```

**需要改造 channel-server**：当前 `server.py:118` 的 `on_pubmsg` 只在检测到 `@mention` 自己时才转发消息给 Claude。但在多 agent 场景下，`fast-agent` 需要接收所有客户消息（不一定有 @mention），`scheduler-agent` 需要监听所有消息做路由决策。

**改造方案**：在 channel-server 中增加**消息过滤模式**配置（通过环境变量 `MSG_FILTER`）：

```python
# server.py on_pubmsg 改造
MSG_FILTER = os.environ.get("MSG_FILTER", "mention")  # "mention" | "all" | "silent"

def on_pubmsg(conn, event):
    nick = event.source.nick
    if nick == AGENT_NAME:
        return
    body = event.arguments[0]
    
    if MSG_FILTER == "mention":
        # 原有行为：只响应 @mention 自己的消息
        if not detect_mention(body, AGENT_NAME):
            return
    elif MSG_FILTER == "all":
        # 新模式：接收所有消息（fast-agent、scheduler-agent 使用）
        pass
    elif MSG_FILTER == "silent":
        # 静默模式：只接收 @mention 和 __zchat_sys: 系统消息（admin-agent 使用）
        if not detect_mention(body, AGENT_NAME) and "__zchat_sys:" not in body:
            return
```

每种 agent 的 `MSG_FILTER` 配置：

| Agent | MSG_FILTER | 行为 |
|-------|-----------|------|
| fast-agent | `all` | 接收所有客户消息，即时回复 |
| deep-agent | `mention` | 只在被 @mention 时响应（由 scheduler 触发） |
| scheduler-agent | `all` | 监听所有消息，做路由决策但不直接回复客户 |
| admin-agent | `silent` | 只监听 @mention 和系统消息，负责持久化和接管 |

**instructions.md（soul.md）配合**：

- `fast-agent`：你是快速响应 agent，直接回复客户。收到 `__zchat_bridge:` 前缀的消息时提取客户问题并回答
- `deep-agent`：你是深度思考 agent，只在被 @mention 时响应。调用资源接口做深度分析
- `scheduler-agent`：你是调度 agent，监听所有消息但**不直接回复客户**。判断消息复杂度，必要时 @deep-agent 请求深度分析
- `admin-agent`：你是管理 agent，持久化所有对话，响应 /hijack 命令，处理人工接管

**agent 间协作仍通过 @mention**：scheduler 通过 `@tenantA-deep 请分析这个复杂问题` 触发 deep-agent，这是 zchat 已有的 agent-to-agent 通信机制。

**改动量评估**：channel-server 只需改 `on_pubmsg` 中约 10 行代码 + 增加 `MSG_FILTER` 环境变量。

### 3.3 Agent 角色定义

每个 agent = 一个 zchat agent（Claude Code session + channel-server），通过 workspace 配置区分角色。

| Agent | nick 示例 | 常驻 channel | 模型 | workspace 关键配置 |
|-------|----------|-------------|------|------------------|
| fast-agent | `tenantA-fast` | `#general` + 所有 `#cust-*` | Haiku/Sonnet (快) | `soul.md`: 快速回复策略、知识库查询 |
| deep-agent | `tenantA-deep` | `#general`（监听 @mention） | Opus (慢但准) | `soul.md`: 深度分析、资源接口调用 |
| scheduler-agent | `tenantA-sched` | `#general` + 所有 `#cust-*` | Sonnet | `soul.md`: 意图检测、路由决策、agent 编排 |
| admin-agent | `tenantA-admin` | `#general` + `#admin` | Sonnet | `soul.md`: 消息持久化、会话管理、人工接管 |

**Agent workspace 结构**（每个 agent 的 `~/.zchat/projects/{tenant}/agents/{nick}/`）：
```
agents/tenantA-fast/
├── .zchat-env              # 环境变量（API key、模型选择）
├── soul.md                 # agent 角色定义 + 行为指令
├── CLAUDE.md               # Claude Code 指令（引用 soul.md）
└── .claude/
    └── settings.local.json # MCP server 配置（channel-server 地址）
```

### 3.4 Channel 生命周期

```
客户首次接入
  └→ bridge 查询 channel_mapper: 该客户有无历史 channel?
      ├─ 无 → 创建 #cust-{id}, 状态=active
      │       scheduler-agent 收到 JOIN 通知
      │       fast-agent JOIN #cust-{id}
      │       admin-agent 记录新客户
      │
      └─ 有 → 重新激活 #cust-{id}, 状态=idle→active
              scheduler-agent 通知 fast-agent JOIN
              admin-agent 注入历史摘要到 channel
              fast-agent 收到摘要 + 新消息

客户离开
  └→ bridge 检测到 WebSocket/连接断开
      └→ IRC PART #cust-{id}
         scheduler-agent 收到 PART 通知
         等待 grace period (5min)
         └→ 超时 → channel 状态=idle
            fast-agent PART #cust-{id}（释放注意力）
            admin-agent 生成对话摘要存储
```

### 3.5 人机交接（Copilot / Takeover）

利用 zchat 已有的 agent-to-agent 通信：

**Copilot 模式（默认）**：fast-agent 主导对话，admin-agent 在旁观察
```
[#cust-001]
bridge:    __zchat_bridge:{"user":"张三","text":"B 套餐多少钱"}
fast:      B 套餐每月 199 元，当前有 8 折优惠...
admin:     (旁听，不发言，记录对话)
```

**Takeover 触发**：
```
# 方式 1: agent 主动求助
[#cust-001]
fast:      @tenantA-admin 这个问题超出我的能力范围，请接管

# 方式 2: 管理员主动接管
[#admin]
管理员:    @tenantA-admin /hijack #cust-001

# 方式 3: 系统自动升级（scheduler 判断）
[#cust-001]
sched:     __zchat_sys:{"type":"takeover","channel":"#cust-001","reason":"customer_escalation"}
```

**角色翻转后**：
```
[#cust-001]
admin:     您好，我是人工客服小李（接管对话）
fast:      (切换为副驾驶，通过 @tenantA-admin 提供建议，不直接回复客户)
```

## 4. 多租户架构

```
┌─────────────────────────────────────────────┐
│              zchat 管理节点                    │
│  zchat project list                          │
│  ├── tenant-a (ergo:6667)                    │
│  ├── tenant-b (ergo:6668)                    │
│  └── tenant-c (ergo:6669)                    │
│                                              │
│  每个 tenant = 一个 zchat project:            │
│  zchat --project tenant-a agent list         │
│  zchat --project tenant-a irc status         │
└─────────────────────────────────────────────┘
```

**租户创建流程**：
```bash
# 1. 创建 zchat project
zchat project create tenant-acme --server local --port 6670

# 2. 创建 4 个 agent（全部常驻）
zchat --project tenant-acme agent create fast --type fast-response
zchat --project tenant-acme agent create deep --type deep-thinking
zchat --project tenant-acme agent create sched --type scheduler
zchat --project tenant-acme agent create admin --type admin-manager

# 3. 启动 bridge（Feishu adapter 连接该租户的 ergo）
zchat --project tenant-acme bridge start feishu --config tenant-acme-feishu.yaml

# 4. 验证
zchat --project tenant-acme agent list
zchat --project tenant-acme irc status
```

**Agent type** 映射到 workspace 模板（zchat 的 `templates/` 机制）：
```
templates/
├── fast-response/
│   ├── template.toml       # model=haiku, channels=["#general"]
│   ├── soul.md             # 快速响应角色定义
│   └── start.sh
├── deep-thinking/
│   ├── template.toml       # model=opus, channels=["#general"]
│   ├── soul.md             # 深度分析角色定义
│   └── start.sh
├── scheduler/
│   ├── template.toml       # model=sonnet, channels=["#general"]
│   ├── soul.md             # 调度策略
│   └── start.sh
└── admin-manager/
    ├── template.toml       # model=sonnet, channels=["#general","#admin"]
    ├── soul.md             # 管理 + 持久化 + 接管
    └── start.sh
```

## 5. AutoService 业务层改造

AutoService 从"自维护 channel-server + tmux agent 管理"变为"zchat project 配置"：

### 删除（迁移到 zchat）
- `feishu/channel_server.py` — 替换为 zchat ergo + bridge
- `feishu/channel.py` — 替换为 zchat channel-server
- `autoservice.sh` 中的 tmux agent spawn 逻辑 — 替换为 zchat agent 管理

### 保留
- `autoservice/` — 核心业务逻辑（CRM、知识库、规则引擎、权限）
- `web/` — Web 前端（通过 web bridge 接入 zchat）
- `plugins/` — 业务插件（作为 agent 的 MCP tool）
- `skills/` — Claude Code skill（配置到 agent workspace）

### 新增
- `tenant-configs/` — 每个租户的 zchat project 配置模板
  - bridge adapter 配置（Feishu credentials、Web 端点）
  - agent soul.md 模板（注入租户特定的知识库、规则）
  - MCP tool 配置（哪些插件暴露给哪个 agent）

## 6. 数据流：一次完整的客户对话

```
1. 客户在飞书发消息 "B 套餐多少钱"
2. Feishu Adapter 收到 → bridge_core → IRC PRIVMSG #cust-001
3. ergo 路由到 #cust-001 的所有成员
4. scheduler-agent 收到 → 判断为简单查询 → 不干预（fast-agent 默认处理）
5. fast-agent 的 channel-server 检测到消息 → MCP inject → Claude (Haiku)
6. Claude 查询知识库（MCP tool）→ 生成回复
7. fast-agent 通过 channel-server reply → IRC PRIVMSG #cust-001
8. bridge_core 收到 → Feishu Adapter → 飞书消息发给客户
9. admin-agent 收到 → 持久化到存储

---

10. 客户追问 "和 A 套餐的详细对比？能不能自定义？"
11. scheduler-agent 检测到复杂查询 → @tenantA-deep 请分析这个对比需求
12. deep-agent 收到 @mention → MCP inject → Claude (Opus)
13. deep-agent 调用多个 MCP tool（知识库 + CRM + 定价引擎）
14. fast-agent 同时发送 "稍等，正在为您详细查询..."（占位消息）
15. deep-agent 生成详细回复 → IRC PRIVMSG #cust-001
16. bridge → Feishu → 客户收到完整回复
```
