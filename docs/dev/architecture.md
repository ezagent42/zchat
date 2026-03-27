# 架构与协议

## 设计原则

**关注点分离**：组件通过 IRC 协议通信，互不知道对方的实现细节。WeeChat 使用原生 IRC 功能；channel-server 作为 IRC client 桥接到 MCP。IRC 协议是唯一的耦合点。

## 系统架构

四个独立可组合的组件：

| 组件 | 类型 | 职责 |
|------|------|------|
| **ergo** | 本地 IRC server | 消息中转。`zchat irc daemon start` 启动 |
| **weechat-zchat-plugin** | WeeChat Python 插件 | `/agent` 命令、系统消息渲染、Agent 状态显示 |
| **weechat-channel-server** | Claude Code plugin (MCP server) | 桥接 Claude Code ↔ IRC。作为 IRC client 连接 server |
| **zchat CLI** | 独立 CLI 工具 | Agent 生命周期管理、项目配置、IRC server 管理 |

所有组件通过标准 IRC 协议（RFC 2812）通信，连接本地 ergo server。

## 消息协议

### 用户消息

标准 IRC PRIVMSG，无特殊格式：

```
PRIVMSG #general :hello everyone
PRIVMSG alice-agent0 :help me with this bug
```

### @mention Agent

在 channel 中 `@alice-agent0 question`，channel-server 检测 @mention 并转发给 Claude。

### 系统消息

IRC PRIVMSG + `__zchat_sys:` 前缀 + JSON payload：

```
PRIVMSG #general :__zchat_sys:{"type":"agent_join","agent":"alice-agent0"}
```

### Presence

IRC 原生 JOIN/PART/QUIT 事件。

## Agent 命名

- 分隔符：`-`（IRC RFC 2812 禁止 `:` 在 nick 中）
- 格式：`{username}-{agent_name}`，如 `alice-agent0`、`alice-helper`
- `scoped_name("helper", "alice")` → `"alice-helper"`

## 组件间通信流

一条消息从用户输入到 Agent 回复的完整路径：

```
1. 用户在 WeeChat buffer 输入消息
2. WeeChat 通过 IRC PRIVMSG 发送到 ergo server

3. channel-server 的 IRC client 收到消息
4. → 过滤自身消息、检查 @mention
5. → 入队到 asyncio.Queue
6. → inject_message() 构造 MCP notification，写入 write_stream

7. Claude Code 收到 notification，处理后调用 reply() tool
8. → reply() 通过 IRC PRIVMSG 发布回复

9. WeeChat 通过 IRC 收到回复，渲染到 buffer
```
