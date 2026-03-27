# 设计决策记录

本文档记录 zchat 的设计原则、tradeoff 和关键决策。具体的实现细节、命令参考和协议规范分别在 [用户文档](guide/) 和 [开发文档](dev/) 中。

-----

## 产品概述

### 一句话描述

一个由多个独立组件构成的本地/局域网多 Agent 协作系统：用户通过 IRC 协议，与一个或多个 Claude Code 实例进行实时对话、任务分配和协作编程。

### 问题陈述

Claude Code Channels（research preview, 2026-03-20）支持 Telegram/Discord 作为消息桥接，但对以下场景不够理想：

- **本地路由** — ergo 作为轻量本地 IRC server，数据不出本机/内网
- **多 Agent 管理** — 同时运行和管理多个 Claude Code 实例
- **终端原生** — 在 tmux/terminal 中完成一切
- **可组合** — 各组件独立使用，不强制绑定

### 设计原则

**关注点分离**：组件通过 IRC 协议通信，互不知道对方的实现细节。

-----

## 组件总览

| 组件 | 类型 | 语言 | 运行方式 | 依赖 |
|------|------|------|----------|------|
| **weechat-zchat-plugin** | WeeChat Python 脚本 | Python | `/python load` | — |
| **zchat CLI** | 独立 CLI 工具 | Python | 命令行 | — |
| **weechat-channel-server** | Python MCP server (Claude Code plugin) | Python | Claude Code plugin | mcp, irc |
| **ergo** | IRC server | Go | zchat irc daemon start | — |

-----

## 关键设计决策

### IRC 协议迁移（从 Zenoh）

**决策**：从 Zenoh P2P 消息总线迁移到标准 IRC 协议。

**原因**：IRC 是成熟的、标准化的聊天协议，WeeChat 原生支持 IRC，无需自定义插件处理消息传输。ergo 作为本地 IRC server 轻量可靠。迁移后减少了 eclipse-zenoh 依赖和 PyO3 兼容性问题。

### WeeChat 术语对齐

**决策**：所有代码和文档使用 IRC/WeeChat 原生术语 channel/private，而非 room/dm。

**原因**：WeeChat 的 `localvar_type` 只有 `"channel"` 和 `"private"` 两种。对齐术语减少概念映射负担。

### Scoped Agent Naming

**决策**：Agent 名称带用户前缀，格式 `{username}-agent0`（使用 `-` 分隔符）。

**原因**：IRC RFC 2812 禁止 `:` 在 nick 中，改用 `-` 作为分隔符。同一台机器多用户场景下防止 agent 名冲突。

### write_stream Notification Injection

**决策**：使用 `mcp.server.lowlevel.Server` 替代 FastMCP，直接向 `write_stream` 写入 MCP notification。

**原因**：Python MCP SDK 不暴露 session 对象，无法通过高层 API 主动推送 notification。低层 Server 配合 `SessionMessage(JSONRPCNotification(...))` 可以直接写入 stdio stream。

-----

## 约束与 Tradeoff

| 约束 | 影响 | 决策 |
|------|------|------|
| Channel MCP 是 research preview | 必须用 `--dangerously-load-development-channels` | 接受，等正式发布后移除 |
| Claude Code 需要 claude.ai 登录 | 不支持 API key | 接受现状 |
| `--dangerously-skip-permissions` | Claude 无确认执行文件操作 | 仅限信任环境 |
| IRC server 必须运行 | 所有通信经由 IRC server | zchat irc daemon start 自动启动 |
| 无跨 session 历史 | 重启后消息丢失 | WeeChat logger 本地保存 |

-----

## 未来演进

| 方向 | 描述 |
|------|------|
| **Agent 间通信** | Agent A 通过 IRC private message 与 Agent B 直接协作 |
| **飞书桥接** | 飞书作为另一个 IRC 桥接节点 |
| **Ed25519 身份** | 消息签名验证，防冒充 |
| **Web UI** | WeeChat relay API 暴露 Web 前端 |
