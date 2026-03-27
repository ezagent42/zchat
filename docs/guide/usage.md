# 使用指南

## 命令速查

### 聊天命令（IRC 原生）

WeeChat 原生支持 IRC，无需额外插件：

| 命令 | 说明 |
|------|------|
| `/join #channel` | 加入一个 channel（群聊） |
| `/msg nick message` | 发送 private message（私聊） |
| `/part [#channel]` | 离开当前或指定的 channel |
| `/nick <name>` | 修改昵称 |
| `/names` | 列出当前 channel 的成员 |

### Agent 管理命令（zchat CLI）

| 命令 | 说明 |
|------|------|
| `zchat agent create <name>` | 启动新的 Claude Code 实例（名称自动加 `{username}-` 前缀） |
| `zchat agent stop <name>` | 停止一个 Agent |
| `zchat agent restart <name>` | 重启一个 Agent |
| `zchat agent list` | 列出所有 Agent 及状态 |
| `zchat agent send <name> <msg>` | 向 Agent 发送文本 |

### WeeChat 插件命令（zchat.py）

| 命令 | 说明 |
|------|------|
| `/agent create <name>` | 在 WeeChat 内创建 Agent |
| `/agent stop <name>` | 停止 Agent |
| `/agent list` | 列出 Agent 状态 |
| `/agent restart <name>` | 重启 Agent |

## 使用场景

### 场景 1：人 ↔ 人聊天

使用标准 IRC，不需要 Claude Code。适合局域网内的终端用户聊天。

```
┌─────────┐  IRC   ┌─────────┐
│ WeeChat │ ◄─────► │ WeeChat │
│ (Alice) │         │ (Bob)   │
└─────────┘         └─────────┘
      ▲                  ▲
      └───────┬──────────┘
         ┌────▼────┐
         │  ergo   │
         │ (IRC)   │
         └─────────┘
```

```bash
# 终端 A
weechat
/connect localhost
/join #team

# 终端 B（同一局域网）
weechat
/connect localhost
/join #team
```

### 场景 2：人 ↔ Agent 对话

使用 WeeChat + channel-server，通过 IRC 通信。

```
┌─────────┐  IRC   ┌───────────────────┐
│ WeeChat │ ◄─────► │ weechat-channel   │
│ (Alice) │         │ (MCP server)      │
└─────────┘         │    ↕ stdio        │
                    │ Claude Code       │
                    └───────────────────┘
```

### 场景 3：完整部署

通过 `./start.sh` 一键启动，tmux 管理所有组件。

```bash
./start.sh ~/my-project
```

在 WeeChat 中你可以动态创建更多 Agent：

```
/agent create helper
@helper 帮我看看这个 bug
```
