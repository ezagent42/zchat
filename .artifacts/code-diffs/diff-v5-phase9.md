---
type: code-diff
id: code-diff-v5-phase9
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 9
related:
  - eval-doc-010
  - test-plan-011
  - test-diff-v5-phase9
spec: docs/spec/channel-server-v5.md §4.2 csat, §10.6
plan: docs/discuss/plan/v5-refactor-plan.md §Phase-9
---

# Code Diff: V5 Phase 9 — CSAT plugin

## 改动摘要

新增 csat plugin。订阅 `channel_resolved` → emit `csat_request` event；订阅 `__csat_score:N` 内容 → 调 `audit.record_csat`。

## 文件清单

**新增（CS）：**
- `src/plugins/csat/__init__.py`
- `src/plugins/csat/plugin.py` — `CsatPlugin(emit_event, audit_plugin)`

**修改（CS）：**
- `src/channel_server/__main__.py` — 注册 csat（依赖 audit_plugin 实例）

## 关键 diff

```python
class CsatPlugin(BasePlugin):
    name = "csat"
    def __init__(self, emit_event, audit_plugin=None):
        self._emit_event = emit_event
        self._audit = audit_plugin

    async def on_ws_event(self, event):
        if event.get("event") == "channel_resolved":
            await self._emit_event("csat_request", event["channel"], {})

    async def on_ws_message(self, msg):
        content = msg.get("content", "")
        if content.startswith("__csat_score:"):
            try: score = int(content.split(":", 1)[1])
            except (ValueError, IndexError): return
            if self._audit:
                self._audit.record_csat(msg["channel"], score)
```

## 事件链

```
/resolve → resolve plugin → channel_resolved
  → audit.record_resolve
  → csat.on_ws_event → emit csat_request
    → bridge 收到 → 发 5 星卡片
    → 客户点 4 星 → bridge 转 __csat_score:4
    → csat.on_ws_message → audit.record_csat
```

## 验收

- unit: tests/unit/test_csat_plugin.py
- e2e: tests/e2e/test_csat_lifecycle.py — 完整 resolve → score → audit.json
