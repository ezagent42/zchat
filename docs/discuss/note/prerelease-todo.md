# Pre-release 待办 + 架构决策记录

> 逐项 PRD review 过程中发现的待补内容
> 更新于 2026-04-15, iteration 3

---

## 架构决策（已确认）

### 1. channel-server 独立化（最重要的架构变更）

**问题**: 当前 channel-server 作为 MCP server 嵌入每个 agent 的 Claude Code 进程。每个 agent 都跑一套完整的 ConversationManager + ModeManager + Bridge API。导致：
- feishu_bridge 只能连一个 agent 的 Bridge API，其他 agent 消息要"中转"
- 重复的状态管理实例，不一致
- fast-agent 既做 AI 又承担全局路由

**目标架构**:
```
channel-server（独立进程，不在任何 Claude Code 里）
  ├── IRC bot → ergo :6667（监听所有 channel，看到所有消息）
  ├── Bridge API :9999 ← feishu_bridge
  ├── engine/（ConversationManager + ModeManager + Gate + EventBus + TimerManager）
  └── 路由: feishu ↔ IRC，按 visibility/mode 规则过滤

fast-agent: Claude Code ↔ [轻量 agent_mcp.py] ↔ IRC ↔ ergo
deep-agent: Claude Code ↔ [轻量 agent_mcp.py] ↔ IRC ↔ ergo
```

**channel-server IRC bot 身份**:
- IRC nick: `cs-bot`（或 `channel-server`，需要一个固定 nick）
- 自动 JOIN 所有 `#conv-*` 频道 + `#squad-*` 频道
- 不 JOIN `#general` 等普通频道（那些由 agent 自己管理）

**消息流**:
```
客户消息 → feishu_bridge → channel-server (Bridge API) → IRC #conv-xxx → agent_mcp → Claude Code
agent回复 → agent_mcp reply() → IRC #conv-xxx → channel-server 看到 → Gate/visibility → Bridge API → feishu_bridge → 飞书
```

**channel-server IRC bot 路由规则**（核心新逻辑）:

channel-server 的 IRC bot 监听 `#conv-*` 和 `#squad-*` 频道所有消息，按以下规则路由：

| IRC 来源 | 消息特征 | channel-server 动作 |
|---------|---------|-------------------|
| `#conv-xxx` 中 agent 发的消息 | 普通 PRIVMSG（无特殊前缀） | Gate 判定 visibility -> Bridge API `{type: "reply", visibility: "public/side"}` |
| `#conv-xxx` 中 agent 发的 edit | 带 `__edit:msg_id:` 前缀 | Bridge API `{type: "edit", message_id: msg_id}` |
| `#conv-xxx` 中 agent 发的 side | 带 `__side:` 前缀 | Bridge API `{type: "reply", visibility: "side"}` |
| Bridge API 收到客户消息 | -- | channel-server 发 IRC PRIVMSG 到 `#conv-xxx` |
| Bridge API 收到 operator_message | -- | channel-server 发 IRC PRIVMSG 到 `#conv-xxx`（Gate 按 mode 判定 visibility） |

**IRC 消息格式约定**（机器可读）:

agent_mcp 发出的 IRC 消息用前缀区分类型：
```
普通回复(含ID): PRIVMSG #conv-xxx :__msg:uuid:回复内容
编辑替换:       PRIVMSG #conv-xxx :__edit:msg_003:替换后的完整内容
side 消息:      PRIVMSG #conv-xxx :__side:建议内容
无前缀回复:     PRIVMSG #conv-xxx :回复内容                          ← 兼容，无 message_id
```

channel-server IRC bot 通过 `parse_agent_message()` (transport/irc_transport.py:30-62) 解析前缀：
- `__msg:` → type="reply", 提取 message_id（用于 edit_of 追踪）
- `__edit:` → type="edit", 提取 original message_id
- `__side:` → type="side"
- 无前缀 → type="reply", visibility 由 Gate 根据 mode + sender role 决定

**visibility 推断逻辑**: channel-server 知道每个 conversation 的 mode（ConversationManager 持有），也知道每个 IRC nick 的 role（agent/operator）。Gate 规则（protocol/gate.py）根据 mode + role + 原始 visibility 决定最终 visibility。这部分逻辑不变，只是执行位置从 per-agent 移到中心。

**拆分方案**: 只拆 server.py (644行)，engine/protocol/bridge_api/transport 全部 0 改动

| 产出 | 内容 | 行数 |
|------|------|------|
| `server.py`（改造） | 独立进程：IRC bot + Bridge API + engine 组装 + 路由逻辑 | ~300 |
| `agent_mcp.py`（新建） | 轻量 MCP server：MCP stdio + tools + IRC @mention 注入 | ~200 |

**unit tests**: engine/ + protocol/ + bridge_api/ 的 unit tests 全部继续 PASS（0 改动）

**E2E tests 需调整**: conftest.py 的 `channel_server` fixture 当前用 `stdin=subprocess.PIPE` 启动（MCP stdio 模式）。拆分后 channel-server 是普通进程（非 MCP stdio），fixture 需改为 `subprocess.Popen(["uv", "run", "zchat-channel"])`，去掉 stdin pipe。6 个 E2E test 文件的启动方式受影响，断言逻辑不变。

**pyproject.toml**: 当前 entry_point `zchat-channel = "server:entry_point"`。拆分后需两个：
- `zchat-channel = "server:entry_point"` -- 独立进程（IRC bot + Bridge API）
- `zchat-agent-mcp = "agent_mcp:entry_point"` -- 轻量 MCP server（agent 用）

**agent 的 .mcp.json 配置变更**: `zchat agent create` 生成的 `.mcp.json` 中 MCP server 命令需从 `zchat-channel` 改为 `zchat-agent-mcp`。

**Bridge API 注册协议**: 不变。feishu_bridge 仍用 `{type: "register", bridge_type: "feishu", ...}` 注册。bridge_api/ws_server.py 0 改动。

**启动流程**:
```
1. ergo IRC server
2. channel-server 独立进程: uv run zchat-channel（IRC bot + Bridge API :9999）
3. zchat agent create fast-agent（轻量 agent_mcp，.mcp.json 指向 zchat-agent-mcp）
4. zchat agent create deep-agent（轻量 agent_mcp）
5. feishu_bridge -> ws://localhost:9999（连 channel-server，不连任何 agent）
```

**spec/plan 需同步更新**:
- [ ] `02-channel-server.md` -- 架构图：per-agent -> 独立进程；MCP Server 移出到 agent_mcp.py
- [ ] `00-overview.md` -- 架构图同上；Agent 层改为 "agent_mcp.py + IRC"
- [ ] `07-phase-final-testing.md` -- 启动流程 + fixture（先启独立 channel-server）
- [ ] `05-user-journeys.md` -- 消息流措辞；删除"不是独立进程"的描述
- [ ] `07-migration-plan.md` -- 新增 agent_mcp.py 描述；agent 模板系统标注 out of scope

### 2. 快慢双 agent

- fast-agent (haiku): 简单问答 + 占位
- deep-agent (sonnet/opus): 复杂查询 + edit 替换
- 各自独立 agent_mcp 进程，共享同一 IRC (ergo)
- channel-server 是中心路由，统一管理 conversation 状态
- 注: "协议级智能路由"仍为 v1.1 scope，v1.0 通过 soul.md 行为实现双 agent 协作

### 3. Squad群 thread 模型

- squad群是监控中心，每个 conversation = 一张卡片 (thread root) + 对应 thread
- copilot: operator 在 squad thread 中给 agent 发建议（side）
- takeover: operator 直接在客户群回复（自动触发 hijack），agent 在 squad thread 提供副驾驶建议
- 飞书 API: `message.create()` 发卡片 -> `message.reply(reply_in_thread=True)` 追加 thread -> `message.update()` 刷新卡片

### 4. Takeover 触发方式

- operator 在客户群发消息 = 自动 hijack（不需要 /hijack 命令）
- feishu_bridge 检测"已知 operator 在 customer_chat 发消息" -> 发 operator_join + 转 takeover
- /hijack 命令保留为备选（可在 squad thread 中使用）

### 5. Agent 配置方式

- soul.md 和模型配置直接写到 agent workspace 目录下
- zchat agent 配置命令不在本次开发范围

### 6. Agent 编排 = 外部配置 + channel-server 执行

编排策略在外部配置文件（routing.toml 或类似），不在 channel-server 代码里，也不在 soul.md 里。
channel-server 只负责读取配置并执行。

**配置示例**:
```toml
[routing]
default_agents = ["fast-agent"]              # 新 conversation 自动 dispatch
escalation_chain = ["deep-agent", "operator"] # 升级时按顺序尝试
available_agents = ["deep-agent", "translation-agent", "audit-agent"]  # /dispatch 白名单
```

**channel-server 需支持的执行能力**:
- [ ] 启动时加载 routing 配置
- [ ] 新 conversation 创建时 auto-dispatch default_agents
- [ ] 收到 escalation event 时按 escalation_chain 顺序 auto-dispatch
- [ ] /dispatch 命令验证 agent 在 available_agents 白名单中
- [ ] agent 之间通过 IRC side message 自由协作（channel-server 不干预，只保证 visibility）

**agent soul.md 管自己的行为 + pipeline 接力（v1.0）**:
- fast-agent: "搞不定就发 escalation event；处理完 @translation-agent 翻译回去"
- deep-agent: "收到 @mention 就分析；处理完 @fast-agent 告知结果"
- translation-agent: "收到翻译请求就翻译；翻译完 @下一个 agent"
- audit-agent: "审核消息合规性；通过后放行"

**v1.1 升级路径: pipeline 引擎**:
v1.0 的 pipeline 接力逻辑分散在各 agent soul.md 中（agent 自行 @mention 下一个）。
v1.1 将 pipeline 逻辑提升到 channel-server：
```toml
# v1.1 routing.toml 新增
[pipeline]
incoming = ["translation-agent", "fast-agent"]   # 入站管线
outgoing = ["translation-agent"]                  # 出站管线
```
channel-server 拦截消息，按配置顺序路由，agent 不需要知道"下一个是谁"。
Socialwares compiler 可从 socialware.py 的 Flow 定义编译出 pipeline 配置。

---

## 按 US 分类的待补缺口

### US-2.1: 客户接入

- [ ] **TestFeishuConversationReactivation 补验证点**: 第二轮对话的 conversation_id 应与第一轮相同（证明 reactivate 而非新建）
- [ ] Conversation 通过 SQLite 持久化（已实现），老客户重入时从 db 恢复

### US-2.2: 占位 + 续写替换（快慢双 agent）

IRC 中是两条消息，飞书中通过 edit_of 标记合并为一条。

**agent_mcp 层**:
- [ ] **reply() 返回 message_id**: agent_mcp 为每条消息生成 UUID，返回给 Claude Code
- [ ] **reply(edit_of=msg_id)**: 带此参数时 IRC PRIVMSG 用 `__edit:msg_id:` 前缀
- [ ] **reply(side=True)** 或 **send_side_message()**: IRC PRIVMSG 用 `__side:` 前缀
- [ ] agent_mcp 不持有 MessageStore（消息持久化统一在 channel-server）

**agent_mcp MCP tools 完整列表**:

| Tool | 参数 | 说明 |
|------|------|------|
| `reply` | `chat_id, text, edit_of?, side?` | 发消息/编辑/side，返回 message_id |
| `join_conversation` | `conversation_id` | JOIN #conv-{id} |
| `send_side_message` | `conversation_id, text` | 语法糖，等价于 reply(side=True) |

注: `list_conversations` 和 `get_conversation_status` 从 agent_mcp 移除。agent 不直接查 ConversationManager。如需查询，在 IRC 发 `__query:status` 前缀消息，channel-server 回复。

**channel-server 层（独立进程）**:
- [ ] **解析 IRC 消息前缀**: `__edit:msg_id:text` -> Bridge `{type: "edit"}`; `__side:text` -> `{type: "reply", visibility: "side"}`
- [ ] **MessageStore 统一存储**: 所有消息存入 MessageStore, msg_id 由 agent_mcp 生成通过 IRC 前缀传递

**feishu_bridge 层**:
- [ ] **cs->feishu 消息 ID 映射**: 发送飞书消息后存 `{cs_msg_id: feishu_msg_id}`。收到 `{type: "edit"}` 时查映射调 `sender.update_message_sync()`

**agent 行为层**:
- [ ] **fast-agent soul.md**: 简单问题直接答；复杂问题 -> reply() 占位 -> send_side_message(@deep-agent, msg_id=xxx)
- [ ] **deep-agent soul.md**: 收到 side -> 深度分析 -> reply(edit_of=msg_id) 替换

### US-2.3 + US-2.4: 分队卡片 + Copilot

**feishu_bridge 层**:
- [ ] **ConvThread 映射**: `conversation_id -> ConvThread(card_msg_id, customer_chat_id, last_customer_msg_id)`
- [ ] **conversation.created -> send_card**: 新对话在 squad群 发卡片，card_msg_id = thread root
- [ ] **public reply -> 双写**: agent public 回复同时发 customer_chat + squad thread
- [ ] **side message -> thread only**: side 消息只进 squad thread
- [ ] **mode.changed -> update_card**: 模式变更更新卡片
- [ ] **conversation.closed -> update_card**: 关闭标记

**反向路由**:
- [ ] **squad thread 消息识别**: 飞书消息 `root_id` 属于已知 card_msg_ids -> operator_message (side)
- [ ] **客户群 operator 消息识别**: `chat_id` 属于 customer_chats + `sender_id` 属于 known_operators -> 触发 takeover

### US-2.5 + US-2.6: Takeover

- [ ] **自动 hijack**: operator 在客户群发消息 -> feishu_bridge 自动发 operator_join + operator_command(/hijack)
- [ ] **operator 加入客户群**: 卡片"进入对话"按钮 -> feishu_bridge 通过飞书 API 将 operator 拉入客户群
- [ ] **/hijack 保留**: squad thread 中可手动使用

---

## Pre-release Fixture

### fast-agent 配置
- [ ] **模型**: haiku
- [ ] **soul.md**: 简单问答 + 占位委托 + 采纳建议 + @operator 求助 + 副驾驶
- [ ] **agent_mcp**: 轻量 MCP (zchat-agent-mcp)，tools: reply/side/join + IRC @mention 注入
- [ ] **IRC**: 自动 JOIN #conv-{customer_chat_id}

### deep-agent 配置
- [ ] **模型**: sonnet 或 opus
- [ ] **soul.md**: 接收委托 + 深度分析 + reply(edit_of=msg_id)
- [ ] **agent_mcp**: 同上

### operator 配置
- [ ] **飞书用户**: squad群 成员 -> operator 权限
- [ ] **客户群**: fixture 预先将 operator 加入，或通过卡片按钮加入

### fixture 启动顺序
```
1. zchat project create prerelease-test
2. 启动 ergo IRC
3. 启动 channel-server 独立进程: uv run zchat-channel
4. zchat agent create fast-agent -> agent_mcp + IRC
5. zchat agent create deep-agent -> agent_mcp + IRC
6. 启动 feishu_bridge（连 channel-server :9999）
7. 验证: 两个 agent 在 IRC 可见 + Bridge API 可达 + feishu_bridge 已注册
```

---

## PRD 覆盖汇总表

| PRD | 测试项 | channel-server 职责 | 状态 |
|-----|--------|-------------------|------|
| US-2.1 客户接入 | 新客户有回复 + 老客户 reactivate 同 conv_id | conversation 创建/恢复 | 补 conv_id 验证 |
| US-2.2 占位+续写 | fast-agent 占位 -> deep-agent edit 替换 | reply(edit_of) + IRC 前缀 + Bridge edit | 需 agent_mcp 拆分 |
| US-2.3 分队卡片 | squad群 收到 interactive card | Bridge event -> feishu card | 需 card+thread |
| US-2.4 Copilot | operator 在 thread 发建议，客户看不到 | Gate side visibility | 已有，需 thread 路由 |
| US-2.5 两种触发 | 自动 hijack + 180s 超时退回 | mode transition + timer | 需自动 hijack 检测 |
| US-2.6 角色翻转 | operator public + agent side + /resolve + CSAT | Gate 翻转 + resolve + set_csat | handler 补全中 |
| US-3.2 管理命令 | /status + /dispatch + /review | command handlers + routing config | 三个都做 |
| US-3.3 SLA 告警 | timer breach -> admin群 告警 | timer + event + Bridge notify | v1.0 单次 breach |
| 共用约束 | 反幻觉/多语言/上下文 | 无专项 -- agent 行为层 | 跳过 |
| Epic 1 | -- | -- | v1.0 out of scope |
| Epic 4 | -- | -- | v1.0 out of scope |

---

## Spec/Plan 一致性审阅（2026-04-15）

以下文档与上述架构决策存在矛盾，需在形成新 spec/plan 时修正。

### 决策 #1 矛盾（channel-server 独立化）

| 文件 | 位置 | 问题 | 修改方向 |
|------|------|------|---------|
| `05-user-journeys.md` | L492-504 | **直接矛盾**: 明文写"channel-server 不是独立进程，而是 Claude Code 的 MCP server" | 改为独立进程启动流程 |
| `07-phase-final-testing.md` | L108-176 | **直接矛盾**: 启动链路仍是 `zchat agent create` -> Claude Code -> channel-server MCP | fixture 改为先启 channel-server 独立进程 |
| `02-channel-server.md` | L1-12, L54-57 | MCP Server 仍列为 channel-server 三角色之一 | MCP Server 移出到 agent_mcp.py 描述 |
| `00-overview.md` | L78-101, L185-191 | Agent = "channel-server MCP client" | 改为 "agent_mcp.py（轻量 MCP + IRC）" |
| `07-migration-plan.md` | L18-21 | 改造方案无 agent_mcp.py | 新增 agent_mcp.py 的描述 |

### 决策 #2 矛盾（快慢双 agent）

| 文件 | 位置 | 问题 | 修改方向 |
|------|------|------|---------|
| `06-gap-fixes.md` | L237-239 | "快慢双模型路由策略"放入 v1.1 scope | 区分：协议级路由 v1.1，双 agent soul.md 行为 v1.0 |

### 决策 #3 矛盾（squad thread 模型）

| 文件 | 位置 | 问题 | 修改方向 |
|------|------|------|---------|
| `09-feishu-bridge.md` | L54-70, L312-344 | VisibilityRouter 是平面 send_text，无 card + thread | 改为 card + thread 模型 |
| `04-prd-mapping.md` | L79-87 | US-2.3 描述为"IRC 文本消息推到分队群" | 改为"feishu_bridge 发 interactive card + thread" |

### 决策 #4 矛盾（takeover 自动触发）

| 文件 | 位置 | 问题 | 修改方向 |
|------|------|------|---------|
| `01-protocol-primitives.md` | L170-178 | takeover 合法转换表只有 /hijack，无自动触发 | 新增: operator 在 customer_chat 发消息 -> 自动 takeover |
| `09-feishu-bridge.md` | GroupManager | 缺失 operator-in-customer-chat 自动 hijack 检测逻辑 | 在 bridge.py 添加检测 |

### 决策 #5 矛盾（agent 配置方式）

| 文件 | 位置 | 问题 | 修改方向 |
|------|------|------|---------|
| `07-migration-plan.md` | L66-86 | 包含 zchat CLI 模板系统 + create-team 命令 | 标注 v1.0 out of scope |

---

## 已知问题（待修复）

### Issue 1: ergo languages 目录下载 — fix/language-dir 分支未合并

**分支**: `fix/language-dir` (bac2f3c)，3 个 commit，未合并到 dev 或 main。

**问题**: 当前 dev 分支的 `zchat/cli/irc_manager.py` 只从 `~/.local/share/ergo/languages` 复制，如果该目录不存在则 ergo 启动失败。

**修复内容**: 新增 `_ensure_ergo_languages()` 方法，3 级 fallback：
1. `~/.local/share/ergo/languages`（系统安装）
2. Homebrew Cellar 路径
3. GitHub release 下载

**状态**: 代码已写完，待合并到 dev。不阻塞 channel-server 开发，但影响本地 ergo 首次启动。

### Issue 2: SQLite 数据库拆分为 3 个独立文件 — 需重构

**位置**: `engine/conversation_manager.py` + `engine/event_bus.py` + `engine/message_store.py`

**问题**: 3 个 engine 组件各自创建独立的 SQLite 文件（conversations.db / conversations_events.db / conversations_messages.db），但它们通过 conversation_id 强关联。跨文件无法建外键约束，导致：
- 删除对话无法 cascade 清理 events/messages
- 无事务一致性（resolve 写 conversations.db 后 crash → events.db 不一致）
- participants/resolutions 表即使在同一个 db 内也没有 FK 约束

**修复方案**: 合并为 1 个 SQLite 文件 5 张表，添加 FK + CASCADE + PRAGMA foreign_keys。详见 `spec/channel-server/11-db-consolidation.md`。

**影响范围**: engine/ 内部接线（构造函数签名），外部接口不变。~200 行代码。

**状态**: 未开始。应在 Phase Final 前完成，避免 pre-release 测试产生假绿。
