---
name: handle-side-from-operator
description: Use when receiving `__side:<text>` WITHOUT `@<my-nick>` prefix. This is operator's private guidance/discussion (squad-thread → bridge → here). Default = acknowledge via side, NOT auto-forward to customer. Only forward when operator explicitly says "tell customer / 告诉客户 / 这话发出去".
---

# Handle Operator Side Guidance

## When
进来一条消息，**完全匹配以下结构**：
```
__side:<text>           ← text 不是以 @<我的 nick> 开头
```
sender 一般是 `cs-bot` 或 bridge 的 IRC nick。**不要**用 sender 做判别，看消息结构。

> 反例（**不**触发本 skill）：
> - `__side:@yaosh-fast-001 ...` —— 点名指令（按指令执行；如果是"请回客户:..." 也按 side→msg 显式转）
> - `__msg:<uuid>:...` —— 客户消息

## Mental model
**side 是 operator-agent 私密协商通道**。客户在 thread 外，永远看不到 side。
operator 发 side 给你的目的通常是：
- 给你**指导口径**（"不退不换"），让你后续按此回客户
- 跟你**讨论**怎么处理一个棘手 case
- 给你**事实补充**（"这单已发货 3 天了"），让你回客户时有依据
- 拒绝你的求助让你自己处理

**默认动作 = 回 side 给 operator**（确认收到 / 跟进），**不**自动 `__msg` 发客户。

## Steps · 默认（绝大多数情况）
1. 用 `reply(side=true)` 回 operator，**简短**确认收到 + 表态怎么用：
   ```
   reply(chat_id="#<my channel>",
         text="收到，按此口径处理。如客户继续追问会引用 <要点摘要>。",
         side=true)
   ```
2. **记住** operator 给的指导（口径 / 事实）。
3. **客户接下来的 `__msg`** 用 `__msg` 正常回（参考 operator 指导，不重复传话）。

## Steps · 显式转发模式
当 operator 在 side 里**明确**说"请回客户" / "告诉客户" / "这话发出去" / "把这条发给他" 时：
1. 抽出真正要发的内容（去掉 operator 给你的前置指令文字）
2. `reply(...)` 普通 `__msg` 发客户
3. 同时 `reply(side=true)` 简短回 operator："已发"

## Steps · operator 让你自己处理
operator 说"你自己想 / 你处理 / 你看着办":
1. side 回："好，我按 <计划> 处理"
2. 等下一条客户 `__msg` 时按计划用 `__msg` 回

## 反模式
- ❌ 把 side 内容**当客户回复草稿**润色后 `__msg` 发出（曾经的错误设计）
- ❌ side 一进来就立即给客户发"已为您处理..."的 `__msg`（客户没问你你别说话）
- ❌ side 进 → 用 `side=false` / 默认（变 `__msg` 客户能看见你回 operator 的话）
- ❌ 已 escalate 求助、operator side 里没明确说 takeover → 你不答客户消息（应该继续答）

## 边界示例

| operator side text | 你的动作 |
|---|---|
| "不退不换" | `side=true` 回："收到，按此口径"；客户下一条问退换 → `__msg` 答 |
| "这单已发货" | `side=true` 回："明白"；客户问物流 → `__msg` 引用此事实答 |
| "请告诉客户：明天发货" | `__msg` 发"您的订单将于明天发出"；`side=true` 回："已发" |
| "你自己想个补偿方案" | `side=true` 回方案候选给 operator 选，不发客户 |
| "这个不退不换，你跟他解释" | `__msg` 发完整解释给客户；`side=true` 回："已解释，等回复" |

## 跟其他 skill 的关系
- 跟 `escalate-to-operator`：escalate 之后通常会收到 operator side 回应。按本 skill 处理 side（默认 side 回），客户继续追问就 `__msg` 答。除非 operator 跑 `/hijack` 触发 `mode_changed=takeover` 才进 `handle-takeover-mode`。
- 跟 `handle-takeover-mode`：takeover 模式下所有 reply 都 `side=true`（不只是 side 输入的回复）；本 skill 的"客户问就 `__msg` 答"在 takeover 模式下被 takeover skill **覆盖**。
