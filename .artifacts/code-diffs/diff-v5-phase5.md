---
type: code-diff
id: code-diff-v5-phase5
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 5
related:
  - eval-doc-010
  - test-plan-011
  - test-diff-v5-phase5
spec: docs/spec/channel-server-v5.md §3.1 emit_event, §7.2
plan: docs/discuss/plan/v5-refactor-plan.md §Phase-5
---

# Code Diff: V5 Phase 5 — emit_event 三路广播 + agent 感知

## 改动摘要

`router.emit_event` 同时广播到 WS / plugin registry / IRC `__zchat_sys:`。`agent_mcp` 识别 sys 前缀注入为 system event 而非普通消息。

## 文件清单

**修改（CS）：**
- `src/channel_server/router.py` — emit_event 加 IRC 分支
- `agent_mcp.py` — `_on_pubmsg` 检测 sys 前缀路径分流

## 关键 diff（router.py）

```python
async def emit_event(self, channel, event, data=None):
    msg = ws_messages.build_event(channel, event, data or {})
    await self._ws.broadcast(msg)
    await self._registry.broadcast_event(msg)
    if channel:
        try:
            payload = irc_encoding.make_sys_payload(
                nick="cs-bot", sys_type=event, body=data or {})
            self._irc.privmsg(f"#{channel}", irc_encoding.encode_sys(payload))
        except Exception:
            log.exception("irc sys broadcast failed")
```

## 关键 diff（agent_mcp.py）

```python
def _on_pubmsg(conn, event):
    body = event.arguments[0]
    parsed = irc_encoding.parse(body)
    if parsed["kind"] == "sys":
        # 注入为 system event，不走 mention 检测
        msg = {"id": os.urandom(4).hex(), "nick": event.source.nick,
               "type": "sys", "body": parsed["payload"], "ts": time.time()}
        loop.call_soon_threadsafe(queue.put_nowait, (msg, event.target))
        return
    # 原 mention 检测路径
```

## 验收

- unit: tests/unit/test_router.py — emit_event 三路广播均触发
- unit: tests/unit/test_agent_mcp.py — sys 不被 detect_mention 误匹配
