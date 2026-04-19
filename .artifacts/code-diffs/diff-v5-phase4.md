---
type: code-diff
id: code-diff-v5-phase4
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 4
related:
  - eval-doc-010
  - test-plan-011
  - test-diff-v5-phase4
spec: docs/spec/channel-server-v5.md §3.3
plan: docs/discuss/plan/v5-refactor-plan.md §Phase-4
---

# Code Diff: V5 Phase 4 — CS watch routing.toml + auto reload

## 改动摘要

CS 启动后轮询 `routing.toml` mtime（2s），变化时 reload 并对差异 channel 做 IRC JOIN/PART。

## 文件清单

**新增（CS）：**
- `src/channel_server/routing_watcher.py` — `watch_routing(path, router, irc_conn, interval=2.0)` async loop

**修改（CS）：**
- `src/channel_server/router.py` — `update_routing(new_routing)` 方法
- `src/channel_server/irc_connection.py` — `part(channel)` 方法（如缺）
- `src/channel_server/__main__.py` — 启动 watcher task

## 关键 diff（routing_watcher.py）

```python
async def watch_routing(path, router, irc_conn, interval=2.0):
    last_mtime = path.stat().st_mtime if path.exists() else 0
    last_channels = set(router._routing.channels.keys())
    while True:
        await asyncio.sleep(interval)
        try:
            mtime = path.stat().st_mtime if path.exists() else 0
            if mtime == last_mtime: continue
            last_mtime = mtime
            new_routing = load_routing(path)
            router.update_routing(new_routing)
            new_set = set(new_routing.channels.keys())
            for ch in new_set - last_channels:
                irc_conn.join(f"#{ch}")
            for ch in last_channels - new_set:
                irc_conn.part(f"#{ch}")
            last_channels = new_set
        except Exception:
            log.exception("watch routing reload error")
```

## 验收

- unit: tests/unit/test_routing_watcher.py
  - mtime 不变 → 不 reload
  - 新增/删除 channel → JOIN/PART 调用
  - reload 异常 → watcher 不挂
