# Channel Architecture v3 — 彻底重新设计

> 基于手动测试反馈，从零重新设计 channel-server + 飞书 bridge 的架构。

---

## 核心原则

1. **一个飞书群 = 一个 IRC channel**
2. **Bot 决定群类型**（不是 GroupManager 配置决定）
3. **通信路由只有 3 种模式**
4. **每个客户群 = 独立的 agent 实例**

---

## 1. 一个群一个 channel

| 飞书群 | IRC channel | Bot |
|--------|-------------|-----|
| cs-customer-A | #customer-A | customer-bot |
| cs-customer-B | #customer-B | customer-bot |
| cs-squad | #squad | squad-bot |
| cs-admin | #admin | admin-bot |

当前问题：只有 customer 群有 `#conv-` channel，squad 和 admin 群没有 IRC channel。

**新设计**：所有群都映射到 IRC channel。飞书消息进入对应 channel，channel 内的 bot 和 agent 通过 IRC 通信。

---

## 2. Bot 决定群类型

不用 GroupManager 的静态 chat_id 配置判断群类型。**看群里有哪个 bot 就是哪种群**：

- 群里有 customer-bot → 这是客户群
- 群里有 squad-bot → 这是分队群
- 群里有 admin-bot → 这是管理群

或者简化版（v1 只有一个 bot）：**配置文件声明群→类型映射**，但未来目标是多 bot。

---

## 3. 三种通信路由

所有消息都在 channel 中，区别是**是否回到 bridge（飞书）**：

```
模式 1: public（公开）
  A 在 channel @C → C 回复到 channel → bridge 转发到飞书群
  = 客户 @agent，agent 回复，所有人可见

模式 2: side（旁路）
  A 在 channel @C → C 回复到 channel → 不回到 bridge
  = operator 给 agent 指令，客户看不到
  = 消息仍在 IRC channel 中留存（审计）

模式 3: @人（在 channel 中 @特定人）
  A 在 channel @B → B 收到并回复到 channel
  = 人和 bot 在 IRC 中无区别
```

**Side 不是私聊**，还是在 channel 中发的。只是 bridge 不转发到飞书群。
Gate 决定哪些消息 bridge 应该转发，哪些不转发。

映射到 IRC：
- 模式 1 = PRIVMSG #channel :@agent text → agent 回复 → bridge 转发
- 模式 2 = PRIVMSG #channel :@agent text → agent 回复 → bridge 不转发（Gate: side）
- 模式 3 = PRIVMSG #channel :@agent text → 同上，人和 bot 无区别

---

## 4. 模式切换 = 命令

```
/hijack   → operator 接管，agent 消息变 side
/release  → 释放，回到 auto
/copilot  → 旁听，operator 消息变 side
/resolve  → 关闭 conversation
```

这些命令在**任何 channel** 中都可以发（由 command skill 的 agent 处理）。不需要特殊的消息类型——就是普通的 `/` 开头文本。

---

## 5. Admin bot = 有状态命令 skill 的 agent

admin-bot 就是一个 Claude Code agent，装了 admin skill：
- `/status` → 查询所有 active conversation
- `/dispatch agent-name conv-id` → 派发 agent
- 不需要 channel-server 的 CommandHandler——agent 自己通过 MCP tool 查询

---

## 6. Squad bot = 有 review/dispatch skill 的 agent

squad-bot 也是一个 Claude Code agent，装了 squad skill：
- `/review` → 查看统计
- 推送 customer conversation 的卡片到 squad channel
- Thread 中的消息 = side 消息给 customer agent

---

## 7. Customer conversation → squad 推送

当 customer channel 有新对话时：
- channel-server 发一条通知到 #squad channel
- 在飞书中渲染为 card（由 squad-bot 的 bridge 处理）
- Thread 中的消息路由到对应 customer channel 的 side

---

## 8. Thread = side channel

飞书的 thread 功能：
- 点击 squad 群的 conversation card → 进入 thread
- 在 thread 中发消息 = 在 customer channel 中发 side 消息
- Customer 看不到（side visibility）
- Agent 能看到（作为指令/建议）

Admin 和 squad 的 channel 不接收 side 消息（只有 customer channel 有 side）。

---

## 9. 多租户 = 每客户独立 agent 实例组

```
客户 A 进群 → zchat agent create fast-agent-A + deep-agent-A
  → 复制 agent 模板（soul.md / skill / .mcp.json）到 agents/fast-agent-A/
  → 启动独立 Claude Code session
  → IRC nick: yaosh-fast-agent-A, yaosh-deep-agent-A
  → 加入 #customer-A channel

客户 B 进群 → zchat agent create fast-agent-B + deep-agent-B
  → 同上，独立实例
  → 加入 #customer-B channel
```

每个租户（客户）有自己的 agent 实例组（fast + deep），路由到各自的 channel。
agent 模板文件夹复制一份以客户名命名（后续可用 git worktree 替代）。

对外飞书只有一个 bot（cs-bot），但后台每个客户对应独立的 agent CLI 进程。
`/dispatch` 命令把 agent 实例派到指定 channel（群），不是派到飞书群。

---

## 当前实现 vs 新设计对比

| 方面 | 当前 | 新设计 |
|------|------|--------|
| 群→channel | 只有 customer 群有 #conv- | 所有群都有 channel |
| 群类型识别 | GroupManager chat_id 配置 | Bot 身份决定 |
| 消息类型 | customer_message/operator_message/reply/... | 统一 message（3 种路由模式） |
| 命令处理 | channel-server CommandHandler | Agent skill |
| Admin 命令 | 硬编码在 engine/ | Admin agent + admin skill |
| Squad 推送 | VisibilityRouter card+thread | Squad agent + squad skill |
| Agent 实例 | 全局 fast-agent/deep-agent | 每客户独立 agent |
| Mode 切换 | operator_join 触发 | /hijack 命令触发 |
| Side 消息 | visibility_hint（混乱） | IRC PRIVMSG（模式 2） |

---

## 需要重写的部分

| 组件 | 改动 |
|------|------|
| zchat-protocol | message 类型统一，去掉 customer_*/operator_*/admin_* |
| channel-server server.py | 纯路由引擎，不含命令处理 |
| channel-server engine/ | CommandHandler 移到 agent skill，只保留 Gate + 路由表 |
| feishu_bridge | 每种 bot 一个 bridge 实例，或统一 bridge 按 bot 分流 |
| agent_mcp | 支持多实例（每客户一个） |
| zchat CLI | agent create 支持 per-conversation 实例 |

---

## 迁移策略

### Phase 1（最小可用）
- 保持单 bot，但修正路由逻辑
- Squad thread → side message 正确路由
- 卡片按钮正常工作
- WeeChat 自动 join channel

### Phase 2（多 agent）
- 每客户独立 agent 实例
- Agent 通过 soul.md + skill 配置行为

### Phase 3（多 bot）
- Admin bot / Squad bot / Customer bot 分离
- 每种 bot 有自己的 skill set
