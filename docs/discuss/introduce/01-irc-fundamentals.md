# 第一章：IRC 协议基础——为什么选 IRC

> 预计阅读：20 分钟

## 为什么不用 WebSocket / gRPC / 自定义协议？

zchat 早期曾考虑过 Zenoh（分布式通信框架），最终迁移到 IRC。原因：

1. **成熟稳定**：IRC 协议诞生于 1988 年，RFC 2812 定义了完整的消息路由、频道管理、昵称机制
2. **天然多客户端**：人用 WeeChat/irssi，agent 用 irc 库，无需适配
3. **Presence 内置**：JOIN/PART/QUIT 天然支持在线状态
4. **工具生态**：WeeChat 提供现成的 UI、脚本系统、状态栏
5. **轻量**：纯文本协议，无序列化开销

> 引用：[docs/design-decisions.md](../../design-decisions.md) "IRC migration from Zenoh"

## IRC 核心概念

### 消息类型

zchat 使用的 IRC 消息类型：

```
PRIVMSG #general :hello everyone          ← 频道消息
PRIVMSG alice-agent0 :help me             ← 私聊消息
JOIN #general                              ← 加入频道
PART #general                              ← 离开频道
QUIT :bye                                  ← 断开连接
```

### 频道（Channel）

- 以 `#` 开头：`#general`、`#dev`
- 多人群聊，所有成员都能看到消息
- 在 zchat 中，人和 agent 共存于同一频道

### 昵称（Nick）

- 每个连接有唯一昵称
- IRC RFC 2812 限制：字母、数字、`-_\[]{}^|`
- **禁止 `:`** — 这就是为什么 zchat 用 `-` 做分隔符而非 `:`

> 引用：[CLAUDE.md](../../../CLAUDE.md) "Agent 命名"

### PRIVMSG

IRC 的核心消息命令。无论是频道消息还是私聊，底层都是 PRIVMSG：

```
:alice!~u@host PRIVMSG #general :hello        ← 频道消息
:alice!~u@host PRIVMSG bob :secret             ← 私聊
```

区别仅在于目标：`#channel` 是频道，`nick` 是私聊。

## zchat 如何使用 IRC

### 三类消息

zchat 在标准 IRC PRIVMSG 上构建了三类消息：

| 类型 | 格式 | 用途 |
|------|------|------|
| 用户聊天 | 标准 PRIVMSG | 人与人、人与 agent 对话 |
| @mention | `@alice-agent0 question` | 在频道中指定 agent 处理 |
| 系统消息 | `__zchat_sys:` + JSON | 机器间控制（stop/join/status） |

> 引用：[CLAUDE.md](../../../CLAUDE.md) "消息协议"

### @mention 检测

channel-server 不处理频道中的所有消息，**只处理 @mention 自己的消息**：

```python
# zchat-channel-server/message.py:10-12
def detect_mention(body: str, agent_name: str) -> bool:
    return f"@{agent_name}" in body
```

这是一个关键设计：减少噪音，agent 只在被明确提及时才响应。

### 系统消息

人类看不到的机器间通信，用 `__zchat_sys:` 前缀标识：

```
PRIVMSG alice :__zchat_sys:{"type":"sys.stop_request","body":{},...}
```

WeeChat 插件会把这些消息转换成人类可读的格式显示。

> 详见 [第二章](./02-protocol.md)

## ergo IRC 服务器

zchat 使用 [ergo](https://ergo.chat) 作为本地 IRC 服务器：

- Go 语言编写，单二进制部署
- 支持 SASL 认证（zchat 用它做 OIDC token 验证）
- 每个 zchat 项目有独立的 ergo 实例和配置

> 引用：`ergo-inside/ergo.yaml` — 生产环境的 ergo 配置

本地开发时，ergo 运行在 `127.0.0.1:6667`，无 TLS。
生产环境可配合 Caddy L4 代理提供 TLS（`:6697`）。

## 关键约束

1. **IRC 消息长度**：单条消息有长度限制，zchat 在 4000 字符处分片
   ```python
   # zchat-channel-server/message.py:7
   MAX_MESSAGE_LENGTH = 4000
   ```

2. **昵称限制**：RFC 2812 禁止特殊字符，所以 agent 名用 `-` 分隔而非 `:`

3. **无历史记录**：IRC 本身不存消息历史，断线重连后看不到之前的消息

## 下一步

理解了 IRC 基础后，进入 [第二章：zchat-protocol 命名与系统消息](./02-protocol.md)。
