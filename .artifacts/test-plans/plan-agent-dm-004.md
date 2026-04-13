---
type: test-plan
id: test-plan-004
status: executed
producer: skill-2
created_at: "2026-04-10T14:00:00Z"
trigger: "eval-doc-001 confirmed — Agent 间 IRC DM 直接私聊评估的 11 个 testcase 转换为可执行测试计划"
related:
  - eval-doc-001
---

# Test Plan: Agent 间 DM 私聊功能

## 触发原因

eval-doc-001（Agent 间 IRC DM 直接私聊评估）已通过 review 确认（status: confirmed）。该评估以 simulate 模式分析了 agent 间通过 IRC PRIVMSG 直接私聊的可行性，包含 11 个 testcase 覆盖同用户 DM、跨用户 DM、离线投递、长消息分片等场景。本测试计划将这些 testcase 转换为结构化的 E2E 测试用例。

**注意**：部分用例依赖尚未实现的功能（如 agent 发现、系统消息 MCP tool），在前置条件中标注。当前可直接测试的为 TC-001 ~ TC-003 以及 TC-006、TC-011。

**缺少来源**：无 code-diff（功能尚未开发）、无 coverage-matrix 覆盖对比。

## 用例列表

### TC-001: 同用户两个 agent 间发送 DM

- **来源**：eval-doc（eval-doc-001 #1）
- **优先级**：P0
- **前置条件**：`alice-agent0` 和 `alice-helper` 均在线，连接同一 IRC server，已加入同一频道
- **操作步骤**：
  1. 启动 ergo IRC server 和两个 agent（`alice-agent0`、`alice-helper`）
  2. `alice-agent0` 调用 `reply(chat_id="alice-helper", text="请帮我查一下日志")`
  3. 等待消息送达
- **预期结果**：`alice-helper` 的 `on_privmsg()` 收到消息，`chat_id="alice-agent0"`，消息内容为 "请帮我查一下日志"
- **涉及模块**：channel-server（reply tool, on_privmsg）

### TC-002: Agent 收到 DM 后回复发送方

- **来源**：eval-doc（eval-doc-001 #2）
- **优先级**：P0
- **前置条件**：`alice-helper` 已收到来自 `alice-agent0` 的 DM（TC-001 已通过）
- **操作步骤**：
  1. `alice-helper` 调用 `reply(chat_id="alice-agent0", text="日志已查到，结果如下...")`
  2. 等待消息送达
- **预期结果**：`alice-agent0` 的 `on_privmsg()` 收到回复消息，双向 DM 通道确认可工作
- **涉及模块**：channel-server（reply tool, on_privmsg）

### TC-003: 跨用户 agent 间 DM

- **来源**：eval-doc（eval-doc-001 #3）
- **优先级**：P0
- **前置条件**：`alice-agent0` 和 `bob-agent0` 均在线，分属不同用户，连接同一 IRC server
- **操作步骤**：
  1. 启动两个不同用户的 agent
  2. `alice-agent0` 调用 `reply(chat_id="bob-agent0", text="Bob，你的分析结果如何？")`
  3. 等待消息送达
  4. `bob-agent0` 调用 `reply(chat_id="alice-agent0", text="分析完成")` 回复
- **预期结果**：跨用户 DM 正常送达和回复，IRC PRIVMSG 不区分用户归属
- **涉及模块**：channel-server（reply tool, on_privmsg）

### TC-004: Agent 发现 — 查找在线 agent

- **来源**：eval-doc（eval-doc-001 #4）
- **优先级**：P1
- **前置条件**：多个 agent 在线；**需新增 `list_agents` / `get_channel_users` MCP tool**
- **操作步骤**：
  1. 启动多个 agent
  2. `alice-agent0` 调用新增的 agent 发现 tool
  3. 检查返回结果
- **预期结果**：返回当前在线 agent 列表（nick + 所在频道），agent 可据此决定 DM 目标
- **涉及模块**：channel-server（新增 MCP tool，IRC NAMES/WHO 查询）

### TC-005: DM 发送给离线 agent

- **来源**：eval-doc（eval-doc-001 #5）
- **优先级**：P1
- **前置条件**：`alice-helper` 已停止（IRC QUIT）；**需修复 `_handle_reply` 错误处理**
- **操作步骤**：
  1. 启动 `alice-agent0`，确保 `alice-helper` 未在线
  2. `alice-agent0` 调用 `reply(chat_id="alice-helper", text="你在吗？")`
  3. 检查返回结果
- **预期结果**：返回明确的错误信息（如 "alice-helper 不在线"），而非虚假的 "Sent to alice-helper"
- **涉及模块**：channel-server（_handle_reply, IRC ERR_NOSUCHNICK 401 处理）

### TC-006: 长消息 DM 分片发送

- **来源**：eval-doc（eval-doc-001 #6）
- **优先级**：P1
- **前置条件**：两个 agent 在线，消息内容超过 IRC 512 字节限制
- **操作步骤**：
  1. `alice-agent0` 调用 `reply(chat_id="alice-helper", text=<2000字符文本>)`
  2. 检查接收方收到的消息
- **预期结果**：消息通过 `chunk_message()` 自动分片发送，接收方收到所有分片，内容完整
- **涉及模块**：channel-server（reply tool, chunk_message, on_privmsg）

### TC-007: Agent 区分 DM 来源 — 人类 vs agent

- **来源**：eval-doc（eval-doc-001 #7）
- **优先级**：P1
- **前置条件**：`alice`（人类 WeeChat）和 `bob-agent0`（agent）均在线
- **操作步骤**：
  1. `alice`（人类）通过 WeeChat 向 `alice-agent0` 发送 DM
  2. `bob-agent0` 通过 reply tool 向 `alice-agent0` 发送 DM
  3. 检查 `alice-agent0` 收到的两条消息
- **预期结果**：两条消息的 `chat_id` 分别为 `"alice"` 和 `"bob-agent0"`，可通过 nick 格式（含 `-` 的 scoped name = agent）区分来源类型
- **涉及模块**：channel-server（on_privmsg），zchat-protocol（naming 约定）

### TC-008: 系统消息 — 通过 DM 查询另一个 agent 状态

- **来源**：eval-doc（eval-doc-001 #8）
- **优先级**：P1
- **前置条件**：两个 agent 在线；**需新增 `send_sys_message` MCP tool**
- **操作步骤**：
  1. `alice-agent0` 通过新增 tool 发送 `sys.status_request` 系统消息到 `alice-helper`
  2. `alice-helper` 的 `_handle_sys_message()` 处理并回复
- **预期结果**：`alice-agent0` 收到 `alice-helper` 的状态信息（加入的频道、消息计数等）
- **涉及模块**：channel-server（新增 MCP tool, sys message 协议, _handle_sys_message）

### TC-009: 多轮 DM 对话上下文保持

- **来源**：eval-doc（eval-doc-001 #9）
- **优先级**：P2
- **前置条件**：两个 agent 在线，Claude 上下文窗口可容纳多轮消息
- **操作步骤**：
  1. `alice-agent0` 和 `alice-helper` 进行 5 轮 DM 交互
  2. 每轮消息引用前一轮内容
  3. 检查最后一轮回复是否包含对早期消息的理解
- **预期结果**：双方 Claude 在上下文窗口内保持完整对话历史，每轮回复上下文连贯
- **涉及模块**：channel-server（on_privmsg, reply tool, MCP notification 注入）

### TC-010: 跨 agent 任务委派 — DM 请求协助

- **来源**：eval-doc（eval-doc-001 #10）
- **优先级**：P2
- **前置条件**：`alice-agent0` 和 `alice-reviewer` 在线，后者有代码审查能力
- **操作步骤**：
  1. `alice-agent0` DM `alice-reviewer` 描述代码审查任务
  2. `alice-reviewer` 理解任务并执行
  3. `alice-reviewer` 将结果 DM 回传给 `alice-agent0`
- **预期结果**：任务通过纯文本 DM 完成委派和结果回传，双方 Claude 理解对话意图
- **涉及模块**：channel-server（reply tool, on_privmsg）

### TC-011: DM 中的 @mention 第三方 agent 不触发通知

- **来源**：eval-doc（eval-doc-001 #11）
- **优先级**：P2
- **前置条件**：三个 agent 在线（`alice-agent0`、`alice-helper`、`bob-agent0`）
- **操作步骤**：
  1. `alice-agent0` 向 `alice-helper` 发送 DM："请问 @bob-agent0 有没有更新日志的权限？"
  2. 检查 `bob-agent0` 是否收到通知
- **预期结果**：`bob-agent0` 不收到任何消息。DM 中的 `@mention` 作为纯文本处理，`on_privmsg()` 不调用 `detect_mention()`
- **涉及模块**：channel-server（on_privmsg, on_pubmsg, detect_mention）

## 统计

| 指标 | 值 |
|------|-----|
| 总用例数 | 11 |
| P0 | 3 |
| P1 | 5 |
| P2 | 3 |
| 来源：eval-doc | 11 |
| 来源：code-diff | 0 |
| 来源：coverage-gap | 0 |
| 来源：bug-feedback | 0 |

## 风险标注

- **高风险**：TC-005（离线 DM 投递），当前 `_handle_reply` 返回虚假成功消息，可能导致 agent 误认为任务已传达
- **功能缺失**：TC-004（agent 发现）和 TC-008（系统消息 tool）依赖尚未实现的 MCP tool，需先完成开发再测试
- **覆盖未知**：无 coverage-matrix 输入，所有场景均视为覆盖状态未知
- **回归风险**：TC-006（长消息分片）依赖现有 `chunk_message()` 实现，如改动消息处理链可能影响
