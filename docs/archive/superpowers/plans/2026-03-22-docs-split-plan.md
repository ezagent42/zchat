# 文档拆分与补充 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将单一 README + PRD 拆分为 guide/ (用户) + dev/ (开发者) 双层文档结构，补充面向现代 IM 用户的入门文档。

**Architecture:** 全部是文档文件操作，无代码变更。从现有 README.md、README_zh.md、PRD.md 提取内容，分散到 9 个新文件 + 1 个重写文件，最后清理旧文件并更新 CLAUDE.md 引用。

**Tech Stack:** Markdown, Git

---

## Chunk 1: 目录结构 + 用户文档

### Task 1: 创建目录结构 + README.md 重写

**Files:**
- Create: `docs/guide/` (directory)
- Create: `docs/dev/` (directory)
- Rewrite: `README.md`

- [ ] **Step 1: 创建目录**

```bash
mkdir -p docs/guide docs/dev
```

- [ ] **Step 2: 重写 README.md**

将 README.md 重写为 ~50 行中文导航索引。内容：

```markdown
# WeeChat-Claude

基于 [WeeChat](https://weechat.org/) 和 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 的本地多 Agent 协作系统，通过 [Zenoh](https://zenoh.io/) P2P 消息总线连接。

## 它能做什么

在终端内运行多个 Claude Code 实例作为聊天参与者——和它们对话、让它们互相协作、管理它们的生命周期。支持人与人、人与 Agent、Agent 与 Agent 的实时通信，所有数据不出本机/局域网。

## 快速导航

### 用户文档

- [概念入门](docs/guide/getting-started.md) — 第一次用？从这里开始
- [安装与启动](docs/guide/quickstart.md) — 环境准备、一键启动
- [使用指南](docs/guide/usage.md) — 命令参考、使用场景
- [限制与路线图](docs/guide/constraints.md) — 已知限制、未来方向

### 开发文档

- [架构与协议](docs/dev/architecture.md) — 系统架构、消息协议、Zenoh topic
- [weechat-zenoh](docs/dev/weechat-zenoh.md) — P2P 聊天插件
- [channel-server](docs/dev/channel-server.md) — MCP server 桥接
- [weechat-agent](docs/dev/agent.md) — Agent 生命周期管理
- [测试](docs/dev/testing.md) — 测试策略与手动测试

### 设计文档

- [设计决策记录](docs/design-decisions.md) — 设计原则与 tradeoff

## License

MIT
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/guide docs/dev
git commit -m "docs: rewrite README as navigation index, create guide/ and dev/ dirs"
```

---

### Task 2: docs/guide/getting-started.md（概念入门）

**Files:**
- Create: `docs/guide/getting-started.md`

- [ ] **Step 1: 写入 getting-started.md**

这是全新内容，面向只用过 Discord/Telegram/微信的用户。内容结构：

```markdown
# 概念入门

如果你用过 Discord、Telegram 或微信，但从没接触过 WeeChat 或 IRC，这篇文档帮你快速理解 WeeChat-Claude 的工作方式。

## 你熟悉的 IM 是怎么工作的

在 Discord 或微信中，你的消息经过一台中央服务器：消息从你的设备发到云端，再分发给其他人。服务器负责存储历史、管理在线状态、推送通知。

WeeChat-Claude 不一样——它没有中央服务器。消息通过 Zenoh P2P 协议在你的本机或局域网内直接传输。这意味着：

- **数据不出本机/内网** — 所有消息都在你控制的范围内
- **不依赖外部平台** — 不需要注册 Discord 或 Telegram 账号
- **终端原生** — 一切在 terminal 中完成，和你的开发工作流无缝衔接

## WeeChat-Claude 和你熟悉的 IM 对比

| 概念 | Discord / 微信 | WeeChat-Claude |
|------|---------------|----------------|
| 消息传输 | 云端服务器中转 | Zenoh P2P（本地/局域网直连） |
| 群聊 | #频道 / 群 | channel（`/zenoh join #channel`） |
| 私聊 | DM / 私信 | private buffer（`/zenoh join @nick`） |
| 在线状态 | 绿点 / 灰点 | Zenoh liveliness（自动广播，掉线即消失） |
| 聊天界面 | GUI 窗口 | WeeChat buffer（终端内的"标签页"） |
| AI 助手 | Bot 账号 | Claude Code 实例（和人类使用完全相同的协议） |

## 核心概念

**Buffer** — WeeChat 里的"聊天窗口"。每个 channel 或 private 对话占一个 buffer，类似 Discord 左侧的频道列表项。你可以同时打开多个 buffer，用快捷键切换。

**Nick** — 你的昵称，类似 Discord 用户名。在 WeeChat-Claude 中用 `/zenoh nick <name>` 设置。

**Channel** — 群聊，类似 Discord 的频道。任何人都可以加入，消息对所有成员可见。

**Private** — 一对一私聊，类似 Discord 的 DM。消息只有双方可见。

**Agent** — 一个 Claude Code 实例。它在聊天中表现得和人类一样——使用相同的消息格式、走相同的 Zenoh 通道。你可以同时运行多个 Agent。

## WeeChat 基本操作

WeeChat 运行在终端中，所有操作通过键盘完成：

| 操作 | 方法 |
|------|------|
| 发消息 | 直接打字，按 Enter 发送 |
| 输入命令 | 以 `/` 开头，例如 `/zenoh join #team` |
| 切换 buffer | `Alt+数字`（Alt+1, Alt+2...）或 `Alt+←/→` |
| 查看在线成员 | 看 buffer 右侧的 nicklist |
| 滚动历史 | `Page Up` / `Page Down` |
| 关闭当前 buffer | `/zenoh leave` |

> **提示**：如果你习惯鼠标操作，可以在 WeeChat 中执行 `/mouse enable` 开启鼠标支持。

## 下一步

环境搭好了，概念也了解了，接下来 → [安装与启动](quickstart.md)
```

- [ ] **Step 2: Commit**

```bash
git add docs/guide/getting-started.md
git commit -m "docs: add getting-started guide for modern IM users"
```

---

### Task 3: docs/guide/quickstart.md（安装与启动）

**Files:**
- Create: `docs/guide/quickstart.md`
- Source: README.md §Prerequisites + §Quick Start

- [ ] **Step 1: 写入 quickstart.md**

```markdown
# 安装与启动

## 前置条件

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | ≥ 2.1.80 | Anthropic 的 CLI AI 助手 |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.4 | Python 包管理器（类似 npm） |
| [WeeChat](https://weechat.org/) | ≥ 4.0 | 终端聊天客户端 |
| [tmux](https://github.com/tmux/tmux) | — | 终端多窗口管理器 |
| Python | ≥ 3.10 | 运行时 |
| [zenohd](https://zenoh.io/) | ≥ 1.0.0 | Zenoh router daemon |

## 一键启动

```bash
git clone https://github.com/ezagent42/weechat-claude.git
cd weechat-claude
./start.sh ~/my-project alice
```

`start.sh` 会自动完成以下步骤：

1. **检查依赖** — 确认 claude、uv、weechat、tmux、zenohd 都已安装
2. **确保 zenohd 运行** — 在 `localhost:7447` 启动 Zenoh router（如果尚未运行）
3. **安装依赖** — `uv sync` 安装 channel-server 依赖，`uv pip install --system eclipse-zenoh` 让 WeeChat 的系统 Python 能 import zenoh
4. **复制插件** — 将 weechat-zenoh.py 和 weechat-agent.py 复制到 WeeChat 插件目录
5. **创建 tmux session** — 分为两个 pane：
   - **Pane 0**：Claude Code (agent0) + channel plugin
   - **Pane 1**：WeeChat + zenoh/agent 插件已加载

## 第一次对话

启动后，你会看到 WeeChat 界面。和 agent0 打个招呼：

```
/zenoh join @agent0
hello agent0，你能帮我做什么？
```

agent0 会通过 Zenoh 收到你的消息，然后通过 MCP channel 回复到你的 WeeChat buffer 中。

## 停止系统

```bash
./stop.sh
```

这会关闭 tmux session。如果要同时停止 zenohd，使用 `./stop.sh --all`。

## 下一步

了解更多命令和使用场景 → [使用指南](usage.md)
```

- [ ] **Step 2: Commit**

```bash
git add docs/guide/quickstart.md
git commit -m "docs: add quickstart guide (prerequisites, start, first conversation)"
```

---

### Task 4: docs/guide/usage.md（命令参考 + 使用场景）

**Files:**
- Create: `docs/guide/usage.md`
- Source: README.md §Usage + §Using Components Independently

- [ ] **Step 1: 写入 usage.md**

```markdown
# 使用指南

## 命令速查

### 聊天命令（weechat-zenoh）

| 命令 | 说明 |
|------|------|
| `/zenoh join #channel` | 加入一个 channel（群聊） |
| `/zenoh join @nick` | 开启 private buffer（私聊） |
| `/zenoh leave [target]` | 离开当前或指定的 channel/private |
| `/zenoh nick <name>` | 修改昵称（会广播给所有已加入的 channel） |
| `/zenoh list` | 列出已加入的 channel 和 private |
| `/zenoh status` | 显示 Zenoh session 状态（zid, peers, routers） |
| `/zenoh send <target> <msg>` | 程序化发送消息（供其他插件调用） |

### Agent 管理命令（weechat-agent）

| 命令 | 说明 |
|------|------|
| `/agent create <name> [--workspace <path>]` | 启动新的 Claude Code 实例 |
| `/agent stop <name>` | 停止一个 Agent（不能停 agent0） |
| `/agent restart <name>` | 重启一个 Agent |
| `/agent list` | 列出所有 Agent 及状态 |
| `/agent join <agent> #channel` | 让 Agent 加入一个 channel |

## 使用场景

### 场景 1：人 ↔ 人聊天

只需要 weechat-zenoh，不需要 Claude Code。适合局域网内的终端用户聊天。

```
┌─────────┐  Zenoh  ┌─────────┐
│ WeeChat │ ◄─────► │ WeeChat │
│ + zenoh │         │ + zenoh │
│ (Alice) │         │ (Bob)   │
└─────────┘         └─────────┘
```

```bash
# 终端 A
weechat
/python load /path/to/weechat-zenoh.py
/zenoh nick alice
/zenoh join #team

# 终端 B（同一局域网）
weechat
/python load /path/to/weechat-zenoh.py
/zenoh nick bob
/zenoh join #team
```

### 场景 2：人 ↔ Agent 对话

使用 weechat-zenoh + weechat-channel-server，不需要 weechat-agent 管理器。

```
┌─────────┐  Zenoh  ┌───────────────────┐
│ WeeChat │ ◄─────► │ weechat-channel   │
│ + zenoh │         │ (MCP server)      │
│ (Alice) │         │    ↕ stdio        │
└─────────┘         │ Claude Code       │
                    └───────────────────┘
```

```bash
# 终端 A：启动 Claude Code + channel plugin
cd weechat-channel-server
claude --dangerously-load-development-channels plugin:weechat-channel

# 终端 B：WeeChat
weechat
/python load /path/to/weechat-zenoh.py
/zenoh nick alice
/zenoh join @agent0
```

### 场景 3：完整部署

三个组件全部启动，通过 tmux 管理。这是 `./start.sh` 做的事。

```
┌─────────────────────────────────┐
│ WeeChat                         │
│  weechat-zenoh.py   (P2P 通信)  │
│  weechat-agent.py   (Agent 管理)│
└────────┬────────────────┬───────┘
         │  Zenoh mesh    │ subprocess
    ┌────▼────┐      ┌───▼──────────┐
    │ WeeChat │      │ Claude Code  │
    │ (Bob)   │      │ + channel    │
    └─────────┘      │ (agent0)     │
                     └──────────────┘
```

```bash
./start.sh ~/my-project alice
```

在 WeeChat 中你可以动态创建更多 Agent：

```
/agent create helper --workspace ~/another-project
/zenoh join @helper
hello helper，帮我看看这个 bug
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/guide/usage.md
git commit -m "docs: add usage guide (commands reference, deployment scenarios)"
```

---

### Task 5: docs/guide/constraints.md（限制与路线图）

**Files:**
- Create: `docs/guide/constraints.md`
- Source: README.md §Known Constraints + §Roadmap

- [ ] **Step 1: 写入 constraints.md**

```markdown
# 已知限制与路线图

## 已知限制

| 限制 | 影响 | 应对方案 |
|------|------|----------|
| Channel MCP 是 research preview | 必须使用 `--dangerously-load-development-channels` flag | 等待正式发布 |
| Claude Code 需要登录 | 不支持 API key 认证 | 使用 claude.ai 账号 |
| `--dangerously-skip-permissions` | Claude 无需确认即可执行文件操作 | 仅在信任环境使用 |
| Zenoh Python + WeeChat .so | 部分系统上可能存在动态库冲突 | 计划中：Zenoh sidecar 进程 |
| 无跨 session 历史 | 重启后消息丢失 | WeeChat logger 自动保存本地；未来接入 zenohd storage |

## 路线图

- **Agent 间通信** — Agent 通过 private topic 直接协作
- **zenohd + storage backend** — 接入持久化后端，提供跨 session 消息历史
- **飞书桥接** — 飞书作为另一个 Zenoh 节点，复用消息总线
- **Ed25519 签名** — 消息签名验证，防止冒充
- **Web UI** — 通过 WeeChat relay API 暴露 Web 前端
```

- [ ] **Step 2: Commit**

```bash
git add docs/guide/constraints.md
git commit -m "docs: add constraints and roadmap"
```

---

## Chunk 2: 开发文档

### Task 6: docs/dev/architecture.md（架构与协议）

**Files:**
- Create: `docs/dev/architecture.md`
- Source: README.md §Architecture + §Message Protocol + PRD §3.2 + §3.5

- [ ] **Step 1: 写入 architecture.md**

```markdown
# 架构与协议

## 设计原则

**关注点分离**：三个组件通过 Zenoh topic 约定通信，互不知道对方的实现细节。weechat-zenoh 不知道 Claude Code 的存在；channel-server 不知道 WeeChat 的存在。Zenoh topic 约定是唯一的耦合点。

## 系统架构

三个独立可组合的组件：

| 组件 | 类型 | 职责 |
|------|------|------|
| **weechat-zenoh** | WeeChat Python 插件 | P2P channel/private 通信，在线状态追踪。对所有参与者一视同仁 |
| **weechat-channel-server** | Claude Code plugin (MCP server) | 桥接 Claude Code ↔ Zenoh。只知道 Zenoh topic 和 MCP 协议 |
| **weechat-agent** | WeeChat Python 插件 | Agent 生命周期管理。通过 WeeChat 命令和 signal 与 weechat-zenoh 交互 |

## 消息协议

所有消息是 JSON 格式，通过 Zenoh pub/sub 传输：

```json
{
  "id": "uuid-v4",
  "nick": "alice",
  "type": "msg",
  "body": "hello everyone",
  "ts": 1711036800.123
}
```

**消息类型 (`type`)**：

| 类型 | 说明 |
|------|------|
| `msg` | 普通消息 |
| `action` | /me 动作（如 `/me waves`） |
| `join` | 加入 channel |
| `leave` | 离开 channel |
| `nick` | 昵称变更 |

## Zenoh Topic 层级

```
wc/
├── channels/{channel_id}/
│   ├── messages                  # channel 消息 (pub/sub)
│   └── presence/{nick}           # channel 成员在线状态 (liveliness)
├── private/{sorted_pair}/
│   └── messages                  # private 消息 (pair 按字母序排列，如 alice_bob)
└── presence/{nick}               # 全局在线状态 (liveliness)
```

**关键设计**：Agent 的回复走和普通用户完全相同的 topic。weechat-zenoh 收到消息后不区分是人类还是 Agent 发的——只看 `nick` 字段。

## Signal 约定

weechat-zenoh 通过 WeeChat signal 机制暴露事件给其他插件（如 weechat-agent）：

```python
# 收到消息时
weechat.hook_signal_send("zenoh_message_received",
    weechat.WEECHAT_HOOK_SIGNAL_STRING,
    json.dumps({"buffer": "channel:#team", "nick": "alice", "body": "hello"}))

# 在线状态变化时
weechat.hook_signal_send("zenoh_presence_changed",
    weechat.WEECHAT_HOOK_SIGNAL_STRING,
    json.dumps({"nick": "bob", "online": True}))
```

`buffer` 字段格式：`channel:#name` 或 `private:@nick`。

## 组件间通信流

一条消息从用户输入到 Agent 回复的完整路径：

```
1. 用户在 WeeChat buffer 输入消息
2. weechat-zenoh buffer_input_cb() 触发
3. → _publish_event() 序列化为 JSON，通过 Zenoh put() 发布到对应 topic
4. → hook_signal_send("zenoh_message_received") 广播给其他插件

5. channel-server 的 Zenoh subscriber 收到消息
6. → on_private() / on_channel() 回调，过滤自身消息、检查 @mention
7. → 入队到 asyncio.Queue（非阻塞，通过 call_soon_threadsafe 桥接）
8. → poll_zenoh_queue() 出队
9. → inject_message() 构造 MCP notification，写入 write_stream

10. Claude Code 收到 notification，处理后调用 reply() tool
11. → reply() 通过 Zenoh put() 发布回复到对应 topic

12. weechat-zenoh subscriber 收到回复
13. → poll_queues_cb() (50ms timer) 出队，渲染到 WeeChat buffer
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/dev/architecture.md
git commit -m "docs: add architecture and protocol reference"
```

---

### Task 7: docs/dev/weechat-zenoh.md

**Files:**
- Create: `docs/dev/weechat-zenoh.md`
- Source: PRD §3.1 + §3.6 + 代码结构

- [ ] **Step 1: 写入 weechat-zenoh.md**

```markdown
# weechat-zenoh 开发文档

## 定位

WeeChat 的 Zenoh P2P 聊天基础设施。提供 channel/private 管理、消息收发、在线状态追踪。**不知道 Claude Code 的存在**——任何 Zenoh 节点（人类、Agent、bot）对它而言都是平等的 participant。

## 文件结构

```
weechat-zenoh/
├── weechat-zenoh.py    # 主插件（WeeChat 加载入口）
└── helpers.py          # 纯函数工具集（可独立测试）
```

## 核心模块

### weechat-zenoh.py

| 函数 | 职责 |
|------|------|
| `zc_init()` | 初始化 Zenoh session、设置 nick、声明全局 liveliness token、注册 poll timer |
| `zc_deinit()` | 清理所有 token/subscriber/publisher，关闭 session |
| `join_channel(channel_id)` | 创建 buffer、订阅消息、声明 liveliness 和 presence 监控 |
| `join_private(target_nick)` | 创建 private buffer（pair 按字母序排列） |
| `leave_channel()` / `leave_private()` | 通过 `_cleanup_key()` 清理资源 |
| `_publish_event(pub_key, msg_type, body)` | 序列化消息为 JSON，通过 Zenoh pub 发送 |
| `buffer_input_cb()` | 用户输入回调——解析 `/me`、发布消息、发送 signal |
| `_on_channel_msg()` / `_on_private_msg()` | Zenoh 消息回调 → 入队到 `msg_queue` |
| `_on_channel_presence()` | Zenoh liveliness 回调 → 入队到 `presence_queue` |
| `poll_queues_cb()` | 50ms timer 回调——出队、渲染到 buffer、发送 signal |
| `zenoh_cmd_cb()` | `/zenoh` 命令分发器 |

### helpers.py

| 函数 | 职责 |
|------|------|
| `build_zenoh_config(connect)` | 构造 Zenoh client config（默认连接 `tcp/127.0.0.1:7447`） |
| `target_to_buffer_label(target, my_nick)` | 内部 key → WeeChat buffer label 转换 |
| `parse_input(input_data)` | 检测 `/me` 前缀，返回 `(msg_type, body)` |

## 扩展点

**添加新命令**：在 `zenoh_cmd_cb()` 的分发逻辑中添加分支。

**监听消息事件**：其他 WeeChat 插件可以 hook signal：

```python
weechat.hook_signal("zenoh_message_received", "my_callback", "")
weechat.hook_signal("zenoh_presence_changed", "my_callback", "")
```

Signal 的 payload 是 JSON string，格式见 [架构与协议](architecture.md#signal-约定)。

## 注意事项

- **WeeChat callback 不能阻塞** — Zenoh 回调运行在 Zenoh 线程中，不能直接调用 WeeChat API。必须通过 deque 入队，由 timer callback (`poll_queues_cb`) 在 WeeChat 主线程中出队处理。
- **50ms poll 间隔** — 消息延迟上限 50ms，在此频率下 CPU 开销极低。
- **Nick 变更广播** — `/zenoh nick` 会向所有已加入的 channel 发布 `nick` 类型事件，并重新声明所有 liveliness token。
```

- [ ] **Step 2: Commit**

```bash
git add docs/dev/weechat-zenoh.md
git commit -m "docs: add weechat-zenoh component dev docs"
```

---

### Task 8: docs/dev/channel-server.md

**Files:**
- Create: `docs/dev/channel-server.md`
- Source: PRD §4.1-4.5 + CLAUDE.md "Adding MCP Tools"

- [ ] **Step 1: 写入 channel-server.md**

```markdown
# weechat-channel-server 开发文档

## 定位

Claude Code 的 Channel MCP server（以 Claude Code plugin 形式运行）。它是 Claude Code 的子进程，通过 stdio 与 Claude Code 通信（MCP 协议），通过 Zenoh pub/sub 与任意 Zenoh 节点通信。**不知道 WeeChat 的存在**——只知道 Zenoh topic 和 MCP 协议。

## 文件结构

```
weechat-channel-server/
├── .claude-plugin/
│   └── plugin.json           # Claude Code plugin 元数据
├── .mcp.json                 # MCP 配置
├── pyproject.toml             # 依赖声明
├── server.py                  # MCP server + Zenoh bridge（主入口）
├── tools.py                   # MCP tool 定义（目前为空，逻辑在 server.py）
├── message.py                 # 消息工具集（dedup、mention、chunking）
├── skills/                    # Agent skills 目录
└── README.md                  # 组件说明
```

## 核心模块

### server.py

MCP server 主入口。使用 `mcp.server.lowlevel.Server`（非 FastMCP）以支持 notification injection。

| 函数 | 职责 |
|------|------|
| `create_server()` | MCP Server 工厂 |
| `register_tools(server, zenoh_session)` | 注册 MCP tool handler |
| `setup_zenoh(queue, loop)` | 初始化 Zenoh session、注册 subscriber、声明 liveliness |
| `inject_message(write_stream, msg, context)` | 构造 MCP notification（`notifications/claude/channel`），写入 write_stream |
| `poll_zenoh_queue(queue, write_stream)` | async 循环：从 queue 出队，调用 inject_message |

**MCP Tools**：

| Tool | 说明 |
|------|------|
| `reply(chat_id, text)` | 回复消息。text 会经过 `chunk_message()` 分段，发布到对应 Zenoh topic |
| `join_channel(channel_name)` | 加入 channel，声明 liveliness presence token |

### message.py

| 函数/类 | 职责 |
|---------|------|
| `MessageDedup` | 基于 OrderedDict 的 LRU 去重（容量 500） |
| `detect_mention(body, agent_name)` | 检测消息中是否 @mention 了指定 agent |
| `clean_mention(body, agent_name)` | 移除 @mention 文本 |
| `make_private_pair(a, b)` | 按字母序生成 pair key（如 `alice_bob`） |
| `private_topic(pair)` | → `wc/private/{pair}/messages` |
| `channel_topic(channel_id)` | → `wc/channels/{channel_id}/messages` |
| `presence_topic(nick)` | → `wc/presence/{nick}` |
| `chunk_message(text, max_length)` | 按段落/行/空格边界分段（默认 4000 字符） |

## 关键实现细节

### Notification Injection

Channel MCP 要求 server 能主动向 Claude Code 推送消息。FastMCP 不支持这一点，因此使用 `mcp.server.lowlevel.Server`，直接向 `write_stream` 写入 `SessionMessage(JSONRPCNotification(...))`。

### Zenoh → Async 桥接

Zenoh subscriber 回调运行在 Zenoh 的后台线程中，而 MCP server 运行在 asyncio event loop 中。桥接方式：

1. Zenoh callback 将消息放入 `asyncio.Queue`（通过 `loop.call_soon_threadsafe(queue.put_nowait, msg)`）
2. `poll_zenoh_queue()` 在 async 循环中 `await queue.get()`
3. 两者通过 `anyio.create_task_group` 并发运行

### 消息过滤

- **Private**：只接收 pair 中包含自己 agent name 的消息；过滤自身发出的消息；LRU 去重
- **Channel**：只处理 @mention 自己的消息；清除 mention 文本；首次收到某 channel 消息时自动 join presence

## 添加 MCP Tool

1. 在 `server.py` 的 `register_tools()` 中添加 `@server.call_tool()` handler
2. 添加对应的 `@server.list_tools()` entry
3. 在 `tests/unit/test_tools.py` 添加测试

## 独立使用

不需要 weechat-agent 管理器即可运行：

```bash
cd weechat-channel-server
claude --dangerously-load-development-channels plugin:weechat-channel
```

此时 agent0 已在 Zenoh 网络上，任何运行 weechat-zenoh 的 WeeChat 实例都可以 `/zenoh join @agent0` 与之对话。
```

- [ ] **Step 2: Commit**

```bash
git add docs/dev/channel-server.md
git commit -m "docs: add channel-server component dev docs"
```

---

### Task 9: docs/dev/agent.md

**Files:**
- Create: `docs/dev/agent.md`
- Source: PRD §5.1-5.4

- [ ] **Step 1: 写入 agent.md**

```markdown
# weechat-agent 开发文档

## 定位

Claude Code Agent 生命周期管理插件。它是 weechat-zenoh 的上层消费者，通过 WeeChat 命令和 signal 与 weechat-zenoh 交互。负责启动/停止 Claude Code 进程、管理 tmux pane。

**不直接调用 Zenoh API** — 所有通信都通过 weechat-zenoh 的命令和 signal 完成。

## 文件结构

```
weechat-agent/
└── weechat-agent.py    # 主插件
```

## 核心模块

| 函数 | 职责 |
|------|------|
| `agent_init()` | 注册 agent0（start.sh 预创建）、hook signal |
| `create_agent(name, workspace)` | 在 tmux 中创建新 pane，启动 Claude Code + channel plugin，记录 pane_id |
| `stop_agent(name)` | 向指定 pane_id 发送 `C-c` 终止进程（agent0 不可停止） |
| `on_message_signal_cb()` | 监听 `zenoh_message_received`，解析 Agent 的结构化命令输出 |
| `on_presence_signal_cb()` | 监听 `zenoh_presence_changed`，追踪 Agent 在线状态 |
| `agent_cmd_cb()` | `/agent` 命令分发器 |

## 与 weechat-zenoh 的交互

```python
# 创建 private buffer → 执行 weechat-zenoh 命令
weechat.command("", "/zenoh join @agent0")

# 监听消息
weechat.hook_signal("zenoh_message_received", "on_msg_signal_cb", "")

# 发送消息给 agent
weechat.command("", "/zenoh send @agent0 hello")
```

## tmux Pane 管理

每个 Agent 在独立的 tmux pane 中运行：

- `create_agent()` 使用 `tmux split-window -P -F '#{pane_id}'` 创建 pane 并捕获 pane_id
- Agent 信息存储在 `agents[name] = {"workspace": ..., "status": ..., "pane_id": ...}`
- `stop_agent()` 使用 `tmux send-keys -t {pane_id} C-c` 定向终止，不会影响其他 pane

## agent0 特殊性

- 由 `start.sh` 创建，不通过 `create_agent()` 流程
- `/agent stop agent0` 会被拒绝
- 重启系统时通过 `./start.sh` 重新创建
```

- [ ] **Step 2: Commit**

```bash
git add docs/dev/agent.md
git commit -m "docs: add weechat-agent component dev docs"
```

---

### Task 10: docs/dev/testing.md

**Files:**
- Create: `docs/dev/testing.md`
- Source: README.md §Testing + PR#1 docs/manual-testing.md + CLAUDE.md §Testing

- [ ] **Step 1: 写入 testing.md**

```markdown
# 测试

## 测试架构

| 类型 | 目录 | 特点 |
|------|------|------|
| Unit | `tests/unit/` | Mock Zenoh session，快速，无外部依赖 |
| Integration | `tests/integration/` | 真实 Zenoh peer session，需要 zenohd 运行 |

## 运行测试

```bash
# 全部测试
pytest

# 仅 unit 测试（快速）
pytest tests/unit/

# 仅 integration 测试（需要 zenohd 在 localhost:7447 运行）
pytest -m integration tests/integration/

# 单个测试
pytest tests/unit/test_message.py::test_specific -v
```

## Fixture 说明

### Unit Test Fixture（`tests/conftest.py`）

`MockZenohSession` 提供：

- `put()` — 记录发布的消息到 `published` 列表
- `declare_publisher()` / `declare_subscriber()` — 返回 mock 对象
- `liveliness()` — 返回 mock liveliness 支持

使用方式：

```python
def test_something(mock_zenoh_session):
    # mock_zenoh_session 是 MockZenohSession 实例
    # 调用后检查 mock_zenoh_session.published
```

### Integration Test Fixture（`tests/integration/conftest.py`）

- `zenoh_session` — 单个 client 模式 Zenoh session（连接 `tcp/127.0.0.1:7447`）
- `zenoh_sessions` — 两个 session，用于测试 pub/sub 通信

前提：需要 zenohd 运行在 localhost:7447。

## 添加测试

### Unit Test

- 放在 `tests/unit/` 下
- 文件命名：`test_<模块名>.py`
- 使用 `mock_zenoh_session` fixture
- 异步测试自动支持（`asyncio_mode = auto`）

### Integration Test

- 放在 `tests/integration/` 下
- 使用 `@pytest.mark.integration` 标记
- 使用 `zenoh_session` / `zenoh_sessions` fixture

## 手动测试指南

以下测试需要完整的 WeeChat + Claude Code + tmux 运行时，无法自动化。

### Phase 1：基础设施

1. **start.sh 依赖安装** — 运行 `./start.sh`，确认 `uv pip install --system` 被使用
2. **zenohd 启动** — 确认 zenohd 在 7447 端口运行

### Phase 2：weechat-zenoh

1. **`/me` action** — 输入 `/me waves`，确认对方收到 action 类型消息
2. **Nick 变更** — `/zenoh nick newname`，确认所有 channel 收到 nick 变更广播
3. **Private 警告** — 向不在线的用户发起 private，确认显示离线提示
4. **Status 增强** — `/zenoh status` 应显示 zid、peers、routers

### Phase 3：Channel Server

1. **Private 消息桥接** — 用户发消息给 agent0，确认 Claude Code 收到 MCP notification
2. **Channel @mention** — 在 channel 中 `@agent0 help`，确认 agent 只响应被 mention 的消息
3. **Presence** — agent join channel 后，确认 nicklist 显示 agent

### Phase 4：Agent 管理

1. **多 Agent pane** — `/agent create helper`，确认新 tmux pane 创建
2. **定向 stop** — `/agent stop helper`，确认只终止对应 pane
3. **Restart** — `/agent restart helper`，确认重启成功

### Phase 5：zenohd 生命周期

1. **共享 zenohd** — 多用户场景下确认 `./stop.sh` 不会误杀其他用户的 zenohd
```

- [ ] **Step 2: Commit**

```bash
git add docs/dev/testing.md
git commit -m "docs: add testing guide (unit, integration, manual)"
```

---

## Chunk 3: 设计决策文档 + 清理

### Task 11: docs/design-decisions.md（PRD 瘦身）

**Files:**
- Create: `docs/design-decisions.md`
- Delete: `docs/PRD.md`
- Source: PRD §1, §2(表格), §9, §10

- [ ] **Step 1: 写入 design-decisions.md**

从当前 PRD.md 提取 §1, §2 表格, §9, §10，更新术语（room→channel, dm→private），删除所有 what 层面的细节。

```markdown
# 设计决策记录

本文档记录 WeeChat-Claude 的设计原则、tradeoff 和关键决策。具体的实现细节、命令参考和协议规范分别在 [用户文档](guide/) 和 [开发文档](dev/) 中。

-----

## 产品概述

### 一句话描述

一个由三个独立组件构成的本地/局域网多 Agent 协作系统：WeeChat 用户通过 Zenoh P2P 消息总线，与一个或多个 Claude Code 实例进行实时对话、任务分配和协作编程。

### 问题陈述

Claude Code Channels（research preview, 2026-03-20）支持 Telegram/Discord 作为消息桥接，但对以下场景不够理想：

- **本地/LAN 优先** — 不依赖外部平台，数据不出本机/内网
- **多 Agent 管理** — 同时运行和管理多个 Claude Code 实例
- **终端原生** — 在 tmux/terminal 中完成一切
- **可组合** — 各组件独立使用，不强制绑定

### 设计原则

**关注点分离**：三个组件通过 Zenoh topic 约定通信，互不知道对方的实现细节。

-----

## 组件总览

| 组件 | 类型 | 语言 | 运行方式 | 依赖 |
|------|------|------|----------|------|
| **weechat-zenoh** | WeeChat Python 脚本 | Python | `/python load` | eclipse-zenoh |
| **weechat-agent** | WeeChat Python 脚本 | Python | `/python load` | weechat-zenoh（通过 WeeChat 命令交互） |
| **weechat-channel-server** | Python MCP server (Claude Code plugin) | Python | Claude Code plugin | mcp, eclipse-zenoh |

-----

## 约束与 Tradeoff

| 约束 | 影响 | 决策 |
|------|------|------|
| Channel MCP 是 research preview | 必须用 `--dangerously-load-development-channels` | 接受，等正式发布后移除 |
| Claude Code 需要 claude.ai 登录 | 不支持 API key | 接受现状 |
| `--dangerously-skip-permissions` | Claude 无确认执行文件操作 | 仅限信任环境 |
| Zenoh Python + WeeChat .so 可能冲突 | 部分系统上动态库加载失败 | Plan B：Zenoh sidecar 进程 |
| 无跨 session 历史 | 重启后消息丢失 | WeeChat logger 本地保存 + 未来接入 zenohd storage |

-----

## 未来演进

| 方向 | 描述 |
|------|------|
| **Agent 间通信** | Agent A 通过 private topic 与 Agent B 直接协作 |
| **zenohd + storage** | 接入 filesystem backend，跨 session 消息历史 |
| **飞书桥接** | 复用 Zenoh 总线，飞书作为另一个 Zenoh 节点 |
| **Ed25519 身份** | 消息签名验证，防冒充 |
| **Socialware** | Channel → Slot, Agent role → Kit, Capability 权限 |
| **Web UI** | WeeChat relay API 暴露 Web 前端 |
```

- [ ] **Step 2: 删除 PRD.md**

```bash
git rm docs/PRD.md
```

- [ ] **Step 3: Commit**

```bash
git add docs/design-decisions.md
git commit -m "docs: replace PRD with slim design-decisions record"
```

---

### Task 12: 删除 README_zh.md + 更新 CLAUDE.md

**Files:**
- Delete: `README_zh.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: 删除 README_zh.md**

```bash
git rm README_zh.md
```

- [ ] **Step 2: 更新 CLAUDE.md**

将 CLAUDE.md 更新为：

```markdown
# WeeChat-Claude

多 Agent 协作系统：WeeChat ↔ Zenoh P2P ↔ Claude Code (MCP)。

## 架构

三个可组合组件，通过 Zenoh topic 约定连接：
- `weechat-zenoh/weechat-zenoh.py` — WeeChat P2P 聊天插件（详见 [docs/dev/weechat-zenoh.md](docs/dev/weechat-zenoh.md)）
- `weechat-channel-server/` — MCP server 桥接 Claude Code ↔ Zenoh（详见 [docs/dev/channel-server.md](docs/dev/channel-server.md)）
- `weechat-agent/weechat-agent.py` — Agent 生命周期管理（详见 [docs/dev/agent.md](docs/dev/agent.md)）

## Zenoh Topics

- `wc/channels/{channel_id}/messages` — channel pub/sub
- `wc/channels/{channel_id}/presence/{nick}` — channel presence (liveliness)
- `wc/private/{sorted_pair}/messages` — private pub/sub（按字母序排列，如 `alice_bob`）
- `wc/presence/{nick}` — 全局在线状态

消息格式：JSON `{id, nick, type, body, ts}`

## 开发

### 常用命令

```bash
./start.sh ~/workspace username    # 完整系统启动（tmux + agent0 + weechat）
./stop.sh                          # 停止 tmux session
pytest tests/unit/                 # Unit 测试（mock Zenoh，快）
pytest -m integration tests/       # Integration 测试（真实 Zenoh peer）
```

### 依赖

- `eclipse-zenoh` ≥1.0.0 — P2P 消息
- `mcp[cli]` ≥1.2.0 — MCP server 框架
- `uv` — Python 依赖管理
- `tmux` — Session/pane 管理

### 测试

详见 [docs/dev/testing.md](docs/dev/testing.md)

### 添加 MCP Tool

详见 [docs/dev/channel-server.md](docs/dev/channel-server.md#添加-mcp-tool)

### 关键约束

- Channel MCP 需要 `--dangerously-load-development-channels` flag
- `agent0` 由 start.sh 创建，不能通过 `/agent stop` 停止
- WeeChat callback 不能阻塞 — 使用 deque + timer 实现异步
- Zenoh Python + WeeChat .so 可能冲突 — 计划使用 sidecar 进程
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with new doc paths and channel/private terminology"
```

---

### Task 13: 移动 superpowers 过程文档

**注意**：此 task 仅在 PR #1 合入后的分支上执行。当前 main 分支上 `docs/specs/` 和 `docs/plans/` 不存在。

**Files:**
- Move: `docs/specs/*` → `docs/superpowers/specs/`
- Move: `docs/plans/*` → `docs/superpowers/plans/`
- Delete: `docs/manual-testing.md`（内容已合入 `docs/dev/testing.md`）

- [ ] **Step 1: 移动文件**

```bash
# 仅当 docs/specs/ 和 docs/plans/ 存在时执行
git mv docs/specs/* docs/superpowers/specs/ 2>/dev/null || true
git mv docs/plans/* docs/superpowers/plans/ 2>/dev/null || true
git rm docs/manual-testing.md 2>/dev/null || true
rmdir docs/specs docs/plans 2>/dev/null || true
```

- [ ] **Step 2: Commit**

```bash
git add -A docs/superpowers/ docs/specs docs/plans docs/manual-testing.md
git commit -m "docs: move process docs to superpowers/, remove manual-testing.md"
```
