---
name: escalate-to-operator
description: Use when customer requests refund dispute, files complaint, demands human, query is sensitive/out-of-scope, or when delegated deep peer reports no data. Issues @operator side request and waiting message; sla plugin handles 180s timer.
---

# Escalate to Human Operator

## When (allow-list)
**只在以下场景**走人工：
- 退款纠纷 / 规则不清（金额争议）
- 客户明确投诉 / 情绪化抱怨
- delegate-to-deep 已经发委托，deep 回 side 说查不到、建议转人工
- 客户问的不在你的产品线范围

## When NOT (ban-list)
- ❌ 查订单 / 物流 / 清关 / 库存 / CRM / 价格 → 用 `delegate-to-deep`
- ❌ 客户第一条消息还没经过 deep 就直接转人工
- ❌ 客户说"我要查订单" → 这是查询不是投诉

## Steps
1. **side 请求 operator**（仅 squad 群可见，客户群不可见）：
   ```
   reply(chat_id="#<my channel>",
         text="@operator <一句话理由：什么客户、什么诉求、为什么超出我能力>",
         side=true)
   ```
   → sla plugin 自动启 180s help timer + 触发 squad bridge 通知（你不用管）

2. **同时**给客户**等候提示**（普通 reply）：
   ```
   reply(chat_id="#<my channel>", text="这个问题我帮您转人工处理，请稍等")
   ```

3. **等**：
   - 若 180s 内 operator 回 `__side:<text>` → 用 `handle-side-from-operator` skill 处理
   - 若超时 → 收到 `__zchat_sys:help_timeout` 事件 → 发**唯一一次**安抚，**挂到占位下**（如果有）：
     ```
     reply(chat_id="#<my channel>",
           text="抱歉让您久等，正在为您连接人工客服，请稍候",
           edit_of="<placeholder_uuid, 如果之前发过占位>")
     ```
     bridge 把 `__edit:` 映射为 reply，安抚会挂在占位下。如果之前没发占位就直接 `reply` 正常文本。
     **不要循环求助**。

4. **继续正常处理客户消息** —— escalate 不等于"我下班了"。
   - 客户后续 `__msg:` 你照常用 `__msg` 答（参考 operator 通过 side 给的指导口径）
   - 只有收到 `__zchat_sys:mode_changed to=takeover` 系统事件，才进 `handle-takeover-mode`（reply 都 `side=true`）
   - operator 没正式 `/hijack` 之前，**你仍是首响**

## 反模式
- ❌ 把 `@operator` 写在普通 reply 里（应该 side=true，否则客户看到内部喊话）
- ❌ 已发求助还在原 conv 反复 @operator（一次就够）
- ❌ help_timeout 后再 escalate（客户已等很久，再发只会更糟）
- ❌ escalate 后**对客户后续消息装聋作哑**等 operator —— operator 没 takeover 你就还是首响，要继续答（用 side 指导内容）
