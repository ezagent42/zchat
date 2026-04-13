# 第三章：zchat-channel-server——MCP ↔ IRC 桥接

> 预计阅读：30 分钟

## 概述

channel-server 是 zchat 的**核心枢纽**。它是一个 MCP（Model Context Protocol）server，运行在每个 agent 进程中，负责：

1. 作为 IRC 客户端连接到 ergo 服务器
2. 监听 IRC 消息，过滤 @mention 和私聊
3. 将 IRC 消息转换为 MCP 通知，推送给 Claude Code
4. 提供 MCP 工具（reply、join_channel），让 Claude Code 能回复 IRC

> 代码位置：`zchat-channel-server/`

## 架构：双线程 + 异步队列

channel-server 使用**混合线程模型**：

```
┌─────────────────────┐     ┌─────────────────────┐
│ IRC 线程（daemon）    │     │ Async 主线程          │
│                     │     │                     │
│ reactor.process_    │     │ ┌─── MCP Server ──┐ │
│   forever()         │     │ │ stdin/stdout     │ │
│                     │     │ │ ↕ Claude Code    │ │
│ on_pubmsg() ────────┼──→  │ └─────────────────┘ │
│ on_privmsg() ───────┼──→  │                     │
│                     │  队列 │ poll_irc_queue()    │
│ IRC event handlers  │     │   ↓                 │
│                     │     │ inject_message()    │
│                     │  ←──┼── reply() tool      │
│ connection.privmsg()│     │                     │
└─────────────────────┘     └─────────────────────┘
```

> 引用：`zchat-channel-server/server.py:171-178`（IRC 线程创建）

### 为什么需要两个线程？

- **IRC 库（`irc.client.Reactor`）** 是阻塞式事件循环，必须在独立线程运行
- **MCP Server** 基于 asyncio，需要 async 事件循环
- `asyncio.Queue` 作为线程安全的桥梁，连接两者

### 线程安全桥接

IRC 线程往 async 队列放消息时，必须用 `call_soon_threadsafe()`：

```python
# zchat-channel-server/server.py:130
loop.call_soon_threadsafe(queue.put_nowait, (msg, target))
```

这是关键的线程安全点——直接调用 `queue.put_nowait()` 在跨线程场景下不安全。

> 引用：`zchat-channel-server/server.py:130`

## 环境配置

channel-server 通过环境变量配置，由 agent 的 start.sh 模板设置：

```python
# zchat-channel-server/server.py:31-36
AGENT_NAME   = os.environ.get("AGENT_NAME", "agent0")
IRC_SERVER   = os.environ.get("IRC_SERVER", "127.0.0.1")
IRC_PORT     = int(os.environ.get("IRC_PORT", "6667"))
IRC_CHANNELS = os.environ.get("IRC_CHANNELS", "general")
IRC_TLS      = os.environ.get("IRC_TLS", "false").lower() == "true"
IRC_AUTH_TOKEN = os.environ.get("IRC_AUTH_TOKEN", "")
```

| 变量 | 默认值 | 用途 |
|------|--------|------|
| `AGENT_NAME` | `agent0` | Agent 的 IRC 昵称 |
| `IRC_SERVER` | `127.0.0.1` | IRC 服务器地址 |
| `IRC_PORT` | `6667` | IRC 服务器端口 |
| `IRC_CHANNELS` | `general` | 自动加入的频道（逗号分隔） |
| `IRC_TLS` | `false` | 是否启用 TLS |
| `IRC_AUTH_TOKEN` | `""` | SASL 认证 token |

> 引用：`zchat-channel-server/server.py:31-36`

## IRC 连接与事件处理

### 连接建立

```python
# zchat-channel-server/server.py:78-94
def setup_irc(queue, loop):
    reactor = irc.client.Reactor()
    # TLS 支持
    if IRC_TLS:
        ssl_ctx = ssl.create_default_context()
        wrapper = ssl_ctx.wrap_socket
    # SASL 认证
    if IRC_AUTH_TOKEN:
        conn.set_sasl_credentials(AGENT_NAME, IRC_AUTH_TOKEN)
    conn = reactor.server().connect(IRC_SERVER, IRC_PORT, AGENT_NAME, ...)
```

> 引用：`zchat-channel-server/server.py:78-94`

### 四个事件处理器

#### 1. on_welcome — 连接成功

```python
# server.py:97-110
def on_welcome(connection, event):
    # 验证昵称是否符合预期
    actual = connection.get_nickname()
    if actual != AGENT_NAME:
        print(f"Warning: nick mismatch", file=sys.stderr)
    # 自动加入频道
    for ch in IRC_CHANNELS.split(","):
        ch = ch.strip()
        if not ch.startswith("#"):
            ch = f"#{ch}"
        connection.join(ch)
```

> 引用：`zchat-channel-server/server.py:97-110`

#### 2. on_pubmsg — 频道消息

这是消息过滤的核心：

```python
# server.py:112-131
def on_pubmsg(connection, event):
    nick = event.source.nick
    body = event.arguments[0]
    
    # 忽略自己的消息
    if nick == AGENT_NAME:
        return
    
    # 只处理 @mention 自己的消息
    if not detect_mention(body, AGENT_NAME):
        return
    
    # 清理 mention 文本
    cleaned = clean_mention(body, AGENT_NAME)
    target = event.target  # #channel
    
    msg = {"id": hex_id, "nick": nick, "type": "msg", "body": cleaned, "ts": time.time()}
    loop.call_soon_threadsafe(queue.put_nowait, (msg, target))
```

**关键设计**：agent 不处理频道中的所有消息，只处理被 `@` 提及的。这避免了消息风暴。

> 引用：`zchat-channel-server/server.py:112-131`

#### 3. on_privmsg — 私聊消息

```python
# server.py:133-154
def on_privmsg(connection, event):
    nick = event.source.nick
    body = event.arguments[0]
    
    if nick == AGENT_NAME:
        return
    
    # 先检查是否是系统消息
    sys_msg = decode_sys_from_irc(body)
    if sys_msg:
        _handle_sys_message(sys_msg, nick, connection, joined_channels)
        return
    
    # 普通私聊消息
    msg = {"id": hex_id, "nick": nick, "type": "msg", "body": body, "ts": time.time()}
    loop.call_soon_threadsafe(queue.put_nowait, (msg, nick))
```

私聊消息不需要 @mention 检测——发给你就是给你的。

> 引用：`zchat-channel-server/server.py:133-154`

#### 4. on_disconnect — 断线重连

```python
# server.py:156-163
def on_disconnect(connection, event):
    time.sleep(5)
    connection.reconnect()
```

> 引用：`zchat-channel-server/server.py:156-163`

## MCP 通知注入

当 IRC 消息通过队列到达 async 侧，`inject_message()` 将其转换为 MCP 通知：

```python
# server.py:43-60
async def inject_message(write_stream, msg, context):
    notification = JSONRPCNotification(
        method="notifications/claude/channel",
        params={
            "content": msg["body"],
            "meta": {
                "chat_id": context,       # "#general" 或 "alice"
                "message_id": msg["id"],
                "user": msg["nick"],
                "ts": iso_timestamp
            }
        }
    )
    await write_stream.send(notification)
```

Claude Code 收到后，消息格式如：

```xml
<channel source="zchat-channel" chat_id="#general" user="alice" ts="2026-04-02T15:20:00Z">
help me debug this function
</channel>
```

> 引用：`zchat-channel-server/server.py:43-60`、`zchat-channel-server/instructions.md`

## MCP 工具

channel-server 注册了两个 MCP 工具，供 Claude Code 调用：

### reply — 回复消息

```python
# server.py:270-278
def _handle_reply(connection, arguments):
    chat_id = arguments["chat_id"]  # "#general" 或 "alice"
    text = arguments["text"]
    
    # 长消息分片
    chunks = chunk_message(text, MAX_MESSAGE_LENGTH)
    for chunk in chunks:
        connection.privmsg(chat_id, chunk)
    
    _msg_counter["sent"] += 1
    return f"Sent to {chat_id}"
```

> 引用：`zchat-channel-server/server.py:270-278`

### join_channel — 加入频道

```python
# server.py:280-283
def _handle_join_channel(connection, arguments):
    channel = f"#{arguments['channel_name']}"
    connection.join(channel)
    return f"Joined {channel}"
```

> 引用：`zchat-channel-server/server.py:280-283`

## 消息分片

IRC 有消息长度限制，channel-server 在 4000 字符处分片：

```python
# zchat-channel-server/message.py:20-48
def chunk_message(text, max_length=MAX_MESSAGE_LENGTH):
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        
        # 尝试在段落、换行、空格处断开
        for sep in ["\n\n", "\n", " "]:
            idx = text.rfind(sep, 0, max_length)
            if idx > 0:
                chunks.append(text[:idx])
                text = text[idx:].lstrip()
                break
        else:
            # 硬切
            chunks.append(text[:max_length])
            text = text[max_length:]
    
    return chunks
```

> 引用：`zchat-channel-server/message.py:20-48`

## Agent 行为指令

channel-server 启动时加载 `instructions.md`，定义了 agent 的行为准则：

```python
# server.py:212-216
def load_instructions(agent_name):
    path = os.path.join(os.path.dirname(__file__), "instructions.md")
    template = Template(open(path).read())
    return template.substitute(agent_name=agent_name)
```

### 关键行为规则

1. **空闲时**：直接用 `reply` 工具回复
2. **忙碌时**：启动子 agent（Agent tool）处理消息，不中断当前任务
3. **系统消息**：总是直接处理
4. **优先级**：Owner DM > 其他 DM > @mention > 系统消息
5. **soul.md**：可选的角色定义文件，自定义 agent 性格

> 引用：`zchat-channel-server/instructions.md`

### 可用的 Slash 命令

agent 可以使用这些 skill 命令：

- `/zchat:reply -c #general -t "message"` — 回复频道或用户
- `/zchat:join -c dev` — 加入频道
- `/zchat:dm -u alice -t "private"` — 发私聊
- `/zchat:broadcast -t "announcement"` — 广播到所有频道

> 引用：`zchat-channel-server/commands/` 目录

## 系统消息处理

```python
# server.py:186-206
def _handle_sys_message(msg, sender_nick, connection, joined_channels):
    if msg["type"] == "sys.stop_request":
        reply = make_sys_message(AGENT_NAME, "sys.stop_confirmed", {}, ref_id=msg["id"])
        connection.privmsg(sender_nick, encode_sys_for_irc(reply))
    
    elif msg["type"] == "sys.join_request":
        channel = msg["body"].get("channel", "")
        connection.join(channel)
        joined_channels.add(channel)
        reply = make_sys_message(AGENT_NAME, "sys.join_confirmed", {"channel": channel}, ref_id=msg["id"])
        connection.privmsg(sender_nick, encode_sys_for_irc(reply))
    
    elif msg["type"] == "sys.status_request":
        reply = make_sys_message(AGENT_NAME, "sys.status_response", {
            "channels": list(joined_channels),
            "messages_sent": _msg_counter["sent"],
            "messages_received": _msg_counter["received"],
        }, ref_id=msg["id"])
        connection.privmsg(sender_nick, encode_sys_for_irc(reply))
```

> 引用：`zchat-channel-server/server.py:186-206`

## 启动流程

```python
# server.py:290-313
async def main():
    queue = asyncio.Queue()        # IRC → async 桥
    loop = asyncio.get_event_loop()
    server = create_server()       # MCP server 实例
    
    # 等待 Claude Code 初始化
    await asyncio.sleep(2)
    
    # 启动 IRC 客户端（在独立线程中）
    conn, joined = setup_irc(queue, loop)
    state = {"connection": conn, "joined_channels": joined}
    register_tools(server, state)
    
    async with anyio.create_task_group() as tg:
        tg.start_soon(server.run, ...)     # MCP server 循环
        tg.start_soon(poll_irc_queue, ...)  # 队列消费者
    
    # 退出时断开 IRC
    conn.disconnect("Shutting down")
```

> 引用：`zchat-channel-server/server.py:290-313`

## 测试

```bash
cd zchat-channel-server && uv run pytest tests/ -v
```

测试覆盖：mention 检测、消息分片、系统消息编解码、指令加载。

> 引用：`zchat-channel-server/tests/test_channel_server.py`

## 下一步

理解了 MCP ↔ IRC 桥接后，进入 [第四章：zchat CLI 项目与配置管理](./04-cli-project.md)。
