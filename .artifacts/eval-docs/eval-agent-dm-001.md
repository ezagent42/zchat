---
type: eval-doc
id: eval-doc-001
status: draft
producer: skill-5
created_at: "2026-04-10"
mode: simulate
feature: "Agent 间 IRC DM 直接私聊"
submitter: "Sy Yao"
related: []
---

# Eval: Agent 间 IRC DM 直接私聊

## 基本信息
- 模式：模拟
- 提交人：Sy Yao
- 日期：2026-04-10
- 状态：draft

## Feature 描述

支持 zchat agent 之间通过 IRC PRIVMSG 直接私聊，不经过频道。典型场景：`alice-agent0` 直接向 `alice-helper` 发送消息请求协助，或 `bob-agent0` 向 `alice-agent0` 发起跨用户协作。

## 架构分析摘要

**已有基础设施：**
- `on_privmsg()` (server.py:133-154) 已处理所有入站 PRIVMSG，非系统消息路由到 MCP，`chat_id=sender_nick`
- `reply` MCP tool (server.py:270-278) 已支持 `chat_id` 为 nick（非 `#channel`）
- `/zchat:dm` command 存在，是 `reply` 的便利封装
- 系统消息协议 (`__zchat_sys:`) 已通过 PRIVMSG 传输，支持 agent 间控制指令

**缺失能力：**
- 无 agent 发现机制（不知道谁在线）
- 无投递确认 / ACK
- 无跨 agent 工具调用协议
- 无 agent vs 人类用户的身份区分
- instructions.md 未充分文档化 agent 间 DM 用法

## Testcase 表格

| # | 场景 | 前置条件 | 操作步骤 | 预期效果 | 模拟效果 | 差异描述 | 优先级 |
|---|------|---------|---------|---------|---------|---------|--------|
| 1 | 同用户两个 agent 间发送 DM | `alice-agent0` 和 `alice-helper` 均在线且连接同一 IRC server | `alice-agent0` 调用 `reply(chat_id="alice-helper", text="请帮我查一下日志")` | `alice-helper` 收到 DM，Claude 识别为来自 `alice-agent0` 的私聊，可正常回复 | **可行**。`reply` tool 已支持 nick 目标，IRC PRIVMSG 直接送达。`alice-helper` 的 `on_privmsg()` 接收并注入 MCP，`chat_id="alice-agent0"`。Claude 可识别为 DM 并回复。 | 无核心差异。但 `alice-helper` 的 Claude 需在 instructions 中被告知如何处理来自其他 agent 的 DM（当前 instructions.md 仅列为 "Other user DM / Normal priority"，未区分 agent vs 人类） | P0 |
| 2 | Agent 收到 DM 后回复发送方 | `alice-helper` 已收到来自 `alice-agent0` 的 DM | `alice-helper` 调用 `reply(chat_id="alice-agent0", text="日志已查到，结果如下...")` | 消息送达 `alice-agent0`，双向对话建立 | **可行**。回复路径与发送路径对称，`reply` tool 以 `alice-agent0` 为 target 发出 PRIVMSG，对方 `on_privmsg()` 接收。 | 无。双向 DM 在现有架构下完全可工作。 | P0 |
| 3 | 跨用户 agent 间 DM | `alice-agent0` 和 `bob-agent0` 均在线，分属不同用户 | `alice-agent0` 调用 `reply(chat_id="bob-agent0", text="Bob，你的分析结果如何？")` | `bob-agent0` 收到 DM 并可回复 | **可行**。IRC PRIVMSG 不区分用户归属，只要两个 nick 在同一 IRC server 上即可通信。跨用户 DM 与同用户 DM 走相同代码路径。 | 无技术差异。但涉及权限问题：`bob-agent0` 的 instructions 中将 `alice-agent0` 视为 "Other user DM"（Normal priority），可能不会主动响应非 owner 的请求。需要 agent instructions 定义跨用户协作策略。 | P0 |
| 4 | Agent 发现：查找在线 agent | 多个 agent 在线，`alice-agent0` 想知道谁可以联系 | `alice-agent0` 尝试列出可 DM 的 agent | 返回当前在线 agent 列表（nick + 所在频道） | **不可行**。当前无 `list_users` 或 `get_channel_members` MCP tool。agent 无法发现其他在线 agent。需新增 MCP tool 查询 IRC NAMES/WHO 命令结果。 | **关键缺失**。无发现机制意味着 agent 必须预先知道对方 nick 才能 DM，严重限制动态协作场景。 | P1 |
| 5 | DM 发送给离线 agent | `alice-helper` 已停止（IRC QUIT），`alice-agent0` 尝试 DM | `alice-agent0` 调用 `reply(chat_id="alice-helper", text="你在吗？")` | 发送失败，agent 收到明确的错误反馈 | **部分可行**。IRC `PRIVMSG` 到不存在的 nick 会被 IRC server 返回 `ERR_NOSUCHNICK (401)`。但 `_handle_reply()` (server.py:270-278) 不捕获 IRC 错误——它只是调用 `connection.privmsg()` 然后返回成功消息 `"Sent to alice-helper"`。agent 不知道消息未送达。 | **差异显著**。agent 会收到虚假的"发送成功"反馈。需要在 `_handle_reply` 中注册 IRC error handler 捕获 `ERR_NOSUCHNICK` 并返回错误。 | P1 |
| 6 | 长消息 DM | 消息超过 IRC 512 字节限制 | `alice-agent0` 发送一段 2000 字符的分析报告给 `alice-helper` | 消息自动分片发送，接收方收到完整内容 | **可行**。`_handle_reply()` 调用 `chunk_message(text)` (message.py) 对长消息分片。每片 ≤ IRC 限制，依次发送。接收方 `on_privmsg()` 分别收到每片。 | 分片发送可工作，但接收方会收到多条独立消息而非重组后的完整消息。Claude 在上下文中可以拼接理解，但 `chat_id` 和 `message_id` 不含分片信息，无法程序化重组。对 agent 间传递结构化数据（如 JSON）有风险。 | P1 |
| 7 | Agent 区分 DM 来源：人类 vs agent | `alice`（人类，WeeChat）和 `bob-agent0`（agent）分别向 `alice-agent0` 发 DM | 两条 DM 分别送达 | agent 能区分消息来自人类还是其他 agent，并采用不同响应策略 | **部分可行**。两条消息都通过 `on_privmsg()` 送达，`chat_id` 分别为 `"alice"` 和 `"bob-agent0"`。从 nick 格式可推断：含 `-` 的 scoped name（如 `bob-agent0`）是 agent，纯 nick 是人类。但这是命名约定，非强制校验。 | agent 的 Claude 可通过 nick 格式启发式判断，但无可靠的身份验证机制。恶意用户可注册 agent 风格的 nick 冒充。instructions 需补充 agent nick 识别规则。 | P1 |
| 8 | 系统消息：通过 DM 查询另一个 agent 状态 | `alice-agent0` 想检查 `alice-helper` 是否在线且状态正常 | 发送系统消息 `sys.status_request` 到 `alice-helper` | 返回 `alice-helper` 的状态（加入的频道、消息计数等） | **可行**。系统消息协议已支持此场景。`make_sys_message()` + `encode_sys_for_irc()` 生成 `__zchat_sys:{...}` 消息，通过 PRIVMSG 送达。`alice-helper` 的 `_handle_sys_message()` 处理 `sys.status_request` 并回复。 | 无差异，这是现有功能。但当前只有 CLI (`zchat agent send`) 触发系统消息，agent 自身的 Claude 没有 MCP tool 来主动发送系统消息。需新增 `send_sys_message` tool。 | P1 |
| 9 | 多轮 DM 对话上下文保持 | `alice-agent0` 与 `alice-helper` 进行 5 轮 DM 交互 | 连续发送/接收 5 轮消息 | 双方 Claude 保持完整对话上下文 | **可行但有限制**。每条 DM 作为独立 MCP notification 注入 Claude 上下文。Claude 的上下文窗口内可以看到所有历史 DM。但 `chat_id` 是 sender nick，不含 "conversation ID"——如果 agent 同时与多人 DM，所有 DM 混在同一个 Claude 上下文中。 | Claude 能处理多轮对话，但无隔离机制。如果 `alice-agent0` 同时与 `helper` 和 `bob-agent0` DM，三方消息交织可能造成混淆。需要 Claude instructions 明确按 `chat_id` 区分对话线程。 | P2 |
| 10 | 跨 agent 任务委派：DM 请求协助 | `alice-agent0` 发现需要代码审查，想委派给 `alice-reviewer` | DM `alice-reviewer` 描述任务，等待结果回传 | `alice-reviewer` 理解任务、执行、将结果 DM 回传 | **部分可行**。文本层面的任务委派可工作（DM 传递描述 + 结果），但无结构化的任务协议。无法传递文件引用、代码片段、工具调用等结构化数据。agent 只能通过自然语言描述和 IRC 纯文本交互。 | 功能可用但体验粗糙。对比理想状态（如 A2A 协议的结构化 task delegation），当前只有纯文本信道。适合简单请求，不适合复杂多步任务。考虑未来通过系统消息扩展 `sys.task_request`/`sys.task_response` 协议。 | P2 |
| 11 | DM 中的 @mention 第三方 agent | `alice-agent0` 在与 `alice-helper` 的 DM 中提到 `@bob-agent0` | 发送 DM: `"请问 @bob-agent0 有没有更新日志的权限？"` | `@bob-agent0` 不被转发（DM 中的 mention 不应触发第三方通知） | **符合预期**。`on_privmsg()` 不调用 `detect_mention()`（仅 `on_pubmsg()` 做 mention 检测）。DM 中的 `@` 作为纯文本处理，不会触发任何路由。 | 无差异。当前设计正确隔离了 DM 和 channel mention 的行为。 | P2 |

## 可行性总结

### 架构匹配度：高

现有 IRC 基础设施（PRIVMSG + `on_privmsg()` + `reply` tool）天然支持 agent 间 DM，无需新增传输层。核心消息通路已打通。

### 需新增的能力

| 能力 | 复杂度 | 关联 Testcase |
|------|--------|---------------|
| Agent 发现 MCP tool (`list_agents` / `get_channel_users`) | 中 | #4 |
| DM 投递失败反馈（捕获 `ERR_NOSUCHNICK`） | 低 | #5 |
| Agent 身份验证 / nick 类型判断 | 低 | #7 |
| 发送系统消息的 MCP tool | 中 | #8 |
| DM 对话线程隔离指导（instructions 更新） | 低 | #9 |
| 结构化任务委派协议（`sys.task_*`） | 高 | #10 |

### 风险点

1. **无投递确认**：agent 发 DM 给离线 agent 会收到虚假成功，可能导致任务丢失
2. **身份冒充**：IRC 无内建身份验证，恶意用户可注册 agent 风格 nick
3. **上下文污染**：多方并发 DM 混入同一 Claude 上下文窗口，高并发场景下可能混淆
4. **消息分片**：长消息分片后无法程序化重组，影响结构化数据传递

## 后续行动

- [x] eval-doc 已注册到 .artifacts/eval-docs/
- [ ] 用户已确认 testcase 表格 (status: draft → confirmed)
