# weechat-channel-server 开发文档

## 定位

Claude Code 的 Channel MCP server（以 Claude Code plugin 形式运行）。它是 Claude Code 的子进程，通过 stdio 与 Claude Code 通信（MCP 协议），通过 IRC 与 ergo server 通信。**不知道 WeeChat 的存在**——只知道 IRC channel 和 MCP 协议。

## 文件结构

```
weechat-channel-server/
├── .claude-plugin/
│   └── plugin.json           # Claude Code plugin 元数据
├── .mcp.json                 # MCP 配置
├── pyproject.toml             # 依赖声明
├── server.py                  # MCP server + IRC bridge（主入口）
├── tools.py                   # MCP tool 定义
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
| `register_tools(server, irc_client)` | 注册 MCP tool handler |
| `inject_message(write_stream, msg, context)` | 构造 MCP notification（`notifications/claude/channel`），通过 `write_stream.send(SessionMessage(...))` 写入 stdio stream |

**MCP Tools**：

| Tool | 说明 |
|------|------|
| `reply(chat_id, text)` | 回复消息。text 会经过 `chunk_message()` 分段，通过 IRC PRIVMSG 发送 |
| `join_channel(channel_name)` | 加入 IRC channel |

### message.py

| 函数/类 | 职责 |
|---------|------|
| `MessageDedup` | 基于 OrderedDict 的 LRU 去重（容量 500） |
| `detect_mention(body, agent_name)` | 检测消息中是否 @mention 了指定 agent |
| `clean_mention(body, agent_name)` | 移除 @mention 文本 |
| `chunk_message(text, max_length)` | 按段落/行/空格边界分段（默认 4000 字符） |

## 关键实现细节

### Notification Injection

Channel MCP 要求 server 能主动向 Claude Code 推送消息。FastMCP 不支持这一点，因此使用 `mcp.server.lowlevel.Server`，直接向 `write_stream` 写入 `SessionMessage(JSONRPCNotification(...))`。

### IRC → Async 桥接

IRC client 回调运行在 IRC reactor 线程中，而 MCP server 运行在 asyncio event loop 中。桥接方式：

1. IRC callback 将消息放入 `asyncio.Queue`（通过 `loop.call_soon_threadsafe(queue.put_nowait, msg)`）
2. async 循环中 `await queue.get()`
3. 两者通过 `anyio.create_task_group()` 并发运行

### 消息过滤

- **Private**：只接收发给自己的消息；过滤自身发出的消息；LRU 去重
- **Channel**：只处理 @mention 自己的消息；清除 mention 文本

## 添加 MCP Tool

1. 在 `server.py` 的 `register_tools()` 中添加 `@server.call_tool()` handler
2. 添加对应的 `@server.list_tools()` entry
3. 在 `tests/unit/test_channel_server_irc.py` 添加测试

## 独立使用

不需要 zchat CLI 即可运行：

```bash
cd weechat-channel-server
claude --dangerously-load-development-channels plugin:weechat-channel
```

此时 agent0 已在 IRC server 上，任何 IRC 客户端都可以与之交互。
