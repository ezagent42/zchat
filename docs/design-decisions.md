# 设计决策记录

本文档记录 WeeChat-Claude 的设计原则、tradeoff 和关键决策。具体的实现细节、命令参考和协议规范分别在 [用户文档](guide/) 和 [开发文档](dev/) 中。

-----

## 产品概述

### 一句话描述

一个由三个独立组件构成的本地/局域网多 Agent 协作系统：WeeChat 用户通过 Zenoh P2P 消息总线，与一个或多个 Claude Code 实例进行实时对话、任务分配和协作编程。

### 问题陈述

Claude Code Channels（research preview, 2026-03-20）支持 Telegram/Discord 作为消息桥接，但对以下场景不够理想：

- **本地路由** — zenohd 作为轻量本地路由，数据不出本机/内网
- **多 Agent 管理** — 同时运行和管理多个 Claude Code 实例
- **终端原生** — 在 tmux/terminal 中完成一切
- **可组合** — 各组件独立使用，不强制绑定

### 设计原则

**关注点分离**：三个组件通过 Zenoh topic 约定通信，互不知道对方的实现细节。

-----

## 组件总览

| 组件 | 类型 | 语言 | 运行方式 | 依赖 |
|------|------|------|----------|------|
| **weechat-zenoh** | WeeChat Python 脚本 | Python | `/python load` | eclipse-zenoh |
| **weechat-agent** | WeeChat Python 脚本 | Python | `/python load` | weechat-zenoh（通过 WeeChat 命令交互） |
| **weechat-channel-server** | Python MCP server (Claude Code plugin) | Python | Claude Code plugin | mcp, eclipse-zenoh |
| **zenohd** | Zenoh 路由 | Rust | start.sh 自动启动 | — |

-----

## 关键设计决策

### zenohd Client Mode（v3.1.0）

**决策**：从 Zenoh peer mode（multicast scouting）迁移到 client mode，连接本地 zenohd 路由。

**原因**：macOS 上 multicast scouting 不可靠。client mode 通过 `tcp/127.0.0.1:7447` 直连 zenohd，行为确定性高。zenohd 跨 session 持续运行，为未来 storage backend 打下基础。

### WeeChat 术语对齐（v3.1.0）

**决策**：所有代码和文档使用 WeeChat 原生术语 channel/private，而非 room/dm。

**原因**：WeeChat 的 `localvar_type` 只有 `"channel"` 和 `"private"` 两种。对齐术语减少概念映射负担。

### Scoped Agent Naming（v3.1.0）

**决策**：Agent 名称带用户前缀，格式 `{username}:agent0`。

**原因**：同一台机器多用户场景下防止 agent 名冲突。`scoped_name(name)` 自动添加前缀，`PRIMARY_AGENT` 变量存储主 agent 全名。

### write_stream Notification Injection（v3.1.0）

**决策**：使用 `mcp.server.lowlevel.Server` 替代 FastMCP，直接向 `write_stream` 写入 MCP notification。

**原因**：Python MCP SDK 不暴露 session 对象，无法通过高层 API 主动推送 notification。低层 Server 配合 `SessionMessage(JSONRPCNotification(...))` 可以直接写入 stdio stream。

-----

## 约束与 Tradeoff

| 约束 | 影响 | 决策 |
|------|------|------|
| Channel MCP 是 research preview | 必须用 `--dangerously-load-development-channels` | 接受，等正式发布后移除 |
| Claude Code 需要 claude.ai 登录 | 不支持 API key | 接受现状 |
| `--dangerously-skip-permissions` | Claude 无确认执行文件操作 | 仅限信任环境 |
| zenohd 必须运行 | 所有 Zenoh 通信经由本地 zenohd | start.sh 自动启动 |
| 无跨 session 历史 | 重启后消息丢失 | WeeChat logger 本地保存 + 未来接入 zenohd storage |

-----

## 未来演进

| 方向 | 描述 |
|------|------|
| **Agent 间通信** | Agent A 通过 private topic 与 Agent B 直接协作 |
| **zenohd + storage** | zenohd 已就绪，接入 storage backend 即可提供跨 session 消息历史 |
| **飞书桥接** | 复用 Zenoh 总线，飞书作为另一个 Zenoh 节点 |
| **Ed25519 身份** | 消息签名验证，防冒充 |
| **Socialware** | Channel → Slot, Agent role → Kit, Capability 权限 |
| **Web UI** | WeeChat relay API 暴露 Web 前端 |
