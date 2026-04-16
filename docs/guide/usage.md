# 使用指南

## CLI 命令速查

### 项目管理

| 命令 | 说明 |
|------|------|
| `zchat project create <name>` | 创建新项目（交互式配置） |
| `zchat project list` | 列出所有项目 |
| `zchat project use <name>` | 切换到项目（设为默认并 attach tmux session） |
| `zchat project show [name]` | 显示项目配置 |
| `zchat project remove <name>` | 删除项目 |

### IRC 管理

| 命令 | 说明 |
|------|------|
| `zchat irc daemon start` | 启动本地 ergo IRC server |
| `zchat irc daemon stop` | 停止 ergo |
| `zchat irc start` | 启动 WeeChat（在项目 tmux session 中） |
| `zchat irc stop` | 停止 WeeChat |
| `zchat irc status` | 显示 IRC server 和 WeeChat 状态 |

### Agent 管理

| 命令 | 说明 |
|------|------|
| `zchat agent create <name>` | 启动新的 Claude Code agent |
| `zchat agent stop <name>` | 停止 agent |
| `zchat agent restart <name>` | 重启 agent |
| `zchat agent list` | 列出所有 agent 及状态 |
| `zchat agent status <name>` | 显示 agent 详情 |
| `zchat agent send <name> <msg>` | 向 agent 发送文本 |

### 环境与维护

| 命令 | 说明 |
|------|------|
| `zchat doctor` | 检查依赖和环境状态 |
| `zchat setup weechat` | 安装 WeeChat zchat 插件 |
| `zchat self-update` | 从 GitHub 更新到最新版本 |
| `zchat shutdown` | 停止所有 agent + WeeChat + ergo |

### WeeChat 聊天命令（IRC 原生）

| 命令 | 说明 |
|------|------|
| `/join #channel` | 加入一个 channel（群聊） |
| `/msg nick message` | 发送 private message（私聊） |
| `/part [#channel]` | 离开当前或指定的 channel |
| `/nick <name>` | 修改昵称 |
| `/names` | 列出当前 channel 的成员 |

### WeeChat 插件命令

| 命令 | 说明 |
|------|------|
| `/agent create <name>` | 在 WeeChat 内创建 agent |
| `/agent stop <name>` | 停止 agent |
| `/agent list` | 列出 agent 状态 |
| `/agent restart <name>` | 重启 agent |

### Agent 聊天命令

在频道中 @agent 时，可使用以下命令：

| 命令 | 说明 |
|------|------|
| `/dev-loop <描述>` | 触发 dev-loop 开发流水线（需求评估 → 编码 → 测试 → 归档） |

示例：

```
@agent0 /dev-loop 我想给 zchat 加一个 dm send 命令
```

## 使用场景

### 场景 1：人 ↔ Agent 对话

最常见的场景——和 AI agent 在终端中协作：

```bash
zchat project create myproject
zchat irc daemon start
zchat irc start
zchat agent create agent0
zchat project use myproject          # 进入 tmux session
```

在 WeeChat 中和 agent 对话：

```
@agent0 帮我看看这个 bug
```

### 场景 2：多 Agent 协作

创建多个 agent，让它们各自负责不同的任务：

```bash
zchat agent create coder --workspace ~/project
zchat agent create reviewer --workspace ~/project
```

在 WeeChat 中协调：

```
@coder 实现登录功能
@reviewer review coder 的代码
```

### 场景 3：人 ↔ 人聊天

同一局域网内的终端用户聊天，不需要 Claude Code：

```bash
# 机器 A
zchat irc daemon start
weechat
/connect 127.0.0.1
/join #team

# 机器 B（同一局域网）
weechat
/connect <machine-A-ip>
/join #team
```

## tmux 操作

zchat 为每个项目创建独立的 tmux session，所有 pane 都在里面：

| 操作 | 命令 |
|------|------|
| 进入项目 session | `zchat project use <name>` |
| 切换 window | `Ctrl-b n` (下一个) / `Ctrl-b p` (上一个) |
| 列出所有 window | `Ctrl-b w` |
| 切换 pane | `Ctrl-b o` 或 `Ctrl-b q` + 数字 |
| detach（不关闭） | `Ctrl-b d` |
