---
type: test-plan
id: test-plan-002
status: draft
producer: skill-2
created_at: "2026-04-10"
trigger: "code-diff-restart-001: restart 函数重构为 graceful stop + create"
related:
  - code-diff-restart-001
  - coverage-matrix-002
---

# Test Plan: Restart 重构验证

## 触发原因

code-diff-restart-001 重构了 `agent_manager.py` 的 `restart()` 方法：改为先 graceful stop（调用 `self.stop()` 含 `pre_stop` hook + `_cleanup_workspace()`），再 `self.create()` 重建 agent，并从 agent dict 中保留 channels 和 agent_type 配置。

coverage-matrix-002 显示 "Agent 重启" 在 E2E 层 ❌ not covered，Unit 层同样无 restart 测试用例。

## 用例列表

### TC-001: Graceful stop 在 restart 中执行

- **来源**：code-diff
- **优先级**：P0
- **前置条件**：agent 已创建并处于 running 状态
- **操作步骤**：
  1. 创建 agent（`mgr.create("helper")`），确认状态 running
  2. Mock `self.stop` 和 `self.create`，执行 `mgr.restart("helper")`
  3. 验证 `stop` 被调用（而非直接 `_force_stop`），且在 `create` 之前
- **预期结果**：`stop("helper")` 先于 `create("helper", ...)` 被调用，确保 graceful shutdown 路径（含 pre_stop hook）完整执行
- **涉及模块**：agent_manager

### TC-002: Restart 保留 channels 配置

- **来源**：code-diff
- **优先级**：P0
- **前置条件**：agent 以自定义 channels `["#dev", "#ops"]` 创建
- **操作步骤**：
  1. 以 `channels=["#dev", "#ops"]` 创建 agent
  2. 执行 `mgr.restart("helper")`
  3. 捕获 `create` 调用时传入的 channels 参数
- **预期结果**：`create` 收到 `channels=["#dev", "#ops"]`，与原始配置一致
- **涉及模块**：agent_manager

### TC-003: Restart 保留 agent_type 配置

- **来源**：code-diff
- **优先级**：P0
- **前置条件**：agent 以 `agent_type="custom-template"` 创建
- **操作步骤**：
  1. 以 `agent_type="custom-template"` 创建 agent
  2. 执行 `mgr.restart("helper")`
  3. 捕获 `create` 调用时传入的 agent_type 参数
- **预期结果**：`create` 收到 `agent_type="custom-template"`
- **涉及模块**：agent_manager

### TC-004: Config 缺失时回退到默认值

- **来源**：code-diff
- **优先级**：P1
- **前置条件**：agent 记录中缺少 channels 和 type 字段（模拟旧版状态文件）
- **操作步骤**：
  1. 手动注入 agent 到 `_agents` dict，不包含 channels/type 字段
  2. 执行 `mgr.restart("helper")`
  3. 捕获 `create` 调用参数
- **预期结果**：channels 回退到 `default_channels`，agent_type 回退到 `default_type`
- **涉及模块**：agent_manager

### TC-005: Stop 失败时 create 不执行

- **来源**：code-diff
- **优先级**：P0
- **前置条件**：agent 存在但 stop 会抛异常（如状态为 offline）
- **操作步骤**：
  1. 创建 agent 后执行 `mgr.stop("helper")` 使其 offline
  2. 执行 `mgr.restart("helper")`
- **预期结果**：`stop` 阶段抛出 `ValueError("already offline")`，异常传播，`create` 不被调用
- **涉及模块**：agent_manager

### TC-006: Restart 未知 agent 抛出 ValueError

- **来源**：code-diff
- **优先级**：P1
- **前置条件**：无名为 "nonexistent" 的 agent
- **操作步骤**：
  1. 执行 `mgr.restart("nonexistent")`
- **预期结果**：抛出 `ValueError`，消息包含 "Unknown agent"
- **涉及模块**：agent_manager

### TC-007: E2E — CLI restart 完整流程

- **来源**：coverage-gap
- **优先级**：P0
- **前置条件**：ergo 运行中，agent 已创建并加入 IRC
- **操作步骤**：
  1. `zchat agent create agent0`，通过 IrcProbe 确认 nick 在线
  2. `zchat agent restart agent0`
  3. 通过 IrcProbe `wait_for_nick` 验证 nick 重新出现
- **预期结果**：agent nick 短暂消失后重新出现在 IRC
- **涉及模块**：app, agent_manager, zellij, irc

### TC-008: E2E — Restart 后 agent 可接收消息

- **来源**：coverage-gap
- **优先级**：P1
- **前置条件**：agent 已成功 restart 并 re-join IRC（依赖 TC-007）
- **操作步骤**：
  1. Restart agent（TC-007 流程）
  2. `zchat agent send agent0 "ping after restart"`
  3. 检查 CLI 无报错
- **预期结果**：send 成功执行，无 "not ready" 或 "not running" 错误
- **涉及模块**：agent_manager, zellij

### TC-009: scoped_name 不会在 restart 中双前缀

- **来源**：coverage-gap（关联已知 bug: scoped_name 双前缀）
- **优先级**：P1
- **前置条件**：username 为 "alice"，agent name 为 "agent0"
- **操作步骤**：
  1. 创建 `alice-agent0`
  2. 执行 restart，传入原始 name "agent0"
  3. 验证 stop 和 create 收到的 name 参数
- **预期结果**：内部 key 始终为 "alice-agent0"，不出现 "alice-alice-agent0"
- **涉及模块**：agent_manager, protocol

## 统计

| 指标 | 值 |
|------|-----|
| 总用例数 | 9 |
| P0 | 4 |
| P1 | 5 |
| P2 | 0 |
| 来源：code-diff | 6 |
| 来源：eval-doc | 0 |
| 来源：coverage-gap | 3 |
| 来源：bug-feedback | 0 |

## 测试分层建议

| 用例 | 建议层级 | 理由 |
|------|---------|------|
| TC-001 ~ TC-006, TC-009 | Unit | 可 mock zellij/IRC，验证纯逻辑 |
| TC-007, TC-008 | E2E | 需要真实 ergo + zellij 环境 |

## 风险标注

- **高风险**：restart 组合了 stop + create 两个核心路径——stop 阶段失败会导致 agent 留在原状态，create 阶段失败会导致 agent 丢失（已 stop 但未重建）
- **回归风险**：stop() 和 create() 各自有 E2E 覆盖（test_agent_stop, test_agent_joins_irc），restart 作为组合调用方，需确保不引入新的交互问题
- **已知 bug 关联**：scoped_name 双前缀 bug（coverage-matrix-002 已知 bug #6/#7）在 restart 路径中可能触发——TC-009 专门验证
- **缺少来源**：无 eval-doc 或 issue 直接关联 restart 重构；eval-doc-001 (Agent DM) 与本次改动无交集
