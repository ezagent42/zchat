# Agent 管理开发文档

## 定位

Agent 生命周期管理，通过 zchat CLI 和 WeeChat 插件两种方式提供。负责启动/停止 Claude Code 进程、管理 tmux pane。

## 管理方式

### zchat CLI（独立工具）

```bash
zchat agent create agent0          # 创建 agent
zchat agent stop helper            # 停止 agent
zchat agent list                   # 列出所有 agent
zchat agent restart helper         # 重启 agent
zchat agent send agent0 "hello"    # 向 agent 发送文本
```

### WeeChat 插件（zchat.py）

```
/agent create helper
/agent stop helper
/agent list
/agent restart helper
```

## Scoped Agent Naming

Agent 名称带用户前缀，格式 `{username}-agent0`：

- `scoped_name("helper", "alice")` → `"alice-helper"`
- 分隔符使用 `-`（IRC RFC 2812 禁止 `:` 在 nick 中）
- `{username}-agent0` 是 primary agent

## tmux Pane 管理

每个 Agent 在独立的 tmux pane 中运行：

- 创建时使用 `tmux split-window` 创建 pane 并捕获 pane_id
- 停止时使用 `tmux send-keys -t {pane_id} C-c` 定向终止
- tmux session 名为 `zchat-{project}`，避免多项目冲突
