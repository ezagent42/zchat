# 04 · 入站消息类型映射

## 1. feishu 当前 10 种 parser

`feishu_bridge/message_parsers.py` 通过 `@register_parser("text" | "post" | ...)` 注册：

| 飞书 msg_type | parser 函数 | 输出 (text, attachment_path) |
|---|---|---|
| `text` | `_parse_text` | (content.text, None) |
| `post` | `_parse_post` | (扁平化后的 text, None) |
| `image` | `_parse_downloadable` | (`[图片]`, local file path) |
| `file` | `_parse_downloadable` | (`[文件: name]`, local path) |
| `audio` | `_parse_downloadable` | (`[音频]`, local path) |
| `media` (视频) | `_parse_downloadable` | (`[视频]`, local path) |
| `interactive` | `_parse_interactive` | (extracted text, None) |
| `merge_forward` | `_parse_merge_forward` | (chat history summary, None) |
| `sticker` | `_parse_sticker` | (`[表情]`, None) |
| `share_chat` | `_parse_share_chat` | (`[分享群]`, None) |
| `share_user` | `_parse_share_user` | (`[分享用户]`, None) |
| `location` | `_parse_location` | (`[位置: name]`, None) |
| `todo` | `_parse_todo` | (`[待办]`, None) |

## 2. WeCom 入站 7 种 msg_type

| WeCom MsgType | 字段 | feishu 对应 | wecom_bridge parser |
|---|---|---|---|
| `text` | Content | text | `_parse_text` |
| `image` | PicUrl, MediaId | image | `_parse_image` 下载 media |
| `voice` | MediaId, Format | audio | `_parse_voice` |
| `video` | MediaId, ThumbMediaId | media | `_parse_video` |
| `file` | MediaId, FileName, FileSize | file | `_parse_file` |
| `link` | Title, Description, Url | (无对应) | `_parse_link` 转 text "[链接: title] url" |
| `location` | Location_X, Location_Y, Label | location | `_parse_location` |
| `event` | Event, ChangeType | (元事件，非客户消息) | 不进 parser，走 callback handler 直接路由 |

WeCom **不支持**：rich post / interactive card 入站 / merge_forward / sticker / share_chat / share_user / todo

对客户场景影响：
- ✅ text / image / voice / video / file / location 是核心，覆盖 99% 客户消息
- ⚠️ rich post (飞书) / link (WeCom) 各有侧重 — link 加一个 parser 即可
- ❌ 客户在 WeCom 里发"投票" / "卡片消息" → 我们收不到（WeCom 不推送给企业应用），客户看到 bot 没反应 — UX 风险

## 3. WeCom Media 下载

WeCom 的图片 / 文件 / 语音都是 `MediaId`，3 天有效。下载：

```python
def download_media(client: WeChatClient, media_id: str, save_dir: str) -> str:
    """下载 media 到本地，返回 file path."""
    from wechatpy.work.media import WeChatMedia
    media = WeChatMedia(client)
    response = media.download(media_id)
    # response 是 requests.Response 对象，stream
    ext = response.headers.get("Content-Type", "").split("/")[-1] or "bin"
    fname = f"{media_id}.{ext}"
    path = os.path.join(save_dir, fname)
    with open(path, "wb") as f:
        for chunk in response.iter_content(8192):
            f.write(chunk)
    return path
```

## 4. wecom_bridge/message_parsers.py 完整

```python
"""WeCom 入站消息解析。

每个 parser 返回 (text_for_irc, attachment_path | None)。
text_for_irc 是要进 IRC PRIVMSG 的 content（已转义）。
attachment_path 用于 audit / 后续展示。
"""
from __future__ import annotations

import logging
from typing import Callable

log = logging.getLogger("wecom-bridge.parsers")

ParserFn = Callable[[dict, "Bridge"], tuple[str, str | None]]
_PARSERS: dict[str, ParserFn] = {}


def register_parser(*msg_types: str):
    def deco(fn: ParserFn):
        for mt in msg_types:
            _PARSERS[mt] = fn
        return fn
    return deco


def parse_message(msg: dict, bridge: "Bridge") -> tuple[str, str | None]:
    msg_type = msg.get("MsgType", "text")
    parser = _PARSERS.get(msg_type)
    if not parser:
        log.warning("no parser for MsgType=%s, fallback to text", msg_type)
        return (f"[未支持消息类型: {msg_type}]", None)
    return parser(msg, bridge)


@register_parser("text")
def _parse_text(msg: dict, bridge) -> tuple[str, str | None]:
    return (msg.get("Content", "").strip(), None)


@register_parser("image")
def _parse_image(msg: dict, bridge) -> tuple[str, str | None]:
    media_id = msg.get("MediaId", "")
    pic_url = msg.get("PicUrl", "")
    if media_id and bridge.config.download_media:
        try:
            path = bridge.download_media(media_id, ext="jpg")
            return ("[图片]", path)
        except Exception:
            log.exception("download image failed media_id=%s", media_id)
    return (f"[图片] {pic_url}" if pic_url else "[图片]", None)


@register_parser("voice")
def _parse_voice(msg: dict, bridge) -> tuple[str, str | None]:
    media_id = msg.get("MediaId", "")
    fmt = msg.get("Format", "amr")
    if media_id and bridge.config.download_media:
        try:
            path = bridge.download_media(media_id, ext=fmt)
            return (f"[语音 {fmt}]", path)
        except Exception:
            pass
    return ("[语音]", None)


@register_parser("video")
def _parse_video(msg: dict, bridge) -> tuple[str, str | None]:
    media_id = msg.get("MediaId", "")
    if media_id and bridge.config.download_media:
        try:
            path = bridge.download_media(media_id, ext="mp4")
            return ("[视频]", path)
        except Exception:
            pass
    return ("[视频]", None)


@register_parser("file")
def _parse_file(msg: dict, bridge) -> tuple[str, str | None]:
    media_id = msg.get("MediaId", "")
    fname = msg.get("FileName", "(unknown)")
    fsize = msg.get("FileSize", "?")
    if media_id and bridge.config.download_media:
        try:
            path = bridge.download_media(media_id, ext=os.path.splitext(fname)[1].lstrip("."))
            return (f"[文件: {fname} {fsize}B]", path)
        except Exception:
            pass
    return (f"[文件: {fname}]", None)


@register_parser("link")
def _parse_link(msg: dict, bridge) -> tuple[str, str | None]:
    title = msg.get("Title", "")
    url = msg.get("Url", "")
    desc = msg.get("Description", "")[:100]
    return (f"[链接: {title}] {url} ({desc})", None)


@register_parser("location")
def _parse_location(msg: dict, bridge) -> tuple[str, str | None]:
    label = msg.get("Label", "")
    x = msg.get("Location_X", "")
    y = msg.get("Location_Y", "")
    return (f"[位置: {label} {x},{y}]", None)
```

## 5. 不支持类型策略

WeCom 不发某些类型给企业应用（投票 / 红包 / 转账 / 接龙 / 卡片消息），客户在 WeCom 内点这些不会进 callback。

对策：
1. 一段时间 (15 min) 内若客户发"非文本"消息但企业应用没收到任何东西 → bot 主动回 "目前仅支持文本/图片/语音消息，请直接打字描述需求"
2. UI 引导：在 WeCom 群欢迎语里说明 bot 能力边界

实现：unsupported types 不进 parser，但 wecom_callback_handler 收到 `MsgType` 不在 `_PARSERS` 里 → 推一条 `__zchat_sys: unsupported_message_type` event，agent_mcp 翻译成 sys event，agent 决定要不要主动 nudge 客户。

## 6. 飞书入站 vs WeCom 行为差异表

| 场景 | 飞书 | WeCom |
|---|---|---|
| 客户发 emoji | text 字符 | text 字符 |
| 客户发表情包（系统） | sticker | 不发回调（客户感知 bot 没反应）|
| 客户发图片 | image (msg.image_key) | image (MediaId 3 天有效) |
| 客户发长文/排版 | post (rich) | text (纯文本) |
| 客户分享小程序 | share_user / share_chat | event change_external_*（特殊事件，需单独订阅）|
| 客户 quote 旧消息 | post 嵌 quoted | 文本里附 "↩"，无结构化 quote 信息 |
| 客户撤回 | recall event | event change_external_chat (有时不通知)|

## 7. 单元测试

```python
# tests/unit/test_wecom_parsers.py
from wecom_bridge.message_parsers import parse_message
from unittest.mock import MagicMock


def test_text_parsed():
    text, path = parse_message({"MsgType": "text", "Content": "你好"}, MagicMock())
    assert text == "你好" and path is None


def test_image_with_download():
    bridge = MagicMock()
    bridge.config.download_media = True
    bridge.download_media.return_value = "/tmp/abc.jpg"
    text, path = parse_message({"MsgType": "image", "MediaId": "M1"}, bridge)
    assert text == "[图片]" and path == "/tmp/abc.jpg"


def test_unsupported_type_fallback():
    text, path = parse_message({"MsgType": "miniprogrampage"}, MagicMock())
    assert text.startswith("[未支持消息类型: miniprogrampage]")
```
