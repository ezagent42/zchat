# 架构与协议

## 设计原则

**关注点分离**：三个组件通过 Zenoh topic 约定通信，互不知道对方的实现细节。weechat-zenoh 不知道 Claude Code 的存在；channel-server 不知道 WeeChat 的存在。Zenoh topic 约定是唯一的耦合点。

## 系统架构

四个独立可组合的组件：

| 组件 | 类型 | 职责 |
|------|------|------|
| **zenohd** | 本地 Zenoh 路由 | 消息中转。start.sh 自动启动在 `tcp/127.0.0.1:7447`，跨 session 持续运行 |
| **weechat-zenoh** | WeeChat Python 插件 | P2P channel/private 通信，在线状态追踪。对所有参与者一视同仁 |
| **weechat-channel-server** | Claude Code plugin (MCP server) | 桥接 Claude Code ↔ Zenoh。只知道 Zenoh topic 和 MCP 协议 |
| **weechat-agent** | WeeChat Python 插件 | Agent 生命周期管理。通过 WeeChat 命令和 signal 与 weechat-zenoh 交互 |

所有 Zenoh session 使用 client mode（`mode: "client"`, `connect: ["tcp/127.0.0.1:7447"]`），通过本地 zenohd 路由通信。

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
