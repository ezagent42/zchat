---
type: e2e-report
id: e2e-report-001
status: green
producer: skill-4
created_at: "2026-04-13T00:00:00Z"
related:
  - test-plan-008
  - eval-doc-007
branch: feat/clear-branch
---

# E2E Report: Ctrl+C cleanup — 红灯阶段（fix 前）

## 结果摘要

| 类别 | 总数 | 通过 | 失败 |
|------|------|------|------|
| 回归用例（已有测试） | 13 | **13** | 0 |
| 新用例 TC-001..006 | 6 | 2 | **4** |
| **合计** | **19** | **15** | **4** |

**整体状态：`partial-pass`（无回归失败，新用例红灯符合预期）**

---

## 回归检查 ✓

13 个已有测试全部通过，新增 TC-001..006 未破坏任何现有功能。

---

## 新用例结果

| 用例 | 函数名 | 结果 | 说明 |
|------|--------|------|------|
| TC-001 | `test_create_calls_force_stop_on_keyboard_interrupt` | **FAIL** | `_force_stop` 未被调用（无 try/finally）|
| TC-002 | `test_create_writes_offline_status_on_keyboard_interrupt` | **FAIL** | status 残留 `"starting"` |
| TC-003 | `test_create_blocked_when_status_is_starting` | **FAIL** | TypeError 非 ValueError（更差的失败模式）|
| TC-004 | `test_create_cleans_ready_marker_on_keyboard_interrupt` | **FAIL** | `.ready` 文件未被清理 |
| TC-005 | `test_create_succeeds_on_second_attempt_after_interrupt` | PASS | 正向路径通过（与 fix 无关） |
| TC-006 | `test_auto_confirm_thread_exits_when_pane_not_found` | PASS | 线程退出行为正确 |

---

## 失败详情

### TC-001 失败
```
AssertionError: Expected '_force_stop' to be called once. Called 0 times.
```
**根因**：`create()` 无 try/finally，KeyboardInterrupt 直接传播，`_force_stop` 从未被调用。

### TC-002 失败
```
AssertionError: status must not remain 'starting' after KeyboardInterrupt, got: starting
```
**根因**：`_save_state()` 在 `_wait_for_ready()` 之后，KI 中断后该调用从未执行，状态永远是 `"starting"`。

### TC-003 失败（比预期更严重）
```
TypeError: Object of type MagicMock is not JSON serializable
  at zchat/cli/agent_manager.py:90 → _save_state()
```
**根因**：守卫条件只检查 `status == "running"`，"starting" 不被拦截，代码继续执行并在 `_save_state()` 崩溃（`tab_name` 含 MagicMock）。预期应抛出 `ValueError`，实际崩溃在更深处。

### TC-004 失败
```
AssertionError: .ready marker should be deleted by _cleanup_workspace in finally block
```
**根因**：无 finally 块，`_cleanup_workspace` 未在中断时调用。

---

## Fix 范围（Phase 6 实施目标）

需修改 `zchat/cli/agent_manager.py`：

1. **`create()` 加 try/finally**（约 8 行）：
   - `finally`：若 status 仍为 `"starting"` → 调用 `_force_stop(name)` + `_cleanup_workspace(name)` + 写状态为 `"offline"`

2. **守卫条件扩展**（1 行，line:73）：
   - `status in ("running", "starting")` 而非仅 `== "running"`

Fix 实施后预期：TC-001/002/003/004 全部转绿，TC-005/006 保持绿色，13 个回归测试保持全绿。
