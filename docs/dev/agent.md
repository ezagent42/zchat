# weechat-agent 开发文档

## 定位

Claude Code Agent 生命周期管理插件。它是 weechat-zenoh 的上层消费者，通过 WeeChat 命令和 signal 与 weechat-zenoh 交互。负责启动/停止 Claude Code 进程、管理 tmux pane。

**不直接调用 Zenoh API** — 所有通信都通过 weechat-zenoh 的命令和 signal 完成。

## 文件结构

```
weechat-agent/
└── weechat-agent.py    # 主插件
```

## 核心模块

| 函数 | 职责 |
|------|------|
| `agent_init()` | 注册 agent0（start.sh 预创建）、hook signal |
| `create_agent(name, workspace)` | 在 tmux 中创建新 pane，启动 Claude Code + channel plugin，记录 pane_id |
| `stop_agent(name)` | 向指定 pane_id 发送 `C-c` 终止进程（agent0 不可停止） |
| `on_message_signal_cb()` | 监听 `zenoh_message_received`，解析 Agent 的结构化命令输出 |
| `on_presence_signal_cb()` | 监听 `zenoh_presence_changed`，追踪 Agent 在线状态 |
| `agent_cmd_cb()` | `/agent` 命令分发器 |

## 与 weechat-zenoh 的交互

```python
# 创建 private buffer → 执行 weechat-zenoh 命令
weechat.command("", "/zenoh join @agent0")

# 监听消息
weechat.hook_signal("zenoh_message_received", "on_msg_signal_cb", "")

# 发送消息给 agent
weechat.command("", "/zenoh send @agent0 hello")
```

## tmux Pane 管理

每个 Agent 在独立的 tmux pane 中运行：

- `create_agent()` 使用 `tmux split-window -P -F '#{pane_id}'` 创建 pane 并捕获 pane_id
- Agent 信息存储在 `agents[name] = {"workspace": ..., "status": ..., "pane_id": ...}`
- `stop_agent()` 使用 `tmux send-keys -t {pane_id} C-c` 定向终止，不会影响其他 pane

## agent0 特殊性

- 由 `start.sh` 创建，不通过 `create_agent()` 流程
- `/agent stop agent0` 会被拒绝
- 重启系统时通过 `./start.sh` 重新创建
