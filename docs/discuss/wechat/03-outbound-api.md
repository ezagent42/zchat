# 03 · 出站 API — 重写 sender

## 1. 飞书 sender 当前调用全集

`feishu_bridge/sender.py` 通过 `lark.Client.im.v1.message.{create,patch,reply,delete}` 实现这 5 个能力：

| 方法 | 飞书 API | 用途 |
|---|---|---|
| `send_text_sync(chat_id, text)` | `message.create(msg_type=text)` | 普通文本回复 |
| `send_card_sync(chat_id, card_json)` | `message.create(msg_type=interactive)` | 发交互卡片（mode 卡 / CSAT 卡）|
| `update_card_sync(msg_id, card_json)` | `message.patch` | 更新卡片内容（mode 切换、求助标）|
| `reply_in_thread_sync(parent_msg_id, text/card)` | `message.reply` | thread 回复（squad supervise 用）|
| `recall_sync(msg_id)` | `message.delete` | 撤回 |
| `get_chat_info_sync(chat_id)` | `chat.get` | 拿群名（lazy_create 时显示用）|

## 2. WeCom 端点对照

| feishu sender method | WeCom 端点 | 备注 |
|---|---|---|
| `send_text` (单聊) | `POST cgi-bin/message/send` `msgtype=text` | touser / toparty / totag |
| `send_text` (群聊) | `POST cgi-bin/appchat/send` `msgtype=text` | chatid 字段 |
| `send_card` | `POST cgi-bin/message/send` `msgtype=template_card` | 模板卡片，受限 |
| `update_card` | **没有 native 等价** | WeCom 只支持 `update_template_card` 给单个 user，不能 update 群卡片 → 详见 05 |
| `reply_in_thread` | **不支持 thread** | WeCom 群无 thread 概念 → 详见 08 |
| `recall` | `POST cgi-bin/message/recall` | 仅企业自建 应用消息可撤回，限 24h |
| `get_chat_info` | `GET cgi-bin/appchat/get?chatid=X` | 返回 name + owner + userlist |

## 3. wechatpy SDK 调用示例

```python
from wechatpy.work import WeChatClient

# 初始化
client = WeChatClient(corp_id="ww123", secret="xyz")
client.session = MyTokenCache()  # 控 access_token 缓存策略，详见 07

# 发文本到群
client.appchat.send(
    chat_id="wm_xxxx",
    msg_type="text",
    text={"content": "您好"},
)

# 发模板卡片到群
client.appchat.send(
    chat_id="wm_xxxx",
    msg_type="template_card",
    template_card={
        "card_type": "text_notice",
        "main_title": {"title": "服务模式", "desc": "Copilot Mode"},
        "card_action": {"type": 1, "url": "https://x.y/action"},
        "task_id": "csat_abc123",   # 后续接 callback 时用
        "button_selection": {
            "question_key": "score",
            "options": [
                {"id": "1", "text": "差"},
                {"id": "5", "text": "好"},
            ],
        },
    },
)

# 撤回（企业内部消息）
client.message.recall(msgid="MESSAGE_ID")

# 群信息
info = client.appchat.get(chat_id="wm_xxxx")
# → {"errcode": 0, "chat_info": {"chatid": ..., "name": ..., "userlist": [...]}}
```

## 4. wecom_bridge/sender.py 完整设计

```python
"""WeCom 消息发送封装 — text / card / recall / get_chat_info。

跟 feishu_bridge/sender.py 同接口名（_sync 后缀），让 outbound.py 几乎不动。
"""
from __future__ import annotations

import logging
from typing import Any

from wechatpy.work import WeChatClient

log = logging.getLogger("wecom-bridge.sender")


class WeComSender:
    """WeCom API 发送封装。

    提供 *_sync 同步方法（callback handler 在 aiohttp 协程里调，但内部
    wechatpy 是同步 requests，所以 *_sync 命名其实是"阻塞"，bridge 用
    asyncio.to_thread 包装非阻塞调用）。
    """

    def __init__(self, corp_id: str, corp_secret: str, agent_id: int,
                 token_cache: Any | None = None) -> None:
        self._client = WeChatClient(corp_id=corp_id, secret=corp_secret)
        if token_cache:
            self._client.session = token_cache
        self._agent_id = agent_id

    # ── 文本 ────────────────────────────────────────────────────────

    def send_text_sync(self, chat_id: str, text: str) -> str | None:
        """发到群。返回 msgid 或 None。"""
        try:
            resp = self._client.appchat.send(
                chat_id=chat_id,
                msg_type="text",
                text={"content": text},
                safe=0,
            )
            if resp.get("errcode") != 0:
                log.warning("send_text errcode=%s msg=%s", resp.get("errcode"), resp.get("errmsg"))
                return None
            return str(resp.get("msgid", ""))
        except Exception as e:
            log.exception("send_text exception: %s", e)
            return None

    # ── 卡片 ────────────────────────────────────────────────────────

    def send_card_sync(self, chat_id: str, card_json: dict) -> str | None:
        """发模板卡片到群。card_json 是 wecom_renderer 出的 template_card 结构。"""
        try:
            resp = self._client.appchat.send(
                chat_id=chat_id,
                msg_type="template_card",
                template_card=card_json,
            )
            if resp.get("errcode") != 0:
                log.warning("send_card errcode=%s msg=%s",
                            resp.get("errcode"), resp.get("errmsg"))
                return None
            return str(resp.get("msgid", ""))
        except Exception as e:
            log.exception("send_card exception: %s", e)
            return None

    def update_card_sync(self, msg_id: str, card_json: dict) -> bool:
        """⚠️ WeCom 群卡不支持服务端 update。
        策略：撤回旧 + 发新。详见 05。
        """
        log.warning("update_card requested for msg_id=%s — falling back to recall+send",
                    msg_id)
        # 此函数目前只 log 一个 warning；实际 update 由调用方走 recall+send 流程
        return False

    # ── 撤回 ────────────────────────────────────────────────────────

    def recall_sync(self, msg_id: str) -> bool:
        try:
            resp = self._client.message.recall(msgid=msg_id)
            return resp.get("errcode") == 0
        except Exception as e:
            log.warning("recall exception: %s", e)
            return False

    # ── reply 不存在 ────────────────────────────────────────────────

    def reply_in_thread_sync(self, parent_msg_id: str, text_or_card: Any) -> str | None:
        """WeCom 没 thread 概念。改成发独立消息 + 引用 parent text。
        详见 08 supervise 模式。
        """
        log.debug("reply_in_thread fallback: sending standalone msg")
        if isinstance(text_or_card, str):
            quoted = f"↩ 引用前消息：\n{text_or_card}"
            return self.send_text_sync(parent_msg_id_to_chat(parent_msg_id), quoted)
        return None

    # ── 群信息 ──────────────────────────────────────────────────────

    def get_chat_info_sync(self, chat_id: str) -> dict | None:
        try:
            resp = self._client.appchat.get(chat_id=chat_id)
            if resp.get("errcode") != 0:
                return None
            return resp.get("chat_info", {})
        except Exception as e:
            log.warning("get_chat_info exception: %s", e)
            return None
```

## 5. asyncio 集成

bridge.py 的 outbound 调用应该在 thread pool 里：

```python
# wecom_bridge/bridge.py
async def _send_text_async(self, chat_id, text):
    return await asyncio.to_thread(self.sender.send_text_sync, chat_id, text)
```

或者直接用 `wechatpy.work.aio.WeChatClient`（如果版本支持）— 但稳定性、文档都不如同步版。

**推荐：sync sender + asyncio.to_thread**。

## 6. Rate limit

WeCom API 有限频：
- `message/send`: 60 次/分钟/应用
- `appchat/send`: 100 次/分钟/应用
- `appchat/get`: 1000 次/分钟

对正常对话场景无压力。但 supervise 镜像场景（一条客户消息→ supervisor 群也要镜像→ 再加 mode 卡更新）容易超限。

需要：
- sender 内置 token bucket 限流
- 卡片更新合并（300ms 内多次 update 合成一次）

具体见 08。

## 7. 重试策略

WeCom API 失败常见错误码：
- `40014` invalid access_token → 触发 token refresh，retry 1 次
- `42001` access_token expired → 同上
- `45009` reach max api daily quota → log error，**不重试**
- `48002` api forbidden → 配置错，**不重试**
- 网络超时 → exponential backoff，max 3 次

实现：

```python
def _call_with_retry(self, fn, *args, max_retries=2, **kwargs):
    delay = 0.5
    for attempt in range(max_retries + 1):
        try:
            resp = fn(*args, **kwargs)
            err = resp.get("errcode") if isinstance(resp, dict) else 0
            if err in (40014, 42001):
                self._client.fetch_access_token()  # force refresh
                continue
            if err == 0:
                return resp
            if err in (45009, 48002):
                log.error("non-retryable %s", err)
                return resp
            time.sleep(delay)
            delay *= 2
        except (requests.Timeout, requests.ConnectionError) as e:
            log.warning("attempt %d failed: %s", attempt, e)
            time.sleep(delay)
            delay *= 2
    return None
```

## 8. 接口契约对照

为了让 outbound.py / bridge.py 几乎不需要改，wecom Sender 必须保持跟 feishu Sender **完全相同**的方法签名：

| feishu_bridge.FeishuSender | wecom_bridge.WeComSender |
|---|---|
| `send_text_sync(chat_id, text) -> str \| None` | ✅ 同 |
| `send_card_sync(chat_id, card_json) -> str \| None` | ✅ 同（card_json 内部结构不同，由 renderer 出）|
| `update_card_sync(msg_id, card_json) -> bool` | ⚠️ 返回 False，调用方需 fallback |
| `reply_in_thread_sync(parent_msg_id, text_or_card) -> str \| None` | ⚠️ 退化成独立消息 |
| `recall_sync(msg_id) -> bool` | ✅ 同 |
| `get_chat_info_sync(chat_id) -> dict \| None` | ✅ 同（dict 结构略不同：飞书 `name` vs WeCom `chat_info.name`）|

outbound.py 检测到 `update_card_sync` 返回 False 时走 recall+send fallback。

## 9. 单元测试

```python
# tests/unit/test_wecom_sender.py
from unittest.mock import MagicMock, patch
import pytest
from wecom_bridge.sender import WeComSender


def test_send_text_returns_msgid():
    s = WeComSender("ww1", "secret", agent_id=1000001)
    s._client = MagicMock()
    s._client.appchat.send.return_value = {"errcode": 0, "msgid": "MSG123"}
    assert s.send_text_sync("wm_x", "hi") == "MSG123"


def test_send_text_handles_errcode():
    s = WeComSender("ww1", "secret", agent_id=1000001)
    s._client = MagicMock()
    s._client.appchat.send.return_value = {"errcode": 40014, "errmsg": "bad token"}
    assert s.send_text_sync("wm_x", "hi") is None


def test_update_card_returns_false_warns():
    s = WeComSender("ww1", "secret", agent_id=1000001)
    assert s.update_card_sync("MSG123", {}) is False
```
