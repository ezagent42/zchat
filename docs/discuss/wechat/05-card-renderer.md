# 05 · 卡片渲染 — 飞书 Interactive Card → WeCom 模板卡片

## 1. 飞书当前 3 种卡片

`feishu_bridge/feishu_renderer.py`：

| 函数 | 卡片类型 | 出现时机 |
|---|---|---|
| `build_conv_card(conv_id, metadata, mode, state)` | 主对话卡片，含 mode 标 / chat_name / state | conversation 创建时（squad supervise 模式）+ mode 切换时 update |
| `csat_card(conversation_id)` | 评分卡 1-5 星 | conversation_resolved 后请客户评分 |
| `thank_you_card(score)` | 感谢卡 | 客户给完分后展示 |

特征：
- 飞书 Interactive Card 支持 update（同 message_id 改 content）
- 卡片支持 button / select / form / 嵌入图片 / 富文本
- 卡片点击事件通过 `card_action` callback 回到 bridge

## 2. WeCom 卡片现状（受限）

WeCom 的"模板卡片"只是消息推送，**不支持 update**：

| WeCom 模板卡 | 描述 | 限制 |
|---|---|---|
| `text_notice` | 标题 + 描述 + 按钮 | 不可 update |
| `news_notice` | 图文 + 卡片图片 + 按钮 | 不可 update |
| `button_interaction` | 多个按钮 (最多 6) | 按钮点击有 callback |
| `vote_interaction` | 单选/多选投票 | 客户提交后会有 callback |
| `multiple_interaction` | 多个下拉框 | 同上 |

WeCom 也有 `update_template_card` API，**但仅限单聊（user）**，群消息卡片**不能 update**。

## 3. 适配策略

### 3.1 conv_card

| 飞书行为 | WeCom 退化 |
|---|---|
| 创建卡片显示 mode | 发 text_notice 卡，主标题 = conv_id，副标题 = mode |
| mode 切换时 update | **撤回旧卡 + 发新卡**（recall + send） |
| state 改（resolved 等）| 同上 |

撤回限制：仅 24h 内有效。conv 持续超 24h 就没法撤回旧 mode 卡了。可以接受 — 老卡留着不影响功能（agents 不读卡，只看 IRC）。

### 3.2 csat_card

WeCom `vote_interaction` 直接对应：

```json
{
  "card_type": "vote_interaction",
  "main_title": {"title": "服务评分", "desc": "本次服务请打分"},
  "checkbox": {
    "question_key": "csat_score",
    "mode": 0,
    "option_list": [
      {"id": "5", "text": "⭐⭐⭐⭐⭐ 很满意"},
      {"id": "4", "text": "⭐⭐⭐⭐ 满意"},
      {"id": "3", "text": "⭐⭐⭐ 一般"},
      {"id": "2", "text": "⭐⭐ 不满意"},
      {"id": "1", "text": "⭐ 很差"}
    ]
  },
  "submit_button": {"text": "提交", "key": "submit_csat"},
  "task_id": f"csat_{conversation_id}"
}
```

客户点提交 → WeCom 推 `template_card_event` callback：
```xml
<MsgType>event</MsgType>
<Event>template_card_event</Event>
<TaskId>csat_xxx</TaskId>
<CardType>vote_interaction</CardType>
<SelectedItems>
  <SelectedItem>
    <QuestionKey>csat_score</QuestionKey>
    <OptionIds>
      <OptionId>4</OptionId>
    </OptionIds>
  </SelectedItem>
</SelectedItems>
```

bridge 解析 → emit `csat_score` event → audit plugin 接（跟飞书 flow 一样）。

### 3.3 thank_you_card

简单 `text_notice`：
```json
{
  "card_type": "text_notice",
  "main_title": {"title": "感谢您的评价 ⭐⭐⭐⭐", "desc": "我们会持续改进服务"}
}
```

不需 update。

## 4. wecom_renderer.py 完整

```python
"""WeCom 模板卡片 JSON 构建。

跟 feishu_renderer.py 同接口名（build_conv_card / csat_card / thank_you_card）
让 outbound.py 调用方零差异。
"""
from __future__ import annotations


def build_conv_card(
    conv_id: str,
    metadata: dict,
    mode: str = "fast",
    state: str = "active",
) -> dict:
    """主对话卡片（squad supervise 群里展示一个 conv 状态）。

    WeCom 限制：不能 update。callsite 改了 mode/state 时由 outbound 走
    recall + send 流程。
    """
    chat_name = metadata.get("chat_name") or "(未知群)"
    customer = metadata.get("customer", "")
    desc_lines = [
        f"群: {chat_name}",
        f"客户: {customer}" if customer else "",
        f"模式: {_mode_label(mode)}",
        f"状态: {_state_label(state)}",
    ]
    return {
        "card_type": "text_notice",
        "main_title": {
            "title": f"对话 {conv_id}",
            "desc": " · ".join(d for d in desc_lines if d),
        },
        "horizontal_content_list": [
            {"keyname": "Conv ID", "value": conv_id},
            {"keyname": "Mode", "value": _mode_label(mode)},
            {"keyname": "State", "value": _state_label(state)},
        ],
        "task_id": f"conv_{conv_id}_{mode}_{state}",
    }


def csat_card(conversation_id: str) -> dict:
    return {
        "card_type": "vote_interaction",
        "main_title": {
            "title": "本次服务评分",
            "desc": "您的反馈帮助我们改进",
        },
        "checkbox": {
            "question_key": "csat_score",
            "mode": 0,  # 单选
            "option_list": [
                {"id": "5", "text": "⭐⭐⭐⭐⭐ 很满意"},
                {"id": "4", "text": "⭐⭐⭐⭐ 满意"},
                {"id": "3", "text": "⭐⭐⭐ 一般"},
                {"id": "2", "text": "⭐⭐ 不满意"},
                {"id": "1", "text": "⭐ 很差"},
            ],
        },
        "submit_button": {"text": "提交", "key": "submit_csat"},
        "task_id": f"csat_{conversation_id}",
    }


def thank_you_card(score: int) -> dict:
    stars = "⭐" * max(1, min(5, int(score)))
    return {
        "card_type": "text_notice",
        "main_title": {
            "title": f"感谢您的评价 {stars}",
            "desc": "我们会持续改进服务质量",
        },
    }


def _mode_label(mode: str) -> str:
    return {"fast": "Copilot", "takeover": "🔴 人工接管", "auto": "Copilot"}.get(mode, mode)


def _state_label(state: str) -> str:
    return {
        "active": "🟢 进行中",
        "resolved": "✅ 已结束",
        "help_requested": "🚨 求助中",
    }.get(state, state)
```

## 5. update_card 退化流程

`outbound.py` `on_mode_changed` / `on_conversation_closed` 会调用 sender.update_card_sync，但 WeCom 返回 False。
所以 outbound 检测后走 fallback：

```python
def on_mode_changed(self, conversation_id: str, mode: str, **_kw) -> bool:
    thread = self._threads.get(conversation_id)
    if not thread or not thread.card_msg_id:
        return False

    new_card = build_conv_card(conversation_id, thread.metadata, mode=mode,
                               state=thread.state or "active")

    ok = self.sender.update_card_sync(thread.card_msg_id, new_card)
    if ok:
        return True
    # WeCom fallback: recall + send
    self.sender.recall_sync(thread.card_msg_id)
    new_msg_id = self.sender.send_card_sync(thread.metadata["squad_chat_id"], new_card)
    if new_msg_id:
        thread.card_msg_id = new_msg_id
        thread.mode = mode
        return True
    return False
```

## 6. 卡片更新限频

频繁的 mode/state 变更 → 频繁 recall+send → 客户群快速刷屏 + 24h 后老卡撤不掉。

策略：
- **300ms debounce**：300ms 内连续 update 合成一次
- **撤回失败容忍**：log warning 不算错
- **24h 后卡片不再 update**：此后只 send 新卡，旧卡保留（数量很小）

## 7. 客户 WeCom 卡片受限的功能补偿

飞书有 update 能力支撑这些 UX：
- 占位 → 实际答复（`__edit:<placeholder>:<text>`）
- 流式打字效果
- 多轮 thread 内追加内容

WeCom 没法做 placeholder + edit。妥协：
- **取消 placeholder pattern**：fast-agent 直接发完整回复，不发 "让我查一下..." 占位
- **禁用 streaming TTS / streaming text**：客户群里只发完整一条
- 这两条由 `routing.toml` 加 `bridge_features = ["no-placeholder", "no-streaming"]` 标记，agent_mcp 读到后跳过 placeholder 行为

→ 这些是 agent 层适配，不在本 doc 范围。see 11 phase E。

## 8. 卡片点击 callback 解析

WeCom 模板卡片的 `template_card_event`（参见 02 §2.2）解析：

```python
def parse_card_action(msg: dict) -> tuple[str, str, str | None]:
    """从 template_card_event XML msg 拿 (task_id, button_key, selected_id).

    selected_id 仅 vote/checkbox 卡有；button_interaction 卡返回 None.
    """
    task_id = msg.get("TaskId", "")
    card_type = msg.get("CardType", "")

    if card_type in ("vote_interaction", "multiple_interaction"):
        # 解析 SelectedItems > SelectedItem > OptionIds > OptionId
        # （callback handler 已把 XML 解析成 dict — 但嵌套结构需深解）
        items = msg.get("SelectedItems", {}).get("SelectedItem", [])
        if isinstance(items, dict):
            items = [items]
        if items:
            opts = items[0].get("OptionIds", {}).get("OptionId", [])
            if isinstance(opts, list):
                selected_id = opts[0] if opts else None
            else:
                selected_id = opts
            return (task_id, "submit", selected_id)
    elif card_type == "button_interaction":
        # ResponseCode / ButtonKey
        button_key = msg.get("ButtonKey", "")
        return (task_id, button_key, None)
    return (task_id, "", None)
```

## 9. 测试

```python
# tests/unit/test_wecom_renderer.py
from wecom_bridge.wecom_renderer import build_conv_card, csat_card, thank_you_card


def test_csat_card_has_5_options():
    card = csat_card("conv-001")
    assert card["card_type"] == "vote_interaction"
    assert len(card["checkbox"]["option_list"]) == 5
    assert card["task_id"] == "csat_conv-001"


def test_conv_card_includes_mode():
    card = build_conv_card("c1", {"chat_name": "X 群"}, mode="takeover")
    assert "🔴" in card["main_title"]["desc"]


def test_thank_you_card_stars_clamped():
    assert "⭐⭐⭐⭐⭐" in thank_you_card(10)["main_title"]["title"]
    assert "⭐" in thank_you_card(0)["main_title"]["title"]
```
