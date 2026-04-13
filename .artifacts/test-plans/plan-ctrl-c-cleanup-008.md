---
type: test-plan
id: test-plan-008
status: draft
producer: skill-2
created_at: "2026-04-13T00:00:00Z"
trigger: "eval-doc-007"
related:
  - eval-doc-007
  - coverage-matrix-002
---

# Test Plan: Ctrl+C 中断 agent create 清理行为

## 触发原因

eval-doc-007 记录了以下 bug：`zchat agent create` 在 `_wait_for_ready()` 轮询期间若被
`KeyboardInterrupt` 中断，`create()` 方法无 try/finally 保护，导致：

1. zellij tab 内 Claude Code 孤儿进程继续运行并连上 IRC
2. 状态文件残留 `status: "starting"`
3. 下次 `create()` 守卫只检查 `"running"`，不拦截 `"starting"` → 重复创建 → IRC nick 冲突

**覆盖缺口**：现有单元测试（`test_agent_manager.py`）只测试 `_wait_for_ready` 正常路径和超时，
无任何 KeyboardInterrupt 场景测试；E2E 测试只测试正常创建流程。

---

## 用例列表

### TC-001: KeyboardInterrupt 中断时调用 _force_stop 清理 tab

- **来源**：eval-doc-007 TC-1
- **优先级**：P0
- **前置条件**：
  - mock `_spawn_tab` 使其返回而不真正创建 zellij tab
  - mock `_wait_for_ready` 使其抛出 `KeyboardInterrupt`
  - mock `_force_stop` 记录是否被调用
  - `project_dir` 已设置
- **操作步骤**：
  1. 构造 `AgentManager` 实例，注入以上 mock
  2. 调用 `mgr.create("helper")`
  3. 捕获 `KeyboardInterrupt`（测试不应 re-raise）
  4. 检查 `_force_stop` 是否被以正确的 `scoped_name` 调用
- **预期结果**：
  - `_force_stop("alice-helper")` 被调用一次
  - `KeyboardInterrupt` 被正确传播（`create()` 不吞掉它）
- **涉及模块**：`zchat/cli/agent_manager.py` — `create()`, `_force_stop()`

---

### TC-002: KeyboardInterrupt 后状态文件写为 "offline"

- **来源**：eval-doc-007 TC-5
- **优先级**：P0
- **前置条件**：
  - mock `_spawn_tab` 正常返回
  - mock `_wait_for_ready` 抛出 `KeyboardInterrupt`
  - mock `_force_stop` 为空操作（不关心 tab 清理）
  - 使用真实 `tmp_path` 作为 state_file 和 project_dir
- **操作步骤**：
  1. 调用 `mgr.create("helper")`，捕获 `KeyboardInterrupt`
  2. 读取 `state_file` 内容（JSON）
  3. 取出 agent `alice-helper` 的 status 字段
- **预期结果**：
  - status == `"offline"`（fix 后应写入 offline）
  - 或者：agent entry 不存在（被清除）
  - **不应出现**：status == `"starting"`
- **涉及模块**：`zchat/cli/agent_manager.py` — `create()`, `_save_state()`

---

### TC-003: status="starting" 时重复 create 被拒绝

- **来源**：eval-doc-007 TC-2 + TC-3
- **优先级**：P0
- **前置条件**：
  - 预加载 state，`alice-helper` 的 status = `"starting"`
  - mock `check_irc_connectivity` 为空操作
- **操作步骤**：
  1. 构造已预加载状态的 `AgentManager`
  2. 调用 `mgr.create("helper")`
  3. 捕获抛出的异常
- **预期结果**：
  - 抛出 `ValueError`，消息中包含 `"starting"` 或 `"already exists"`
  - `_spawn_tab` 未被调用（不产生新进程）
- **涉及模块**：`zchat/cli/agent_manager.py` — `create()` line:73 守卫条件

---

### TC-004: KeyboardInterrupt 后 .ready 文件不残留

- **来源**：eval-doc-007 TC-1 补充
- **优先级**：P1
- **前置条件**：
  - 使用真实 `tmp_path` 作为 project_dir
  - mock `_spawn_tab` 正常返回
  - mock `_wait_for_ready`：先创建 `.ready` 文件，再抛出 `KeyboardInterrupt`
    （模拟 Claude Code 已 ready 但 Python 进程在此时被中断的边缘情况）
  - mock `_force_stop` 为空操作
- **操作步骤**：
  1. 调用 `mgr.create("helper")`，捕获 `KeyboardInterrupt`
  2. 检查 `project_dir/agents/alice-helper.ready` 是否存在
- **预期结果**：
  - `.ready` 文件不存在（fix 后 finally 块应调用 `_cleanup_workspace` 清理）
- **涉及模块**：`zchat/cli/agent_manager.py` — `create()`, `_cleanup_workspace()`

---

### TC-005: 孤儿清理后可正常二次 create

- **来源**：eval-doc-007 TC-2（修复后的正向路径）
- **优先级**：P1
- **前置条件**：
  - 第一次 create 被 KeyboardInterrupt 中断后，状态为 offline（TC-002 已保证）
  - mock `_spawn_tab`、`_wait_for_ready`（返回 True）、`_force_stop`
- **操作步骤**：
  1. 第一次 `mgr.create("helper")`，被 KeyboardInterrupt 中断
  2. 捕获异常
  3. 第二次 `mgr.create("helper")`（不再中断，正常完成）
- **预期结果**：
  - 第二次 create 成功返回，status == `"running"`
  - `_spawn_tab` 被调用了两次（第一次被清理，第二次正常）
- **涉及模块**：`zchat/cli/agent_manager.py` — 完整 create/cleanup 流程

---

### TC-006: 两个 _auto_confirm_startup 线程不同时存活

- **来源**：eval-doc-007 TC-4
- **优先级**：P1
- **前置条件**：
  - 第一次 create 被中断，旧 tab 仍存在（mock `tab_exists` 返回 True）
  - 准备第二次 create
- **操作步骤**：
  1. 第一次 `mgr.create("helper")`，被中断
  2. 第二次 `mgr.create("helper")`
  3. 等待 2 秒后统计活跃的 `_auto_confirm_startup` 相关线程数
- **预期结果**：
  - 活跃的确认线程数 ≤ 1（fix 后旧 tab 已被 `_force_stop` 关闭，旧线程自然退出）
- **涉及模块**：`zchat/cli/agent_manager.py` — `_auto_confirm_startup()`, `_force_stop()`

---

## 统计

| 指标 | 值 |
|------|-----|
| 总用例数 | 6 |
| P0 | 3 |
| P1 | 3 |
| P2 | 0 |
| 来源：eval-doc | 6 |
| 来源：coverage-gap | 0 |
| 来源：code-diff | 0 |

## 风险标注

- **高风险**：`create()` 方法是 agent 生命周期的入口，加 try/finally 须保证正常路径不受影响（TC-005 覆盖正向回归）
- **回归风险**：`_cleanup_workspace` 现有逻辑区分 project_dir 和 tmp 路径，修复不能破坏 stop 命令的清理行为
- **覆盖未知**：TC-006（线程竞争）在 CI 中可能因时序不稳定而偶现失败，建议标记 `@pytest.mark.flaky`

## 实现指引（给 Skill 3）

所有用例为**纯单元测试**，放在 `tests/unit/test_agent_manager.py`，使用 `unittest.mock.patch` 隔离外部依赖：

```python
# mock 目标
patch("zchat.cli.agent_manager.AgentManager._spawn_tab")
patch("zchat.cli.agent_manager.AgentManager._wait_for_ready")
patch("zchat.cli.agent_manager.AgentManager._force_stop")
patch("zchat.cli.agent_manager.check_irc_connectivity")
```

fix 尚未实现，TC-001/002/003 在 fix 前应全部 **FAIL**（用于验证 fix 正确性的回归套件）。
