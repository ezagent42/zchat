# 概念入门

如果你用过 Discord、Telegram 或微信，但从没接触过 WeeChat 或 IRC，这篇文档帮你快速理解 zchat 的工作方式。

## 你熟悉的 IM 是怎么工作的

在 Discord 或微信中，你的消息经过一台中央服务器：消息从你的设备发到云端，再分发给其他人。服务器负责存储历史、管理在线状态、推送通知。

zchat 使用本地的 ergo IRC server 来转发消息。同一台机器上的所有 IRC 客户端通过 ergo 通信，不经过任何外部服务器。这意味着：

- **数据不出本机/内网** — 所有消息都在你控制的范围内
- **不依赖外部平台** — 不需要注册 Discord 或 Telegram 账号
- **终端原生** — 一切在 terminal 中完成，和你的开发工作流无缝衔接

## zchat 和你熟悉的 IM 对比

| 概念 | Discord / 微信 | zchat |
|------|---------------|-------|
| 消息传输 | 云端服务器中转 | 本地 ergo IRC server 转发（不经过外部服务器） |
| 群聊 | #频道 / 群 | IRC channel（`/join #channel`） |
| 私聊 | DM / 私信 | IRC private message（`/msg nick`） |
| 在线状态 | 绿点 / 灰点 | IRC presence（JOIN/PART/QUIT） |
| 聊天界面 | GUI 窗口 | WeeChat buffer（终端内的"标签页"） |
| AI 助手 | Bot 账号 | Claude Code 实例（和人类使用完全相同的 IRC 协议） |

## 核心概念

**Buffer** — WeeChat 里的"聊天窗口"。每个 channel 或 private 对话占一个 buffer，类似 Discord 左侧的频道列表项。你可以同时打开多个 buffer，用快捷键切换。

**Nick** — 你的昵称，类似 Discord 用户名。在 IRC 中用 `/nick <name>` 设置。

**Channel** — 群聊，类似 Discord 的频道。任何人都可以加入，消息对所有成员可见。

**Private** — 一对一私聊，类似 Discord 的 DM。消息只有双方可见。

**Agent** — 一个 Claude Code 实例。它在聊天中表现得和人类一样——使用相同的消息格式、走相同的 IRC 协议。你可以同时运行多个 Agent。

## WeeChat 基本操作

WeeChat 运行在终端中，所有操作通过键盘完成：

| 操作 | 方法 |
|------|------|
| 发消息 | 直接打字，按 Enter 发送 |
| 输入命令 | 以 `/` 开头，例如 `/join #team` |
| 切换 buffer | `Alt+数字`（Alt+1, Alt+2...）或 `Alt+←/→` |
| 查看在线成员 | 看 buffer 右侧的 nicklist |
| 滚动历史 | `Page Up` / `Page Down` |
| 关闭当前 buffer | `/part` |

> **提示**：如果你习惯鼠标操作，可以在 WeeChat 中执行 `/mouse enable` 开启鼠标支持。

## 下一步

环境搭好了，概念也了解了，接下来 → [安装与启动](quickstart.md)
