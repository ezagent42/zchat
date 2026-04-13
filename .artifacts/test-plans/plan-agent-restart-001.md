---
type: test-plan
id: test-plan-001
status: draft
producer: skill-2
created_at: "2026-04-10"
trigger: "coverage-gap: Agent 重启流程在 Unit 和 E2E 层均无覆盖"
related:
  - coverage-matrix-002
---

# Test Plan: Agent 重启流程

## 触发原因

coverage-matrix-002 显示 "Agent 重启" 流程在操作 E2E 覆盖中标记为 `❌ not covered`。
Unit 测试层 (`tests/unit/test_agent_manager.py`) 同样没有任何 restart 相关用例。
Pre-release 层 (`tests/pre_release/test_04_agent.py:test_agent_restart`) 仅验证了 nick 重新出现，
未覆盖配置保留、状态转换、异常路径等关键场景。

**来源缺失说明：** 无 code-diff artifact（非代码改动触发，而是覆盖缺口补充）。

## 影响范围

| 模块 | 文件 | 涉及函数 |
|------|------|---------|
| agent_manager | `zchat/cli/agent_manager.py` | `restart()`, `stop()`, `create()`, `_cleanup_workspace()` |
| app (CLI) | `zchat/cli/app.py` | `cmd_agent_restart()` |
| protocol | `zchat-protocol/` | `scoped_name()` |
| zellij | `zchat/cli/zellij.py` | `tab_exists()`, `close_tab()`, `new_tab()` |

## 用例列表

### TC-001: 正常重启运行中的 agent

- **来源**：coverage-gap
- **优先级**：P0
- **前置条件**：agent 已创建并处于 running 状态，IRC 可达
- **操作步骤**：
  1. 创建 agent（`mgr.create("helper")`）并确认状态为 running
  2. 执行 `mgr.restart("helper")`
  3. 检查 agent 状态
- **预期结果**：restart 无异常，agent 最终状态为 running 或 starting（视 ready marker 而定）
- **涉及模块**：agent_manager, zellij

### TC-002: 重启后保留 channels 配置

- **来源**：coverage-gap
- **优先级**：P0
- **前置条件**：agent 以自定义 channels（如 `["#dev", "#ops"]`）创建
- **操作步骤**：
  1. 以 `channels=["#dev", "#ops"]` 创建 agent
  2. 执行 restart
  3. 读取重启后 agent 的 channels 字段
- **预期结果**：重启后 channels 与创建时一致 `["#dev", "#ops"]`
- **涉及模块**：agent_manager

### TC-003: 重启后保留 agent_type 配置

- **来源**：coverage-gap
- **优先级**：P0
- **前置条件**：agent 以自定义 agent_type（如 `"custom-template"`）创建
- **操作步骤**：
  1. 以 `agent_type="custom-template"` 创建 agent
  2. 执行 restart
  3. 读取重启后 agent 的 type 字段
- **预期结果**：重启后 type 与创建时一致 `"custom-template"`
- **涉及模块**：agent_manager

### TC-004: 重启未知 agent 抛出 ValueError

- **来源**：coverage-gap
- **优先级**：P0
- **前置条件**：无名为 "nonexistent" 的 agent
- **操作步骤**：
  1. 执行 `mgr.restart("nonexistent")`
- **预期结果**：抛出 `ValueError`，消息包含 "Unknown agent"
- **涉及模块**：agent_manager

### TC-005: 重启过程中状态转换正确

- **来源**：coverage-gap
- **优先级**：P1
- **前置条件**：agent 已创建并处于 running 状态
- **操作步骤**：
  1. 创建 agent 并确认 running
  2. Mock stop 和 create 方法，在 restart 中捕获调用顺序
  3. 验证 stop 在 create 之前被调用
- **预期结果**：restart 内部先调用 stop(name)，再调用 create(name, channels=..., agent_type=...)
- **涉及模块**：agent_manager

### TC-006: 重启时 _cleanup_workspace 删除 ready marker 但保留 workspace 目录

- **来源**：coverage-gap
- **优先级**：P1
- **前置条件**：agent 已创建，project_dir 已设置，ready marker 文件存在
- **操作步骤**：
  1. 创建 agent，确认 `.agents/<scoped_name>.ready` 文件存在
  2. 执行 stop（restart 的第一步）
  3. 检查 ready marker 和 workspace 目录
- **预期结果**：ready marker 被删除，workspace 目录 `.agents/<scoped_name>/` 保留
- **涉及模块**：agent_manager

### TC-007: CLI `zchat agent restart` 端到端（E2E）

- **来源**：coverage-gap
- **优先级**：P0
- **前置条件**：ergo 运行中，agent 已创建并加入 IRC
- **操作步骤**：
  1. `zchat agent create agent0`，确认 agent 加入 IRC
  2. `zchat agent restart agent0`
  3. 通过 IRC probe 验证 agent nick
- **预期结果**：agent nick 短暂消失后重新出现在 IRC；CLI 输出 "Restarted alice-agent0"
- **涉及模块**：app, agent_manager, zellij, irc

### TC-008: 重启后 agent 能正常接收消息

- **来源**：coverage-gap
- **优先级**：P1
- **前置条件**：agent 已重启成功并 re-join IRC
- **操作步骤**：
  1. 重启 agent（依赖 TC-007）
  2. `zchat agent send agent0 "ping after restart"`
  3. 检查 CLI 无报错
- **预期结果**：send 命令成功执行，无 "not ready" 或 "not running" 错误
- **涉及模块**：agent_manager, zellij

### TC-009: 重启 offline 状态的 agent

- **来源**：coverage-gap
- **优先级**：P1
- **前置条件**：agent 已创建后被 stop，状态为 offline
- **操作步骤**：
  1. 创建 agent
  2. 执行 `mgr.stop("helper")`
  3. 执行 `mgr.restart("helper")`
- **预期结果**：stop 阶段抛出 ValueError（"already offline"），restart 整体失败
- **涉及模块**：agent_manager

### TC-010: 重启时 scoped_name 不会双前缀

- **来源**：coverage-gap（关联 protocol bug: eval-doc-002）
- **优先级**：P1
- **前置条件**：username 为 "alice"，agent name 为 "agent0"
- **操作步骤**：
  1. 创建 `alice-agent0`
  2. restart 使用原始 name "agent0"
  3. 检查 restart 后内部 key 仍为 "alice-agent0" 而非 "alice-alice-agent0"
- **预期结果**：scoped name 保持 "alice-agent0"，不出现双前缀
- **涉及模块**：agent_manager, protocol

## 统计

| 指标 | 值 |
|------|-----|
| 总用例数 | 10 |
| P0 | 4 |
| P1 | 6 |
| P2 | 0 |
| 来源：code-diff | 0 |
| 来源：eval-doc | 0 |
| 来源：coverage-gap | 10 |
| 来源：bug-feedback | 0 |

## 测试分层建议

| 用例 | 建议层级 | 理由 |
|------|---------|------|
| TC-001 ~ TC-006, TC-009, TC-010 | Unit | 可 mock zellij/IRC，验证纯逻辑 |
| TC-007, TC-008 | E2E | 需要真实 ergo + zellij 环境 |

## 风险标注

- **高风险**：restart 是 stop + create 的组合，两个核心路径串联——任一环节失败会导致 agent 处于不一致状态（已 stop 但未 create）
- **回归风险**：restart 复用 `stop()` 和 `create()` 路径，这两个已有部分 E2E 覆盖（test_agent_stop, test_agent_joins_irc），restart 测试可检测组合使用时的回归
- **已知 bug 关联**：scoped_name 双前缀 bug（coverage-matrix-002 已知 bug #6/#7）在 restart 路径上同样存在，TC-010 专门验证此场景
- **缺少来源**：无 code-diff artifact（本次为覆盖缺口补充，非代码改动驱动）
