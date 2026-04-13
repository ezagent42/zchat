# 第八章：通信全链路深度解析

> 预计阅读：35 分钟
>
> 本章重写 [旧版第八章](../introduce/08-end-to-end.md)，重点深入通信机制。

## 概述

前七章分别讲解了每个组件。本章将它们串联，追踪每一条消息从输入到输出的完整路径，并深入分析通信中的关键设计决策。

## 一、消息全链路追踪

### 场景 1：频道 @mention（最常见）

用户在 WeeChat 输入：`@yaosh-agent0 帮我看看 main.py`

```
时间轴:

T0  用户在 WeeChat 输入
    ┌─────────────────────────────────────────────────────┐
    │ WeeChat → IRC PRIVMSG #general :@yaosh-agent0 ...  │
    └────────────────────────┬────────────────────────────┘
                             │
T1  ergo 路由（< 1ms）        │
    ┌────────────────────────┼────────────────────────────┐
    │ ergo 广播到 #general    │                            │
    │ 所有成员                 ▼                            │
    │  ┌──────────┐  ┌──────────────────┐                 │
    │  │ WeeChat  │  │ yaosh-agent0     │                 │
    │  │ (echo)   │  │ (channel-server) │                 │
    │  └──────────┘  └────────┬─────────┘                 │
    └─────────────────────────┼───────────────────────────┘
                              │
T2  channel-server IRC 线程    │
    ┌─────────────────────────┼───────────────────────────┐
    │ on_pubmsg(event)        │                           │
    │   │                     ▼                           │
    │   ├─ nick == AGENT_NAME?  → 跳过（忽略自己）         │
    │   ├─ detect_mention(body, "yaosh-agent0") → True    │
    │   ├─ clean_mention(body) → "帮我看看 main.py"       │
    │   └─ loop.call_soon_threadsafe(                     │
    │         queue.put_nowait,                            │
    │         (msg, "#general")                            │
    │       )                                             │
    └─────────────────────────┬───────────────────────────┘
                              │ asyncio.Queue
T3  channel-server async 线程  │
    ┌─────────────────────────┼───────────────────────────┐
    │ poll_irc_queue():       │                           │
    │   msg, target = await queue.get()                   │
    │   await inject_message(write_stream, msg, target)   │
    │                         │                           │
    │ inject_message():       │                           │
    │   notification = JSONRPCNotification(               │
    │     method="notifications/claude/channel",          │
    │     params={                                        │
    │       "content": "帮我看看 main.py",                │
    │       "meta": {                                     │
    │         "chat_id": "#general",                      │
    │         "user": "yaosh",                            │
    │         "message_id": "a1b2c3",                     │
    │       }                                             │
    │     }                                               │
    │   )                                                 │
    │   await write_stream.send(notification)             │
    └─────────────────────────┬───────────────────────────┘
                              │ MCP stdio (stdout)
T4  Claude Code 接收           │
    ┌─────────────────────────┼───────────────────────────┐
    │ 渲染为：                 ▼                           │
    │ <channel chat_id="#general" user="yaosh">            │
    │   帮我看看 main.py                                   │
    │ </channel>                                          │
    │                                                     │
    │ Claude 处理 → 读取 main.py → 构造回复                │
    │                                                     │
    │ 调用 MCP tool:                                      │
    │   reply(chat_id="#general", text="main.py 包含...")  │
    └─────────────────────────┬───────────────────────────┘
                              │ MCP tool call (stdin)
T5  channel-server 处理回复    │
    ┌─────────────────────────┼───────────────────────────┐
    │ _handle_reply():        │                           │
    │   chunks = chunk_message(text, 4000)                │
    │   for chunk in chunks:                              │
    │     connection.privmsg("#general", chunk)            │
    └─────────────────────────┬───────────────────────────┘
                              │ IRC PRIVMSG
T6  ergo → WeeChat            │
    ┌─────────────────────────┼───────────────────────────┐
    │ 用户在 #general 看到     ▼                           │
    │ yaosh-agent0: main.py 包含...                       │
    └─────────────────────────────────────────────────────┘
```

**总延迟**：T0→T6 通常 < 2 秒（取决于 Claude 处理时间）。

### 场景 2：私聊

用户输入：`/msg yaosh-agent0 帮我 debug`

```
用户 → PRIVMSG yaosh-agent0 :帮我 debug
  → ergo 直接路由给 yaosh-agent0（不广播）
  → on_privmsg()
  → decode_sys_from_irc() → None（不是系统消息）
  → queue → inject_message(context="yaosh")
     ↑ 注意：context 是发送者 nick，不是 "#channel"
  → Claude 处理
  → reply(chat_id="yaosh", text="好的...")
  → PRIVMSG yaosh :好的...
  → 用户在私聊窗口看到回复
```

**关键区别**：`chat_id` 是用户 nick（`"yaosh"`），不是频道名。reply 时发回给个人。

### 场景 3：Agent 间通信

agent0 想让 helper 帮忙审查代码：

```
agent0 的 Claude Code:
  → 调用 MCP tool: reply(chat_id="#general", text="@yaosh-helper 请审查 PR #42")
  
agent0 的 channel-server:
  → connection.privmsg("#general", "@yaosh-helper 请审查 PR #42")
  
ergo:
  → 广播到 #general 所有成员
  
helper 的 channel-server:
  → on_pubmsg() → detect_mention("@yaosh-helper ...") → True
  → queue → inject_message → Claude Code
  
helper 的 Claude Code:
  → 处理审查请求
  → reply(chat_id="#general", text="@yaosh-agent0 审查完毕，发现 3 个问题...")
```

**设计洞察**：Agent 间通信走的是**完全相同的路径**——没有特殊的 agent-to-agent 通道。这是 IRC 作为通信协议的优势：所有参与者（人和 agent）地位平等。

### 场景 4：系统消息（停止 Agent）

CLI 执行 `zchat agent stop agent0`：

```
AgentManager.stop("agent0"):
  │
  ├─ 1. 加载 template pre_stop hook
  │     pre_stop 命令可能是 "/exit" 或自定义脚本
  │
  ├─ 2. 通过 Zellij 发送到 agent tab
  │     zellij.send_command(session, pane_id, pre_stop)
  │
  ├─ 3. 等待 tab 自行关闭（最多 10s）
  │     Claude Code 收到退出信号 → 优雅关闭
  │
  ├─ 4. 超时 → 强制关闭 tab
  │     zellij.close_tab(session, name)
  │
  ├─ 5. 删除 .ready 标记（保留工作目录）
  │     rm agents/yaosh-agent0.ready
  │
  └─ 6. 更新 state.json
        status: "running" → "offline"
```

## 二、通信协议栈

从底层到顶层：

```
┌──────────────────────────────────────────────────┐
│ 第 5 层：应用语义                                  │
│ "帮我看看 main.py" / soul.md 角色定义             │
├──────────────────────────────────────────────────┤
│ 第 4 层：MCP 通知/工具                             │
│ notifications/claude/channel + reply tool        │
│ JSON-RPC 2.0 over stdio                         │
├──────────────────────────────────────────────────┤
│ 第 3 层：消息转换（channel-server）                 │
│ @mention 检测 / clean_mention / chunk_message    │
│ asyncio.Queue 桥接                               │
├──────────────────────────────────────────────────┤
│ 第 2 层：IRC 协议                                  │
│ PRIVMSG / JOIN / PART / QUIT / NICK             │
│ __zchat_sys: 前缀系统消息                          │
├──────────────────────────────────────────────────┤
│ 第 1 层：传输                                      │
│ TCP 6667（本地）/ TLS 6697（远程 via Caddy）       │
└──────────────────────────────────────────────────┘
```

## 三、消息类型分类

| 类型 | 方向 | IRC 形式 | MCP 形式 | 触发条件 |
|------|------|----------|----------|----------|
| 频道 mention | 人→Agent | `PRIVMSG #ch :@agent msg` | notification | @mention 匹配 |
| 频道普通 | 人→人 | `PRIVMSG #ch :msg` | _(忽略)_ | 无 @mention |
| 私聊 | 人→Agent | `PRIVMSG agent :msg` | notification | 直接发送 |
| 回复 | Agent→频道/人 | `PRIVMSG target :msg` | tool call | Claude 调用 reply |
| 系统消息 | CLI→Agent | `PRIVMSG agent :__zchat_sys:{json}` | _(内部处理)_ | CLI 命令 |
| Presence | 任意 | `JOIN/PART/QUIT` | _(不转发)_ | 加入/离开频道 |

## 四、并发和竞态

### 多 Agent 同频道

```
#general 频道：
  - yaosh-agent0（在线）
  - yaosh-helper（在线）
  - yaosh（人类）

用户发送：@yaosh-agent0 @yaosh-helper 你们都来看看

→ agent0 的 channel-server: detect_mention → True（匹配 agent0）
→ helper 的 channel-server: detect_mention → True（匹配 helper）
→ 两个 agent 同时收到通知，独立处理，各自回复
```

**没有协调机制**——两个 agent 可能同时回复。这是设计选择：
- 简单可靠
- 符合 IRC 的"广播+过滤"模型
- 如果需要协调，通过 soul.md 或 instructions.md 定义协作规则

### 消息顺序

```
IRC 保证：同一连接上的消息是有序的
channel-server 保证：asyncio.Queue 是 FIFO
MCP 保证：stdio 是顺序的

结论：单个 agent 收到的消息顺序与 IRC 上的顺序一致。
但多个 agent 之间没有全局顺序保证。
```

### Queue 背压

如果 Claude 处理慢，queue 会积压：

```
IRC 消息速率 > Claude 处理速率
  → asyncio.Queue 无限增长（默认无上限）
  → 内存压力

当前策略：不限制。实际场景中 @mention 频率不高，不是问题。
未来可能：添加 maxsize + 溢出丢弃策略。
```

## 五、远程协作模式

### 本地模式 vs 远程模式

```
本地模式：
  WeeChat ──TCP──→ ergo (127.0.0.1:6667) ←──TCP── channel-server
  
  全部在本机，延迟 < 1ms。

远程模式：
  WeeChat ──TLS──→ Caddy (:6697) → ergo (:6667) ←──TLS── channel-server
  
  Caddy 提供 TLS 终止 + 反向代理。
  SASL 认证保护连接。
```

### 远程架构

```
┌─ 你的机器 ──────────────────┐     ┌─ 远程服务器 ─────────────┐
│                             │     │                          │
│ WeeChat ──────TLS:6697──────┼────→│ Caddy (TLS 终止)         │
│                             │     │   ↓                      │
│ channel-server ──TLS:6697───┼────→│ ergo (IRC :6667)         │
│                             │     │                          │
│ Claude Code (MCP stdio)     │     │ OIDC auth-script         │
│                             │     │                          │
└─────────────────────────────┘     └──────────────────────────┘
```

远程模式的额外组件：

| 组件 | 位置 | 作用 |
|------|------|------|
| Caddy | 远程服务器 | TLS 终止，`:6697` → `:6667` |
| OIDC auth-script | 远程 ergo | SASL 认证，验证 token |
| `zchat auth login` | 本地 | 获取 OIDC token |

### 认证流程

```
zchat auth login
  → OIDC Device Code Flow
  → 浏览器确认
  → 获取 access_token + refresh_token
  → 保存到 ~/.zchat/auth.json

zchat irc start / agent create
  → 读取 auth.json
  → WeeChat: SASL PLAIN (nick + token)
  → channel-server: IRC_AUTH_TOKEN 环境变量
  
ergo (auth-script):
  → 收到 SASL credentials
  → 调用 OIDC userinfo endpoint 验证 token
  → 通过 → 允许连接
```

## 六、系统启动全流程

```
./start.sh ~/workspace local

1. uv sync
   └─ 同步主项目 + channel-server 依赖

2. zchat project create local（如不存在）
   ├─ 交互式选择 IRC server / channels / agent type
   ├─ 写入 config.toml
   └─ 生成 layout.kdl

3. zchat irc daemon start
   ├─ 检查 127.0.0.1:6667 端口
   ├─ 生成 ergo 配置（从 defaultconfig 修补端口、移除 TLS）
   ├─ 确保 languages 目录存在（本地复制或从 GitHub 下载）
   ├─ 启动 ergo 子进程
   └─ 保存 PID 到 state.json

4. zchat irc start
   ├─ 预检 IRC 连通性
   ├─ 构造 WeeChat 启动命令（server add + autojoin + SASL + plugin）
   ├─ 创建 Zellij "chat" tab
   └─ 保存 tab 信息到 state.json

5. zchat agent create agent0 --workspace ~/workspace
   ├─ scoped_name("agent0", "yaosh") → "yaosh-agent0"
   ├─ 渲染 .zchat-env 环境变量
   ├─ 创建 Zellij "yaosh-agent0" tab
   ├─ 运行 start.sh → 启动 Claude Code + channel-server MCP
   ├─ 后台线程自动确认启动提示
   └─ 等待 SessionStart hook 写入 .ready 文件

6. zellij attach zchat-local
   └─ 进入 Zellij session
```

## 七、系统关闭全流程

```
zchat shutdown / ./stop.sh

1. 停止所有 agent
   ├─ 对每个 running agent:
   │   ├─ 发送 pre_stop hook 命令
   │   ├─ 等待 tab 自行关闭（10s）
   │   ├─ 超时 → 强制 close_tab
   │   └─ 删除 .ready 标记
   └─ 更新 state.json

2. 停止 WeeChat
   ├─ 发送 /quit 到 chat tab
   └─ 更新 state.json

3. 停止 ergo
   ├─ kill 存储的 PID
   └─ 更新 state.json

4. 终止 Zellij session
   └─ zellij kill-session zchat-local
```

## 八、调试通信问题

### 检查 IRC 连通性

```bash
# 能否连上 IRC？
zchat irc status

# 手动测试
nc -zv 127.0.0.1 6667          # 本地
openssl s_client -connect zchat.inside.h2os.cloud:6697  # 远程
```

### 检查 channel-server 日志

Agent tab 中的 stderr 输出包含 channel-server 的日志：
- `Connected to IRC`
- `Joined #general`
- `Mention detected from alice`

```bash
# 切到 agent tab 查看
zchat agent focus agent0
```

### 检查消息流

```bash
# 在 WeeChat 中查看原始 IRC 消息
/set irc.look.display_ctcp_reply on
/debug tags            # 显示消息标签
```

### 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| Agent 不回复 @mention | nick 大小写不匹配 | 检查 `zchat agent list` 的实际 nick |
| 消息截断 | IRC 长度限制 | channel-server 自动分片（4000 字符） |
| 私聊无回复 | Agent 还在 starting | 等待 `.ready` 或检查 agent tab |
| 远程连接失败 | SASL 认证过期 | `zchat auth refresh` |
| 多条重复回复 | 多个 agent 响应同一 mention | 精确 @mention 单个 agent |

## 九、扩展通信能力

### 添加新 MCP 工具

在 `zchat-channel-server/server.py` 的 `register_tools()` 中：

```python
# 1. 在 @server.list_tools() 添加定义
Tool(name="my_tool", description="...", inputSchema={...})

# 2. 在 @server.call_tool() 添加 handler
if name == "my_tool":
    return _handle_my_tool(state["connection"], arguments)

# 3. 实现处理函数
def _handle_my_tool(connection, arguments):
    ...
```

### 添加新 Slash 命令

在 `zchat-channel-server/commands/` 添加 YAML 文件：

```yaml
# commands/my_command.yaml
name: my_command
description: "自定义命令"
parameters:
  - name: target
    type: string
    required: true
```

### soul.md 自定义 Agent 行为

```markdown
# Soul
你是 code-reviewer agent。
收到 @mention 时：
1. 读取提到的文件
2. 给出 3 个改进建议
3. 用中文回复，代码用英文
```

## 十、架构总结

```
┌──────────────────────────────────────────────────────────────┐
│                     用户交互层                                 │
│  WeeChat + zchat.py（/agent 命令、消息渲染、状态栏）            │
├──────────────────────────────────────────────────────────────┤
│                     管理层                                     │
│  zchat CLI (Typer) + Zellij                                  │
│  ├─ ProjectManager (config.toml, layout.kdl)                 │
│  ├─ AgentManager (create/stop/restart, Zellij tabs)          │
│  ├─ IrcManager (ergo daemon, WeeChat)                        │
│  └─ Auth (OIDC device code, token cache)                     │
├──────────────────────────────────────────────────────────────┤
│                     桥接层                                     │
│  zchat-channel-server (MCP Server)                           │
│  ├─ IRC 线程 (irc.client.Reactor)                            │
│  ├─ Async 主线程 (MCP stdio + queue polling)                  │
│  └─ MCP 工具 (reply, join_channel, dm, broadcast)            │
├──────────────────────────────────────────────────────────────┤
│                     协议层                                     │
│  zchat-protocol                                              │
│  ├─ naming (scoped_name, AGENT_SEPARATOR)                    │
│  └─ sys_messages (encode/decode, __zchat_sys: 前缀)          │
├──────────────────────────────────────────────────────────────┤
│                     基础设施层                                  │
│  IRC (ergo) + Zellij + Claude Code CLI                       │
│  本地: TCP:6667  /  远程: TLS:6697 (Caddy → ergo)            │
└──────────────────────────────────────────────────────────────┘
```

## 快速参考

| 我想… | 命令/操作 |
|-------|----------|
| 创建项目 | `zchat project create local` |
| 启动全部 | `./start.sh ~/workspace` |
| 创建 agent | `zchat agent create agent0 --workspace ~/workspace` |
| 在频道对话 | WeeChat: `@yaosh-agent0 你好` |
| 私聊 agent | WeeChat: `/msg yaosh-agent0 hello` |
| 查看 agent 终端 | `zchat agent focus agent0` 或 `Alt+3` |
| 查看状态 | `zchat agent list` |
| 停止全部 | `zchat shutdown` |
| 跑单元测试 | `uv run pytest tests/unit/ -v` |
| 跑 E2E 测试 | `uv run pytest tests/e2e/ -v -m e2e` |
| 添加 MCP 工具 | 编辑 `zchat-channel-server/server.py` |
| 自定义 agent | 在工作空间创建 `soul.md` |
| 远程协作 | `zchat auth login` + 选远程服务器 |
