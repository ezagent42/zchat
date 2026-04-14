---
type: code-diff
id: code-diff-006
status: merged
producer: manual
created_at: "2026-04-13T18:17:00Z"
commit: 689c385
related:
  - eval-doc: eval-doc-007
  - issue: agent-create-ctrl-c-cleanup
---

# Code Diff: Ctrl+C 中断 agent create 清理修复

## 提交信息

```
commit 689c385
fix: cleanup orphan Claude Code process on Ctrl+C during agent create

When KeyboardInterrupt fires in _wait_for_ready(), the agent tab was left
running in zellij with status stuck at "starting", causing IRC nick
collision on the next create attempt.

Changes:
- Extend create() guard to block status="starting" (not just "running")
- Wrap _wait_for_ready() in try/except to call _force_stop() +
  _cleanup_workspace() and write status="offline" before re-raising
```

## 核心 Diff（zchat/cli/agent_manager.py）

```diff
-        if name in self._agents and self._agents[name].get("status") == "running":
-            raise ValueError(f"{name} already exists and is running")
+        if name in self._agents and self._agents[name].get("status") in ("running", "starting"):
+            raise ValueError(f"{name} already exists and is running or starting")

         # Wait for ready marker (SessionStart hook)
-        if self._wait_for_ready(name, timeout=60):
-            self._agents[name]["status"] = "running"
-        else:
-            self._agents[name]["status"] = "error"
+        try:
+            if self._wait_for_ready(name, timeout=60):
+                self._agents[name]["status"] = "running"
+            else:
+                self._agents[name]["status"] = "error"
+        except (KeyboardInterrupt, Exception):
+            self._force_stop(name)
+            self._cleanup_workspace(name)
+            self._agents[name]["status"] = "offline"
+            self._save_state()
+            raise
         self._save_state()
```

## 影响模块

- `zchat/cli/agent_manager.py:73` — 守卫条件扩展：`"running"` → `("running", "starting")`
- `zchat/cli/agent_manager.py:90-97` — `_wait_for_ready()` 包裹 try/except，KI 时调用清理链
