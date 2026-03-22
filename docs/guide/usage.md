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
