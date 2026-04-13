# zchat 介绍指南（Zellij 版）

基于 [旧版介绍](../introduce/README.md) 更新，反映 tmux → Zellij 迁移后的架构变化。

## 目录

| 章 | 主题 | 变化 | 时间 |
|----|------|------|------|
| [Quick Start](./quick-start.md) | 从零到对话的操作指南 | **全新** | 10 min |
| [第零章](./00-overview.md) | 全局概览与架构变化 | **重写** | 15 min |
| 第一章 | IRC 协议基础 | 无变化，参见 [旧版](../introduce/01-irc-fundamentals.md) | 20 min |
| 第二章 | zchat-protocol | 无变化，参见 [旧版](../introduce/02-protocol.md) | 20 min |
| [第三章](./03-channel-server.md) | channel-server 通信详解 | **重写** — 深入通信机制 | 35 min |
| [第四章](./04-cli-and-zellij.md) | CLI + Zellij 会话管理 | **重写** — tmux → Zellij | 25 min |
| [第五章](./05-agent-lifecycle.md) | Agent 生命周期 | **更新** — Zellij tab 模型 | 25 min |
| 第六章 | IRC 与认证管理 | 小幅更新，参见 [旧版](../introduce/06-irc-auth.md) | 20 min |
| 第七章 | WeeChat 插件 | 无变化，参见 [旧版](../introduce/07-weechat-plugin.md) | 15 min |
| [第八章](./08-communication.md) | 通信全链路深度解析 | **重写** — 重点章节 | 35 min |

**总计约 3.5 小时**（含 Quick Start）

## 与旧版的区别

1. **终端复用器**：tmux + tmuxp → Zellij + KDL layout
2. **配置格式**：`[irc]/[tmux]/[agents]` → 扁平结构 + `[zellij]`
3. **路径管理**：散落在各模块 → 集中在 `paths.py`
4. **新增内容**：通信全链路深度解析（第八章重写）、Quick Start
5. **依赖变化**：移除 `libtmux`/`tmuxp`，新增 `python-dotenv`
