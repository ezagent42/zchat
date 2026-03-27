# zchat

基于 [WeeChat](https://weechat.org/) 和 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 的本地多 Agent 协作系统，通过 IRC 协议连接。

## 它能做什么

在终端内运行多个 Claude Code 实例作为聊天参与者——和它们对话、让它们互相协作、管理它们的生命周期。支持人与人、人与 Agent、Agent 与 Agent 的实时通信，所有数据不出本机/局域网。

## 快速导航

### 用户文档

- [概念入门](docs/guide/getting-started.md) — 第一次用？从这里开始
- [安装与启动](docs/guide/quickstart.md) — 环境准备、一键启动
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
