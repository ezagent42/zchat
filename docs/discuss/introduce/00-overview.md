# 第零章：全局概览与学习路线

> 预计阅读：15 分钟

## zchat 是什么

zchat 是一个**多 Agent 协作系统**，让多个 Claude Code 实例（agent）和人类通过 IRC 协议实时聊天、协作完成软件工程任务。

**一句话总结**：把 IRC 聊天室变成 AI agent 的工作空间——人在 WeeChat 里打字，agent 在 Claude Code 里干活，所有对话走 IRC 协议。

## 为什么需要它

Claude Code 本身是单人单 agent 的交互模式。但实际开发中常见需求：

1. **多 agent 并行**：一个 agent 写代码，另一个跑测试，第三个审查
2. **人机混合**：开发者和多个 agent 在同一个频道讨论
3. **持久化运行**：agent 在 tmux 里长期运行，SSH 断了也不影响
4. **数据本地化**：所有通信走本地 IRC，不经过云端

zchat 解决的就是这些问题。

## 架构总览

```
┌──────────────┐  ┌──────────────┐
│ alice        │  │ bob          │   ← 人类（任意 IRC 客户端）
│ (WeeChat     │  │ (irssi)      │
│  +zchat.py)  │  │              │
└──────┬───────┘  └──────┬───────┘
       │ IRC             │ IRC
       ▼                 ▼
┌─────────────────────────────┐
│ IRC Server (ergo)           │   ← 消息路由中枢
└──┬─────────────┬────────────┘
   │ IRC         │ IRC
   ▼             ▼
┌────────┐    ┌────────┐
│agent0  │    │helper  │         ← AI agent（Claude Code 实例）
│(channel│    │(channel│
│-server)│    │-server)│
└──┬─────┘    └──┬─────┘
   │MCP          │MCP
   ▼             ▼
 Claude        Claude               ← Claude Code CLI
```

> 引用：[CLAUDE.md](../../../CLAUDE.md) 架构图

五个组件：

| 组件 | 职责 | 代码位置 |
|------|------|----------|
| **zchat CLI** | 项目/agent/IRC 生命周期管理 | `zchat/cli/` |
| **zchat-channel-server** | MCP server，桥接 IRC ↔ Claude Code | `zchat-channel-server/` |
| **zchat-protocol** | 命名规范 + 系统消息协议 | `zchat-protocol/` |
| **weechat-zchat-plugin** | WeeChat 插件，提供 `/agent` 命令和状态栏 | `weechat-zchat-plugin/` |
| **ergo** | 本地 IRC 服务器 | 第三方，通过 brew 安装 |

## 学习路线

本系列共 8 章，按**从底层到上层**的顺序组织：

| 章 | 主题 | 时间 | 你将掌握 |
|----|------|------|----------|
| 1 | IRC 协议基础 | 20 min | 为什么选 IRC，核心概念 |
| 2 | zchat-protocol：命名与系统消息 | 20 min | agent 命名规则，机器间通信协议 |
| 3 | zchat-channel-server：MCP ↔ IRC 桥接 | 30 min | 消息如何在 Claude Code 和 IRC 之间流动 |
| 4 | zchat CLI：项目与配置管理 | 25 min | 项目创建、配置体系、状态持久化 |
| 5 | zchat CLI：Agent 生命周期 | 25 min | agent 创建/停止/重启的完整流程 |
| 6 | zchat CLI：IRC 与认证管理 | 20 min | ergo 启动、WeeChat 集成、OIDC 认证 |
| 7 | weechat-zchat-plugin：用户界面 | 15 min | WeeChat 插件如何提供 agent 管理 UI |
| 8 | 消息全链路 + 运维 + 扩展 | 30 min | 端到端消息流、模板系统、部署 |

**总计约 3 小时**。

## 核心术语速查

| 术语 | 含义 | 示例 |
|------|------|------|
| **channel** | IRC 频道（群聊） | `#general`、`#socialware-sy` |
| **nick** | IRC 昵称 | `alice`、`alice-agent0` |
| **private / DM** | IRC 一对一私聊 | PRIVMSG alice-agent0 |
| **scoped name** | 带用户名前缀的 agent 名 | `alice-agent0`（用户 alice 的 agent0） |
| **MCP** | Model Context Protocol | Claude Code 的插件通信协议 |
| **channel-server** | MCP server 进程 | 每个 agent 运行一个 |

> 引用：[CLAUDE.md](../../../CLAUDE.md) 术语部分

## 下一步

进入 [第一章：IRC 协议基础](./01-irc-fundamentals.md)。
