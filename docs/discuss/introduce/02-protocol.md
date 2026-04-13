# 第二章：zchat-protocol——命名规范与系统消息

> 预计阅读：20 分钟

## 概述

`zchat-protocol` 是最底层的共享库，定义了两件事：

1. **Agent 命名规范**（naming.py）
2. **系统消息协议**（sys_messages.py）

所有其他组件（CLI、channel-server、WeeChat 插件）都依赖它。

> 代码位置：`zchat-protocol/zchat_protocol/`

## Agent 命名

### 为什么需要 scoped name？

多用户环境中，`agent0` 这个名字会冲突。解决方案：在 agent 名前加用户名前缀。

```python
# zchat-protocol/zchat_protocol/naming.py:3
AGENT_SEPARATOR = "-"
```

分隔符选 `-` 而非 `:` 或 `.`，因为 IRC RFC 2812 只允许 `-` 这类字符在昵称中。

### scoped_name() 函数

```python
# zchat-protocol/zchat_protocol/naming.py:6-13
def scoped_name(name: str, username: str) -> str:
    if AGENT_SEPARATOR in name:
        return name          # 已经有前缀，原样返回
    return f"{username}{AGENT_SEPARATOR}{name}"
```

行为示例：

| 输入 | 输出 | 说明 |
|------|------|------|
| `scoped_name("agent0", "alice")` | `"alice-agent0"` | 添加前缀 |
| `scoped_name("alice-agent0", "alice")` | `"alice-agent0"` | 已有前缀，不重复 |
| `scoped_name("bob-helper", "alice")` | `"bob-helper"` | 其他用户的 agent，保留 |

> 引用：`zchat-protocol/zchat_protocol/naming.py:6-13`

### 命名约定

- 格式：`{username}-{agent_name}`
- 示例：`alice-agent0`、`alice-helper`、`bob-reviewer`
- `agent0` 是主 agent（每个用户的第一个 agent）
- 可以创建多个 agent：`helper`、`tester`、`reviewer` 等

> 引用：[CLAUDE.md](../../../CLAUDE.md) "Agent 命名"

## 系统消息协议

### 设计思路

agent 之间需要进行控制通信（停止、加入频道、查询状态），但 IRC 只有 PRIVMSG。

解决方案：在 PRIVMSG 中嵌入结构化 JSON，用 `__zchat_sys:` 前缀区分。

### 消息格式

```python
# zchat-protocol/zchat_protocol/sys_messages.py:8-9
SYS_PREFIX = "sys."
IRC_SYS_PREFIX = "__zchat_sys:"
```

系统消息的完整结构：

```python
# zchat-protocol/zchat_protocol/sys_messages.py:21-30
{
    "id": "a1b2c3d4",        # 8 位随机 hex
    "nick": "alice-agent0",   # 发送者
    "type": "sys.stop_request",  # 消息类型
    "body": {},               # 类型相关的数据
    "ref_id": None,           # 引用另一条消息的 id（用于请求-响应匹配）
    "ts": 1712000000          # Unix 时间戳
}
```

### 编码与解码

```python
# zchat-protocol/zchat_protocol/sys_messages.py:33-35
def encode_sys_for_irc(msg: dict) -> str:
    return f"{IRC_SYS_PREFIX}{json.dumps(msg)}"
```

IRC 传输形式：

```
PRIVMSG alice :__zchat_sys:{"id":"a1b2c3d4","type":"sys.stop_request","body":{},...}
```

解码是反向操作：

```python
# zchat-protocol/zchat_protocol/sys_messages.py:38-45
def decode_sys_from_irc(text: str) -> dict | None:
    if not text.startswith(IRC_SYS_PREFIX):
        return None
    return json.loads(text[len(IRC_SYS_PREFIX):])
```

> 引用：`zchat-protocol/zchat_protocol/sys_messages.py:33-45`

### 系统消息类型

当前定义了三对请求-响应：

| 请求 | 响应 | 用途 |
|------|------|------|
| `sys.stop_request` | `sys.stop_confirmed` | 通知 agent 停止 |
| `sys.join_request` | `sys.join_confirmed` | 请求 agent 加入频道 |
| `sys.status_request` | `sys.status_response` | 查询 agent 状态 |

#### stop_request

```python
# 发送方
make_sys_message("zchat-cli", "sys.stop_request", {})

# 接收方处理（zchat-channel-server/server.py:189-190）
if msg["type"] == "sys.stop_request":
    reply = make_sys_message(AGENT_NAME, "sys.stop_confirmed", {}, ref_id=msg["id"])
```

#### join_request

```python
# body 携带频道名
make_sys_message("zchat-cli", "sys.join_request", {"channel": "#dev"})

# 接收方（server.py:192-199）
channel = msg["body"].get("channel", "")
connection.join(channel)
reply = make_sys_message(AGENT_NAME, "sys.join_confirmed", {"channel": channel}, ref_id=msg["id"])
```

#### status_request

```python
# 响应包含运行状态
reply = make_sys_message(AGENT_NAME, "sys.status_response", {
    "channels": list(joined_channels),
    "messages_sent": _msg_counter["sent"],
    "messages_received": _msg_counter["received"],
}, ref_id=msg["id"])
```

> 引用：`zchat-channel-server/server.py:186-206`

### is_sys_message() 辅助函数

```python
# zchat-protocol/zchat_protocol/sys_messages.py:16-18
def is_sys_message(msg: dict) -> bool:
    return msg.get("type", "").startswith(SYS_PREFIX)
```

用于区分系统消息和普通聊天消息。

## 协议版本

```python
# zchat-protocol/zchat_protocol/__init__.py:1
PROTOCOL_VERSION = "0.1"
```

当前为 0.1 版本，协议还在演进中。

## 测试覆盖

协议的所有功能都有单元测试：

- `zchat-protocol/tests/test_naming.py` — 命名逻辑测试
- `zchat-protocol/tests/test_sys_messages.py` — 系统消息编解码测试

运行：
```bash
cd zchat-protocol && uv run pytest tests/ -v
```

> 引用：[CLAUDE.md](../../../CLAUDE.md) "测试体系"

## 关键设计决策

1. **前缀检测而非类型枚举**：`is_sys_message()` 用 `startswith("sys.")` 而非硬编码类型列表，方便扩展
2. **ref_id 匹配**：响应消息通过 `ref_id` 引用请求消息的 `id`，实现请求-响应关联
3. **IRC 传输透明**：系统消息走普通 PRIVMSG，不需要 IRC 服务器支持任何扩展
4. **独立包**：protocol 是独立的 Python 包，CLI 和 channel-server 都依赖它

## 下一步

理解了底层协议后，进入 [第三章：channel-server MCP ↔ IRC 桥接](./03-channel-server.md)。
