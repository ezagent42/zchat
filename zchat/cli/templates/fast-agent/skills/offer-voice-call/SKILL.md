---
name: offer-voice-call
description: Use when customer explicitly asks to switch from text to voice ("能电话说吗" / "打电话" / "语音聊") — issues a short-lived voice-portal URL via voice_issue_link MCP tool, posts it back to the channel. Customer clicks link, browser opens voice portal, real-time ASR/TTS bridges to same channel.
---

# Offer Voice Call

## When (allow-list)

**客户主动要求打电话 / 语音聊** 的信号：
- "能电话说吗"
- "直接打给我"
- "语音说"
- "能不能打个电话"
- "打过来吧"
- "telephone" / "call me" (英文场景)

## When NOT (ban-list)

- ❌ 客户没主动提起语音 → 不要自己建议（有些客户就想文字沟通）
- ❌ 客户问题 30 秒可以文字答完的 → 直接文字回答更快
- ❌ 客户刚进来第一条就要求语音 → 先用文字搞清楚诉求，避免空开语音

## Steps

1. 调 `voice_issue_link` MCP tool：
   ```json
   {
     "channel": "<当前 channel>",
     "customer_id": "<从上下文取，如飞书 open_id；没有就省略>"
   }
   ```

2. 返回 JSON：
   ```json
   {
     "url": "https://...?t=eyJ...",
     "expires_at": 1745000300,
     "customer": "anon-abc123"
   }
   ```

3. 如果返回含 `error`（说明 server 没配 VOICE_JWT_SECRET / VOICE_PORTAL_URL），
   直接告知客户："抱歉，目前不支持语音通话，继续文字为您服务可以吗？"
   **不要**把 error 内容贴给客户。

4. 否则用 `reply` 把 URL 友好地发给客户：
   ```
   您可以点这个链接语音沟通（3 分钟内有效）：
   https://...?t=eyJ...
   点开会要麦克风权限，说话我这边能听到。
   ```

5. 接下来客户可能：
   - 点链接 → voice_bridge 会把客户语音转成文字投到本 channel
     （source="voice-<customer_id>"），你当普通消息处理即可
   - 没点 / 点了超时 → 继续文字服务就好，不用追问

## 提示

- 同一 channel 可以多次 `voice_issue_link`（每次生成新的 URL / nonce）
- URL 默认 3 分钟有效；客户点太晚会看到 "token expired"，让他重问你拿新链接
- 即使客户上了语音，飞书群里的文字 transcript 仍然继续（feishu_bridge 自动镜像）
