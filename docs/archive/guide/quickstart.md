# 安装与启动

## 安装 zchat

一键安装（推荐）：

```bash
curl -fsSL https://raw.githubusercontent.com/ezagent42/zchat/main/install.sh | bash
```

或通过 Homebrew：

```bash
brew tap ezagent42/zchat
brew install zchat
```

## 安装依赖

zchat 依赖几个外部工具。运行 `zchat doctor` 查看哪些已安装、哪些缺失：

```bash
zchat doctor
```

输出示例：

```
  ✓ tmux              3.6a  (required)
  ✓ claude            2.1.86 (Claude Code)  (required)
  ✓ zchat-channel     (required)
  ✗ ergo              (optional, brew install ezagent42/zchat/ergo)
  ✗ weechat           (optional, brew install weechat)
  ✗ weechat plugin    (optional, run: zchat setup weechat)
```

按提示安装缺失的组件：

```bash
# 必需（brew install zchat 已包含 tmux 和 zchat-channel）
# Claude Code 需要单独安装：https://docs.anthropic.com/en/docs/claude-code

# 可选
brew install ezagent42/zchat/ergo   # 本地 IRC server
brew install weechat                 # IRC 客户端 UI
zchat setup weechat                  # WeeChat zchat 插件（自动下载）
```

## 创建项目

```bash
zchat project create local
```

交互式向导会询问：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| IRC server | `zchat.inside.h2os.cloud` | IRC 服务器（或自定义） |
| Default channels | `#general` | 默认加入的频道 |
| Agent types | `claude` | 多选，支持扩展模板 |
| HTTP proxy | （空） | Claude 专属，留空直连 |

## 启动

```bash
zchat irc daemon start               # 1. 启动 ergo IRC server
zchat irc start                      # 2. 启动 WeeChat（自动检查 IRC 连通性）
zchat agent create agent0            # 3. 创建 AI agent（自动检查 IRC 连通性）
```

> `irc start` 和 `agent create` 会在启动前自动检查 IRC 服务器是否可达。如果连接失败会提示错误，而不是静默启动后才发现连不上。

进入项目的 tmux session 查看所有窗口：

```bash
zchat project use local
```

在 tmux 里用 `Ctrl-b n` / `Ctrl-b p` 切换 window（每个 agent 和 WeeChat 各占一个 window）。

## 第一次对话

在 WeeChat 中，向 agent0 发消息：

```
@agent0 hello，你能帮我做什么？
```

agent0 会通过 IRC 收到你的消息，然后回复到 channel 中。

## 停止

```bash
zchat shutdown                       # 停止所有 agent + WeeChat + ergo + tmux session
```

## 更新

```bash
zchat update                         # 检查是否有新版本
zchat upgrade                        # 下载并安装最新版本
```

默认跟踪 `main` 频道（最新开发版）。可通过 `zchat config set update.channel release` 切换到正式版本频道。

## 下一步

了解更多命令和使用场景 → [使用指南](usage.md)
