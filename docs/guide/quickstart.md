# 安装与启动

## 前置条件

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | ≥ 2.1.80 | Anthropic 的 CLI AI 助手 |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.4 | Python 包管理器（类似 npm） |
| [WeeChat](https://weechat.org/) | ≥ 4.0 | 终端聊天客户端 |
| [tmux](https://github.com/tmux/tmux) | — | 终端多窗口管理器 |
| Python | ≥ 3.10 | 运行时 |
| [zenohd](https://zenoh.io/) | ≥ 1.0.0 | Zenoh router daemon |

## 一键启动

```bash
git clone https://github.com/ezagent42/weechat-claude.git
cd weechat-claude
./start.sh ~/my-project alice
```

`start.sh` 会自动完成以下步骤：

1. **检查依赖** — 确认 claude、uv、weechat、tmux、zenohd 都已安装
2. **确保 zenohd 运行** — 在 `localhost:7447` 启动 Zenoh router（如果尚未运行）
3. **安装依赖** — `uv sync` 安装 channel-server 依赖，`uv pip install --system eclipse-zenoh` 让 WeeChat 的系统 Python 能 import zenoh
4. **复制插件** — 将 weechat-zenoh.py 和 weechat-agent.py 复制到 WeeChat 插件目录
5. **创建 tmux session** — 分为两个 pane：
   - **Pane 0**：Claude Code (agent0) + channel plugin
   - **Pane 1**：WeeChat + zenoh/agent 插件已加载

## 第一次对话

启动后，你会看到 WeeChat 界面。和 agent0 打个招呼：

```
/zenoh join @agent0
hello agent0，你能帮我做什么？
```

agent0 会通过 Zenoh 收到你的消息，然后通过 MCP channel 回复到你的 WeeChat buffer 中。

## 停止系统

```bash
./stop.sh
```

这会关闭 tmux session。如果要同时停止 zenohd，使用 `./stop.sh --all`。

## 下一步

了解更多命令和使用场景 → [使用指南](usage.md)
