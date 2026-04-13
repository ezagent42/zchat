# 第三章：channel-server 通信详解

> 预计阅读：35 分钟
>
> 基础概念参见 [旧版第三章](../introduce/03-channel-server.md)。本章深入通信机制和消息处理细节。

## 为什么这是最重要的组件

channel-server 是 zchat 的**通信枢纽**。它解决了一个核心问题：

> Claude Code 只会 MCP（stdin/stdout JSON-RPC），IRC 只会 PRIVMSG。如何让它们对话？

答案是一个**双线程桥接进程**，每个 agent 运行一个独立实例。

## 通信模型全景

```
        人类                    Agent
     (WeeChat)            (Claude Code)
        │                       │
        │ IRC PRIVMSG           │ MCP JSON-RPC
        │                       │
        ▼                       ▼
┌──────────────┐        ┌──────────────┐
│  ergo IRC    │        │  MCP Server  │
│  Server      │        │  (stdio)     │
└──────┬───────┘        └──────┬───────┘
       │                       │
       │    channel-server     │
       │  ┌─────────────────┐  │
       └──│  IRC Thread     │  │
          │  (Reactor)      │  │
          │       │         │  │
          │  asyncio.Queue  │──┘
          │       │         │
          │  Async Thread   │
          │  (MCP + Poll)   │
          └─────────────────┘
```

## 双线程模型

### 为什么需要两个线程

| 组件 | 执行模型 | 原因 |
|------|----------|------|
| IRC 库 (`irc.client.Reactor`) | 阻塞式事件循环 | 第三方库设计如此，`process_forever()` 不返回 |
| MCP Server | asyncio 协程 | Claude Code MCP 协议要求 async |

两个不兼容的事件循环，必须分开。

### 线程安全桥接

```python
# 从 IRC 线程投递到 async 线程
# ❌ 错误——跨线程直接操作 asyncio 对象不安全
queue.put_nowait(msg)

# ✅ 正确——通过 event loop 调度
loop.call_soon_threadsafe(queue.put_nowait, (msg, target))
```

`call_soon_threadsafe()` 是 Python asyncio 提供的唯一线程安全入口。它将操作注册到 event loop 的**唤醒队列**，由 async 线程在下一个 tick 执行。

> 代码位置：`zchat-channel-server/server.py:130`

### 数据流向

```
IRC 消息进入:
  IRC Thread: on_pubmsg() / on_privmsg()
    → 过滤（忽略自己、检查 @mention）
    → 构造 msg dict
    → loop.call_soon_threadsafe(queue.put_nowait, (msg, target))
    
Async Thread: poll_irc_queue()
    → await queue.get()
    → inject_message(write_stream, msg, target)
    → MCP JSONRPCNotification → Claude Code

Claude 回复:
  Async Thread: MCP tool call "reply"
    → _handle_reply(connection, arguments)
    → connection.privmsg(chat_id, chunk)
    → IRC Thread 的 connection 对象直接发送
    
⚠️ 注意：reply 方向没有用队列——irc.client 的 connection.privmsg()
   本身是线程安全的（内部有锁）。
```

## 消息过滤机制

### 频道消息：@mention 检测

Agent 不处理频道中的所有消息——只处理被 `@` 提及的。这是关键设计：

```python
# zchat-channel-server/message.py
def detect_mention(body: str, agent_name: str) -> bool:
    """检测消息是否 @mention 了指定 agent"""
    patterns = [
        f"@{agent_name}",           # @alice-agent0
        f"@{agent_name.lower()}",   # 大小写不敏感
    ]
    return any(p in body.lower() for p in patterns)

def clean_mention(body: str, agent_name: str) -> str:
    """去掉 @mention 前缀，保留实际消息内容"""
    # "@alice-agent0 帮我看看" → "帮我看看"
```

**设计原因**：
- 避免消息风暴——频道可能有大量不相关对话
- 明确意图——只有显式 @mention 才触发 agent 响应
- 多 agent 共存——同一频道的多个 agent 各自只响应自己的 mention

### 私聊消息：直接转发

私聊不需要 @mention 检测——发给你就是给你的。但需要先检查是否是系统消息：

```python
def on_privmsg(connection, event):
    body = event.arguments[0]
    
    # 优先检查系统消息
    sys_msg = decode_sys_from_irc(body)
    if sys_msg:
        _handle_sys_message(sys_msg, ...)
        return
    
    # 普通私聊 → 转发给 Claude
    queue.put_nowait((msg, nick))
```

### 系统消息：机器间通信

系统消息通过 IRC PRIVMSG 传输，但有 `__zchat_sys:` 前缀标识：

```
PRIVMSG alice-agent0 :__zchat_sys:{"type":"sys.stop_request","id":"abc123"}
```

这是一个**带内信令**设计——控制消息和数据消息走同一通道，通过前缀区分。

| 消息类型 | 方向 | 用途 |
|----------|------|------|
| `sys.stop_request` | CLI → Agent | 请求停止 |
| `sys.stop_confirmed` | Agent → CLI | 确认停止 |
| `sys.join_request` | CLI → Agent | 请求加入频道 |
| `sys.join_confirmed` | Agent → CLI | 确认加入 |
| `sys.status_request` | CLI → Agent | 查询状态 |
| `sys.status_response` | Agent → CLI | 返回状态 |

## MCP 通知格式

IRC 消息经过 channel-server 转换后，以 MCP Notification 形式到达 Claude Code：

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/claude/channel",
  "params": {
    "content": "帮我看看 main.py",
    "meta": {
      "chat_id": "#general",
      "message_id": "a1b2c3",
      "user": "alice",
      "ts": "2026-04-08T12:00:00Z"
    }
  }
}
```

Claude Code 内部将其渲染为：

```xml
<channel source="zchat-channel" chat_id="#general" user="alice" ts="...">
帮我看看 main.py
</channel>
```

`chat_id` 的语义：
- `#general` → 来自频道，reply 时发回频道
- `alice` → 来自私聊，reply 时发给个人

## MCP 工具

### reply — 回复消息

```python
def _handle_reply(connection, arguments):
    chat_id = arguments["chat_id"]   # "#general" 或 "alice"
    text = arguments["text"]
    
    # 长消息分片（IRC 有长度限制）
    chunks = chunk_message(text, 4000)
    for chunk in chunks:
        connection.privmsg(chat_id, chunk)
```

**消息分片策略**（`message.py`）：

```
消息 > 4000 字符时：
  1. 优先在 "\n\n"（段落）处断开
  2. 其次在 "\n"（换行）处断开
  3. 再次在 " "（空格）处断开
  4. 最后硬切
```

### join_channel — 加入频道

```python
def _handle_join_channel(connection, arguments):
    channel = f"#{arguments['channel_name']}"
    connection.join(channel)
```

### Slash 命令

channel-server 还注册了 slash 命令供 Claude Code 使用：

```
/zchat:reply -c #general -t "message"     # 回复频道
/zchat:dm -u alice -t "private message"   # 私聊
/zchat:join -c dev                        # 加入频道
/zchat:broadcast -t "announcement"        # 广播所有频道
```

> 命令定义在 `zchat-channel-server/commands/` 目录。

## Agent 行为指令（instructions.md）

每个 channel-server 实例启动时加载 `instructions.md`，指导 Claude 如何处理消息：

### 核心行为规则

1. **空闲时**：直接用 `reply` 工具回复
2. **忙碌时**：启动子 agent（Agent tool）处理消息，不中断当前任务
3. **系统消息**：总是直接处理，不交给子 agent
4. **优先级**：Owner DM > 其他 DM > @mention > 系统消息

### soul.md 角色定义

Agent 可以有个性化行为。在 agent 工作空间放一个 `soul.md`：

```markdown
# Soul
你是一个专注于代码审查的 agent。
对每个 PR 提供 3 个改进建议。
用中文回复。
```

channel-server 的 instructions.md 会引导 Claude 在启动时读取此文件。

## IRC 连接管理

### 连接建立

```python
def setup_irc(queue, loop):
    reactor = irc.client.Reactor()
    
    # TLS 支持（远程服务器）
    if IRC_TLS:
        ssl_ctx = ssl.create_default_context()
        wrapper = ssl_ctx.wrap_socket
    
    # SASL 认证（OIDC token）
    if IRC_AUTH_TOKEN:
        conn.set_sasl_credentials(AGENT_NAME, IRC_AUTH_TOKEN)
    
    conn = reactor.server().connect(IRC_SERVER, IRC_PORT, AGENT_NAME, ...)
```

### 断线重连

```python
def on_disconnect(connection, event):
    time.sleep(5)
    connection.reconnect()
```

简单的 5 秒重试。生产环境中 ergo 本身也有 ping/pong 保活机制。

## 完整启动流程

```python
async def main():
    queue = asyncio.Queue()
    loop = asyncio.get_event_loop()
    server = create_server()       # MCP server 实例
    
    await asyncio.sleep(2)         # 等 Claude Code 初始化
    
    conn, joined = setup_irc(queue, loop)  # 启动 IRC（独立线程）
    state = {"connection": conn, "joined_channels": joined}
    register_tools(server, state)
    
    async with anyio.create_task_group() as tg:
        tg.start_soon(server.run, ...)       # MCP server 循环
        tg.start_soon(poll_irc_queue, ...)   # 队列消费者
    
    conn.disconnect("Shutting down")
```

`anyio.create_task_group()` 同时运行 MCP server 和队列消费者。任一退出则全部停止。

## 测试

```bash
cd zchat-channel-server && uv run pytest tests/ -v
```

覆盖：mention 检测、消息分片、系统消息编解码、指令加载。

## 下一步

进入 [第四章：CLI + Zellij 会话管理](./04-cli-and-zellij.md)。
