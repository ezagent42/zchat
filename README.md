# zchat

基于 [WeeChat](https://weechat.org/) 和 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 的本地多 Agent 协作系统，通过 IRC 协议连接。

## 它能做什么

在终端内运行多个 Claude Code 实例作为聊天参与者——和它们对话、让它们互相协作、管理它们的生命周期。支持人与人、人与 Agent、Agent 与 Agent 的实时通信，所有数据不出本机/局域网。

## 安装

```bash
brew tap ezagent42/zchat
brew install zchat
```

安装后运行 `zchat doctor` 检查环境：

```bash
zchat doctor
```

安装可选组件：

```bash
brew install ezagent42/zchat/ergo   # 本地 IRC server
brew install weechat                 # IRC 客户端
zchat setup weechat                  # WeeChat zchat 插件
```

## 快速开始

```bash
# 初始化
zchat project create local           # 创建项目（交互式配置）
zchat irc daemon start               # 启动 IRC server
zchat irc start                      # 启动 WeeChat

# 创建 agent
zchat agent create agent0            # 创建 AI agent（自动安装 /zchat 插件）
zchat agent create helper            # 可创建多个 agent

# 窗口导航
zchat agent focus agent0             # 切换到 agent0 的工作窗口
zchat agent hide agent0              # 切回 WeeChat 聊天界面
zchat agent hide all                 # 同上（隐藏所有 agent 视图）
zchat project use local              # 进入项目 tmux session

# 管理
zchat agent list                     # 查看所有 agent 状态
zchat agent send agent0 "hello"      # 向 agent 发送消息
zchat agent stop agent0              # 停止 agent
zchat agent restart agent0           # 重启 agent
zchat shutdown                       # 停止所有 agent + 退出 session
```

## 更新

```bash
zchat self-update                    # 更新到 GitHub 最新版本
```

## 文档

### 用户文档

- [概念入门](docs/guide/getting-started.md) — 第一次用？从这里开始
- [安装与启动](docs/guide/quickstart.md) — 环境准备、安装、首次运行
- [使用指南](docs/guide/usage.md) — 命令参考、使用场景
- [限制与路线图](docs/guide/constraints.md) — 已知限制、未来方向

### 开发文档

- [架构与协议](docs/dev/architecture.md) — 系统架构、消息协议、IRC channel
- [channel-server](docs/dev/channel-server.md) — MCP server 桥接
- [agent](docs/dev/agent.md) — Agent 生命周期管理
- [测试](docs/dev/testing.md) — 测试策略与手动测试

### 设计文档

- [设计决策记录](docs/design-decisions.md) — 设计原则与 tradeoff

## License

MIT
