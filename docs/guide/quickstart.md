# 安装与启动

## 前置条件

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | ≥ 2.1.80 | Anthropic 的 CLI AI 助手 |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.4 | Python 包管理器（类似 npm） |
| [WeeChat](https://weechat.org/) | ≥ 4.0 | 终端聊天客户端 |
| [tmux](https://github.com/tmux/tmux) | — | 终端多窗口管理器 |
| Python | ≥ 3.10 | 运行时 |
| [ergo](https://ergo.chat/) | ≥ 2.0 | 本地 IRC server |

## 一键启动

```bash
git clone https://github.com/ezagent42/zchat.git
cd zchat
./start.sh ~/my-project
```

`start.sh` 会自动完成以下步骤：

1. **检查依赖** — 确认 claude、uv、weechat、tmux、ergo 都已安装
2. **确保 ergo 运行** — 启动本地 IRC server（如果尚未运行）
3. **安装依赖** — `uv sync` 安装 channel-server 依赖
4. **创建 tmux session** — 分为多个 pane：
   - Claude Code (`agent0`) + channel plugin
   - WeeChat 连接到本地 IRC server

## 第一次对话

启动后，你会看到 WeeChat 界面。和 agent0 打个招呼：

```
/msg agent0 hello，你能帮我做什么？
```

agent0 会通过 IRC 收到你的消息，然后通过 MCP channel 回复到你的 WeeChat buffer 中。

## 停止系统

```bash
./stop.sh
```

## 下一步

了解更多命令和使用场景 → [使用指南](usage.md)
