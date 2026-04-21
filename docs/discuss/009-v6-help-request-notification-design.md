# V6 Help Request 通知机制设计（零 operator_id 侵入）

> 2026-04-20 · 承接 PRD US-2.5 "Agent @人求助" 的人机衔接设计。
>
> V6 实现中发现：`sla plugin` 检测到 `@operator` 启动 180s timer，但**没有向
> operator 实际通知**（operator 要主动盯 cs-squad 群才知道）。PRD 验收失败。

## 设计原则（硬约束）

1. **零 operator_id 侵入**：routing.toml / 代码不存储、不传递 operator 的飞书 open_id。
   operator 身份由"谁在 squad 群里"**隐含定义**。
2. **agent 之间不直接通信**：fast 发信号，CS plugin 捕获，squad bridge 动作。
   不走 IRC DM，不让 agent 知道"对方是谁"。
3. **routing.toml 保持 generic**：业务语义（客户群名、谁是 operator、卡片内容）
   全在 bridge 业务层运行时派生，不入 routing。

## 事件流

```
fast-agent (#conv-001):
  reply(side=true, text="@operator 客户 X 问题 Y，我处理不了")
    ↓ IRC: __side:@operator ...

sla plugin (CS 层):
  检测到 __side: 中含 @operator/@人工/@admin/@客服 → 启动 180s help_timer (已有)
  ↓ 新增：emit event "help_requested"
       channel: conv-001
       data: {
         reason: "agent_cannot_handle",
         text: "<原消息文本>",
         requesting_agent: "yaosh-fast-001"
       }

CS broadcast event 到 WS + plugin registry + IRC __zchat_sys:

squad bridge 订阅 help_requested:
  1. 取 conv-001 的 supervised card 信息（self.outbound._threads[conv-001]）
  2. 飞书 API：
     a) update_card: title 加 "🚨 求助中"，按钮变 "立即接管"
     b) reply_in_thread(card_msg_id, content="""
        <at user_id="all"></at> 🚨 conv-001（客户群 <chat_name>）求助
        客户问题：<text>
        请在此 thread 回复副驾驶建议，或点卡片"接管"按钮切 takeover 模式
        """)
  3. （可选）若想加强通知：独立在 cs-squad 主聊发一条带 <at user_id="all"/>
     的汇总消息（非 thread 内）

squad-agent (IRC #squad-001) 订阅 __zchat_sys:help_requested:
  - 在 squad 主聊播报："conv-001 (cs-customer) 求助：<text>"
  - 自然语言，让主聊活跃的 operator 直接看到

operator 响应路径：
  - 选项 A：在 thread 里回复 → bridge 转为 __side:<operator_content> 发到 #conv-001
    → sla plugin 检测到 operator 的 side → cancel help_timer (已有)
  - 选项 B：点卡片"接管"按钮 → bridge card_action → CS：/hijack → mode_changed to takeover

超时 180s:
  - sla plugin emit help_timeout (已有)
  - squad bridge 收到 → update_card 标 "⚠️ 求助超时" + 主聊播报
  - fast-agent 收 __zchat_sys:help_timeout → 按 soul.md 给客户发安抚 (已有)
```

## 零 operator_id 的关键

**飞书 `<at user_id="all"></at>` tag** = @所有人（bot 群发权限足够）。
- bot 不需要知道 operator 具体是谁
- 群里所有成员（除 bot）都弹通知
- operator 离群 / 换人 → 自动跟上（下次 @ 自然就覆盖新成员）

## 卡片 title 友好化

当前：`对话 conv-001`。改为：`对话 <飞书群名> · <conv_id>`。

机制：
- customer bridge 在 `on_conversation_created` 或首次处理 conv 时，
  调飞书 `im.v1.chat.get(chat_id).name` 取群名，存本地 cache
- metadata 带 `{"customer_chat_name": "cs-customer", "customer_open_id": "ou_xxx"}`
- 可选：`customer_name` 需要调 `user.get(open_id).name`（API 费一次 call）
- build_conv_card 读 metadata 渲染

**cache 策略**：bridge 内存 dict `chat_id → name`，启动时不预热，收到消息时 lazy get + 存。重启会重新取。

## 实现清单（V6+ 工作量）

| 模块 | 改动 | 工作量 |
|------|------|-------|
| `src/plugins/sla/plugin.py` | 检测 @operator 时 emit `help_requested` event（原 timer 逻辑不变） | 0.1d |
| `src/feishu_bridge/bridge.py` | customer bridge `_forward` 首次见 conv 时调 `get_chat_info`，metadata 带 chat_name + customer_open_id | 0.2d |
| `src/feishu_bridge/bridge.py` | squad bridge 订阅 `help_requested` event → update_card + reply_in_thread `<at all/>` | 0.3d |
| `src/feishu_bridge/feishu_renderer.py` | `build_conv_card` title 读 metadata 里的 chat_name | 0.1d |
| `src/feishu_bridge/bridge.py` | sender filter：忽略本 bot 自发消息（`event.sender.open_id == self._bot_open_id`） | 0.1d |
| `src/plugins/sla/plugin.py` | 超时 emit `help_timeout` + data 带 text（让 squad bridge 能渲染）| 0.1d |
| tests | sla plugin 单元 + squad bridge _handle_help_requested | 0.3d |

**合计 ~1.2 人日**。

## 反模式（已排除）

**❌ routing.toml 加 operator 列表**
```toml
[bots."squad"]
operators = ["ou_xxx", "ou_yyy"]
```
污染 routing；运维地狱；operator 变更要改 routing.toml 重启。

**❌ agent DM 给 squad-agent**
```python
# fast-agent:
reply(chat_id="yaosh-squad-0", text="求助")   # IRC PRIVMSG 直接 DM
```
语义混乱（fast 为啥知道 squad 存在？agent 间耦合），难扩展。

**❌ 飞书 get_chat_members 追踪所有成员**
侵入 / 成员变更要 webhook 同步 / 隐私争议。@all 一样能达到通知效果。

## 依赖飞书 SDK 的项

- `im.v1.chat.get(chat_id)` — 取群名（公开 API，bot 作群成员就有权）
- `im.v1.message.create` with `<at user_id="all"></at>` tag — 飞书官方支持
- `im.v1.message.reply` with `reply_in_thread` — 已用

## 未来扩展

若飞书 @all 被某企业管理员禁用（企业策略可能限制）：
- Fallback 1：不 @，只发卡片 + UI 醒目（红色 icon）
- Fallback 2：用 "应用通知" 类（lark_oapi 的 urgent / important 消息类型）
- Fallback 3：真的要 ID 时，引入 `[bots."squad"].notify_open_ids = [...]`
  但这是真有业务要求再加，不作为 V6 默认

## 状态

- **设计状态**：confirmed（用户 2026-04-20 认可零 operator_id 方向）
- **实现状态**：待开发（阻塞 TC-PR-2.5）
- **归属阶段**：V6 P9（在 V6 sprint 内完成，不放 V7）
