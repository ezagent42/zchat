# V6 占位消息卡片化 · PRD US-2.2 就地替换设计

> **⚠️ SUPERSEDED (2026-04-21)** — 替代方案：phase 6 `edit → reply-to-placeholder` 语义改造。
> bridge `on_edit(msg_id, text)` 改为 `sender.reply_in_thread(msg_id, text)`，
> 把答复挂到占位消息下（客户视角"稍等…" + 展开答复两层），零协议改动 + 零飞书 API 特殊依赖。
> 本 note 保留作为历史决策记录。

> 2026-04-21 · 承接 TC-PR-2.2 验证失败（fast 占位文本 → deep edit 失败）
>
> 根因：飞书 `im.v1.message.patch` API **只支持卡片消息（msg_type=interactive）**。
> 纯文本消息不可编辑。飞书也**没有**单独的"编辑文本消息"API。

## 官方文档证据

> "待更新的消息 ID，仅支持更新卡片（消息类型为 `interactive`）"
> —— https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/patch

额外限制：
- 只能更新 14 天内发送的消息
- 不能更新批量消息 / 限定可见范围的消息 / 已撤回消息

## 用户决策（2026-04-21）

> "可以占位走卡片。但是这个卡片不应该支持继续通过 thread 对话。
> 正式文本发出，可以就撤回了。"

## 设计（方案 B+）

### 语义约定

1. **占位阶段**：fast 发 `__msg:<uuid>:稍等...`
   - bridge 识别"这是占位"？—— 两条路：
     - **B-1（简洁）**：协议扩展 `__placeholder:<uuid>:<text>` 前缀
       bridge 见 `__placeholder:` 走 send_card，见 `__msg:` 走 send_text
     - **B-2（无协议扩展）**：fast 用 reply tool 时传 `is_placeholder=True`，
       MCP server 翻译为 `__placeholder:` 或 bridge 侧其他标识
   - 推荐 **B-1** —— 显式，zchat-protocol 就该定义这类语义

2. **卡片样式**：最小卡片，单 `div` + text 元素，无按钮、无 header、无 thread 交互
   - 关键：**卡片禁用 thread 回复**
     飞书卡片默认可在 thread 回复；设置 `config.enable_forward: false`
     或更安全地在卡片层不暴露 operator 可入的 thread（卡片对客户发，没人会 thread）
   - 注意这是"客户群里的简卡片"，**不是**"squad 群里的监管卡片"
     两种卡片要区分。客户看到的只是个样式差别很小的文本展示。

3. **替换阶段**：deep 发 `__edit:<uuid>:<final>`
   - bridge 查 `_msg_id_map[uuid]` → 拿到卡片 msg_id
   - 调 `update_card(msg_id, build_text_card(final))` 更新卡片内容
   - 客户侧看到：占位卡片 → 就地内容换成最终答复

4. **卡片→文本迁移**（用户约定）：最终答复出来后，把"答复"从卡片形式替换为**正式文本消息**：
   - 步骤：
     a. update_card 刷卡片显示最终答复（先让客户看到结果，不能有空档）
     b. 撤回该卡片消息（`im.v1.message.delete` 或 `recall`）
     c. send_text 发一条普通文本消息作为"正式答复"
   - 或更好地：跳过 a，直接
     a. send_text 发最终答复
     b. 撤回占位卡片
     
     顺序问题：先发再撤 → 客户看到短暂"两条消息"闪烁
     先撤再发 → 客户看到"占位消失"再"新消息出现"短暂空档
     
     **推荐**：先 send_text，再 recall 占位卡片。时间差很小，"两条消息"闪烁优于"空白"。
     
   - **注意**：recall API 也有限制 —— 必须是本 bot 发的消息且 24h 内，这两条都满足。

### 协议扩展（最小）

`zchat-protocol/irc_encoding.py`：
```python
# 新增 kind
def encode_placeholder(msg_id: str, text: str) -> str:
    return f"__placeholder:{msg_id}:{text}"

def parse(content: str) -> dict:
    # 加分支: content.startswith("__placeholder:")
    #        → {"kind": "placeholder", "message_id": uuid, "text": ...}
```

MCP tool `reply(text, placeholder=False, edit_of=None, side=False)`：
- `placeholder=True` → encode_placeholder
- 其余不变

### Bridge 行为

`outbound.route(kind=...)`：
- `kind=placeholder` → `send_card(customer_chat, text_card(text))` + `_msg_id_map[uuid]=card_msg_id` + `_placeholder_ids.add(card_msg_id)`
- `kind=edit` + uuid 在 `_placeholder_ids` → **两步**：
  1. `send_text(customer_chat, new_text)` 发正式答复
  2. `recall(card_msg_id)` 撤回占位卡片
  3. 清理 `_msg_id_map[uuid]` + `_placeholder_ids`
- `kind=edit` + uuid 不在 `_placeholder_ids` → `update_message(patch)` 兜底（理论上不该发生，text 不可 edit）

### 卡片 config

```python
def placeholder_text_card(text: str) -> dict:
    return {
        "config": {
            "wide_screen_mode": True,
            "update_multi": True,  # 允许 patch
            # 不设 enable_forward、不暴露按钮、不设 header
        },
        "elements": [
            {"tag": "div", "text": {"tag": "plain_text", "content": text}}
        ],
    }
```

- 没 header / 没按钮 / 没 thread 入口
- update_multi: true 是 patch API 要求

## 反模式

**❌ 全局把所有客户消息发成卡片**
太重，影响所有客户消息的 UX 体验；卡片消息在飞书 UI 上和文本差别明显。

**❌ 占位用卡片，edit 也改卡片（不发正式文本）**
客户最终看到"一张卡片"而不是自然文本消息。用户明确要求"正式文本发出"。

**❌ 不撤回占位卡片**
客户看到两条消息："稍等..."（卡片） + "订单..."（文本），违反 PRD US-2.2
"一条完整消息"的体验目标。

## 实现清单

| 模块 | 改动 | 工作量 |
|------|------|-------|
| `zchat-protocol/irc_encoding.py` | 加 `encode_placeholder` + parse 分支 | 0.1d |
| `zchat-channel-server/agent_mcp.py` | `reply(..., placeholder=False)` → 协议 | 0.1d |
| `feishu_bridge/sender.py` | `send_card` 已有；加 `recall_message(msg_id)` | 0.1d |
| `feishu_bridge/outbound.py` | `route` 加 placeholder/edit 分支 + `_placeholder_ids` set | 0.3d |
| `feishu_bridge/feishu_renderer.py` | `placeholder_text_card(text)` 单元素卡片 | 0.1d |
| `fast-agent/soul.md` | 占位用 `reply(text=..., placeholder=True)` | 0.05d |
| tests | outbound placeholder→edit 替换；recall 调用时机 | 0.3d |

**合计 ~1.05 人日**。

## 关联文档

- PRD US-2.2 "简单模型首响 + 复杂模型接管"
- V6 help request 设计：`v6-help-request-notification-design.md`
- V6 pre-release test plan：TC-PR-2.2 当前因此阻塞

## 状态

- **设计状态**：confirmed（用户 2026-04-21 认可"占位卡片 + 正式文本 + 撤回"方向）
- **实现状态**：待开发（阻塞 TC-PR-2.2 验收）
- **归属阶段**：V6 P10（在 V6 sprint 内完成）
