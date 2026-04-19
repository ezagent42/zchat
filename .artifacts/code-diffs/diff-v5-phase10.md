---
type: code-diff
id: code-diff-v5-phase10
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 10
related:
  - eval-doc-010
  - test-plan-011
  - test-diff-v5-phase10
spec: docs/spec/channel-server-v5.md §4.1 sla, §10.4
plan: docs/discuss/plan/v5-refactor-plan.md §Phase-10
---

# Code Diff: V5 Phase 10 — sla 扩展求助 timer（US-2.5）

## 改动摘要

sla plugin 在原有 takeover timer 基础上新增 help timer。检测 agent 在 `__side:` 中 @operator/@人工/@admin/@客服 → 启动 180s timer；同 channel 内 operator 的 `__side:` 回复 → 取消；超时 emit `help_timeout` event。

## 文件清单

**修改（CS）：**
- `src/plugins/sla/plugin.py`
  - 加 `HELP_MENTION_PATTERNS = ("@operator", "@人工", "@admin", "@客服")`
  - 加 `OPERATOR_SOURCE_MARKERS = ("operator", "ou_")`
  - 加 `_help_timers: dict[str, asyncio.Task]`
  - 加 `_help_timeout_task / _start_help_timer / _cancel_help_timer`
  - `on_ws_message` 分流：side + 求助 pattern → start；source 像 operator → cancel
  - `on_ws_event` mode_changed copilot 时一并 cancel help_timer（防泄漏）

## 关键 diff

```python
HELP_MENTION_PATTERNS = ("@operator", "@人工", "@admin", "@客服")
OPERATOR_SOURCE_MARKERS = ("operator", "ou_")

async def on_ws_message(self, msg):
    parsed = irc_encoding.parse(msg.get("content",""))
    if parsed.get("kind") != "side": return
    text = parsed.get("text","")
    channel = msg.get("channel","")
    if any(p in text for p in HELP_MENTION_PATTERNS):
        self._start_help_timer(channel)
    elif any(m in (msg.get("source","").lower()) for m in OPERATOR_SOURCE_MARKERS):
        self._cancel_help_timer(channel)
```

## 验收

- unit: tests/unit/test_sla_plugin.py — 覆盖 11 个 case（启动/取消/超时/独立/释放兜底）
- e2e: tests/e2e/test_help_request_lifecycle.py — operator 及时回应 / 超时 / 双 timer 独立
