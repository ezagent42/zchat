# Dev-Loop Skills 交互式 E2E 测试报告

**日期**: 2026-04-10 07:06 UTC
**方法**: `claude -p` (pipe mode) 无头自动化执行
**总用例**: 7 | **通过**: 6 | **失败**: 0 | **错误**: 1 | **跳过**: 0

---

## 结果汇总

| Skill | 功能 | 名称 | 状态 | 耗时 | 断言 |
|-------|------|------|------|------|------|
| 6 | 1 | Skill 6 通过 skill 触发 query --summary | PASS | 34.1s | 3/3 |
| 1 | 1 | Skill 1 项目知识问答 (agent_manager) | PASS | 82.5s | 3/3 |
| 1 | 4 | Skill 1 查询 artifact 状态概览 | PASS | 48.2s | 2/2 |
| 1 | 6 | Skill 1 测试 Pipeline 信息查询 | PASS | 80.3s | 4/4 |
| 5 | 1 | Skill 5 模拟模式 (simulate agent DM) | ERROR | 300.1s | 0/4 |
| 5 | 3 | Skill 5 验证模式 (verify scoped_name bug) | PASS | 147.8s | 2/2 |
| 2 | 2 | Skill 2 从 coverage-gap 生成 test-plan | PASS | 168.1s | 4/4 |

---

## 详细结果

### Skill 6 功能 1: Skill 6 通过 skill 触发 query --summary

**状态**: passed | **耗时**: 34.1s

**提示词**: `使用 artifact-registry skill 查询当前 .artifacts/ 的全局概览。运行 query.sh --summary 并展示结果。`

**断言**:

| # | 描述 | 结果 | 证据 |
|---|------|------|------|
| 1 | 输出包含 coverage-matrix | PASS | ... 2 个 artifact \| \| **类型分布** \| `coverage-matrix` × 2 \| \| **状态分布** \| `draft` ×... |
| 2 | 输出包含 artifact 统计 | PASS | 匹配: 'artifact，都处于 `draft` 状态——说明项目刚完成 bootstrap 阶段（Skill 0' |
| 3 | registry.json 仍然有效 | PASS | exit=0 |

<details>
<summary>输出摘要 (598 chars)</summary>

```
这是当前 `.artifacts/` 的全局概览：

---

**Artifact Registry 总览**

| 指标 | 值 |
|------|----|
| **总数** | 2 个 artifact |
| **类型分布** | `coverage-matrix` × 2 |
| **状态分布** | `draft` × 2 |

---

`★ Insight ─────────────────────────────────────`
- 目前 registry 中只有 2 个 coverage-matrix artifact，都处于 `draft` 状态——说明项目刚完成 bootstrap 阶段（Skill 0），尚未进入 test-plan → test-code → test-run 的完整流水线。
- 这两个 coverage-matrix 对应之前的 commit `2e8ee02` 和 `cb1b2e0`，是 bootstrap 阶段自动注册的。
- 下一步通常是基于 coverage-matrix 生成 test-plan（Skill 2），然后 coverage-matrix 状态会流转到 `confirmed → executed`。

`─────────────────────────────────────────────────`

```

</details>

---

### Skill 1 功能 1: Skill 1 项目知识问答 (agent_manager)

**状态**: passed | **耗时**: 82.5s

**提示词**: `使用 project-discussion-zchat skill 回答：zchat 的 agent_manager 模块是如何管理 agent 生命周期的？create/stop/restart 的核心逻辑在哪里？请引用具体的 file:...`

**断言**:

| # | 描述 | 结果 | 证据 |
|---|------|------|------|
| 1 | 包含 file:line 引用 | PASS | 匹配: 'agent_manager.py:65' |
| 2 | 包含函数名引用 | PASS | 匹配: '.create' |
| 3 | 包含测试执行证据 | PASS | 匹配: 'passed' |

<details>
<summary>输出摘要 (4082 chars)</summary>

```
全部 **19/19 测试通过**，与基线一致。下面结合源码详细解析 agent 生命周期。

---

## Agent 生命周期管理解析

`agent_manager.py` 的核心是 `AgentManager` 类，围绕三个阶段管理 agent：**创建 → 运行 → 停止**，状态通过 JSON 文件持久化。

### 1. Create — 创建并启动 agent

入口：`AgentManager.create()` — `agent_manager.py:65-98`

```
create(name, workspace, channels, agent_type)
  │
  ├─ ① check_irc_connectivity()          ← :70  预检 IRC 连通性
  ├─ ② scoped(name)                      ← :72  加 username 前缀（如 "helper" → "alice-helper"）
  ├─ ③ 重复检测                           ← :73  已在运行

... (共 4082 字符，已截断) ...

─────────────────────────────────
Total                                    19/19 passed ✅  (1.96s)
```

关键测试覆盖了：
- `test_scope_agent_name` — 名称作用域化
- `test_create_workspace_persistent` — project_dir 模式下创建 workspace
- `test_cleanup_workspace_only_removes_ready_marker` — 清理只删 marker 不删目录
- `test_wait_for_ready_detects_marker` / `test_wait_for_ready_timeout` — 就绪检测正反案例
- `test_send_succeeds_when_ready` / `test_send_raises_when_not_ready` — send 的前置条件检查
- `test_agent_state_persistence` — JSON 持久化往返

```

</details>

---

### Skill 1 功能 4: Skill 1 查询 artifact 状态概览

**状态**: passed | **耗时**: 48.2s

**提示词**: `使用 project-discussion-zchat skill，查一下当前 .artifacts/ 中有哪些 artifact，各自什么状态？`

**断言**:

| # | 描述 | 结果 | 证据 |
|---|------|------|------|
| 1 | 包含 coverage-matrix 信息 | PASS | ...态 \| 说明 \| \|---\|---\|---\|---\| \| `coverage-matrix-001` \| coverage-matrix \| **dr... |
| 2 | 包含状态信息 | PASS | 匹配: 'draft' |

<details>
<summary>输出摘要 (1052 chars)</summary>

```
当前 `.artifacts/` 的状态概览：

### 注册的 Artifact（registry.json 中）

| ID | 类型 | 状态 | 说明 |
|---|---|---|---|
| `coverage-matrix-001` | coverage-matrix | **draft** | 初始覆盖矩阵，Skill 0 生成（4/9） |
| `coverage-matrix-002` | coverage-matrix | **draft** | 覆盖矩阵 v2（E2E 全部正常执行），Skill 0 生成（4/10） |

两个版本指向同一文件 `.artifacts/coverage/coverage-matrix.md`，002 是 001 的更新版。

### 目录结构与内容

| 目录 | 内容 | 状态 |
|---|---|---|
| `bootstrap/` | `bootstrap-report.md` + 8 个 `module-reports/*.json` | 有数据（Skill 0 产出） |
| `coverage/` | `cove

... (共 1052 字符，已截断) ...

| 等待首次代码变更记录 |
| `e2e-reports/` | 空 | 等待首次 E2E 报告 |
| `eval-docs/` | 空 | 等待首次 feature eval |
| `issues/` | 空 | 等待首次 issue |
| `test-diffs/` | 空 | 等待首次测试 diff |
| `test-plans/` | 空 | 等待首次测试计划 |

`★ Insight ─────────────────────────────────────`
项目刚完成 **Phase 0 bootstrap**（Skill 0），artifact 空间已初始化但大部分目录还是空的。目前只有覆盖矩阵和模块分析报告。这意味着 dev-loop pipeline 的后续阶段（feature eval → test plan → test code → e2e report）还未开始运转。当你开始修 bug 或加功能时，这些目录会逐步被填充，形成可追溯的变更链条。
`─────────────────────────────────────────────────`

```

</details>

---

### Skill 1 功能 6: Skill 1 测试 Pipeline 信息查询

**状态**: passed | **耗时**: 80.3s

**提示词**: `使用 project-discussion-zchat skill，这个项目的 E2E 测试 pipeline 是什么样的？用什么框架？fixture 有哪些？怎么采集证据？`

**断言**:

| # | 描述 | 结果 | 证据 |
|---|------|------|------|
| 1 | 包含 pytest 框架信息 | PASS | ...E 测试 Pipeline 全景  ### 框架  - **pytest 9.0.2** + **pytest-order 1.3.... |
| 2 | 包含 E2E 目录 | PASS | ...k.e2e` 标记，运行命令：`uv run pytest tests/e2e/ -v -m e2e` - 测试分布在两个文件：   - ... |
| 3 | 包含 fixture 信息 | PASS | 匹配: 'fixture' |
| 4 | 包含 marker 信息 | PASS | 匹配: '@pytest.mark.e2e` 标记，运行命令：`uv run pytest tests/e2e/ -v -m e2e' |

<details>
<summary>输出摘要 (3551 chars)</summary>

```
`★ Insight ─────────────────────────────────────`
这个 E2E pipeline 的设计有几个值得关注的点：
1. **Session-scoped fixtures** — 所有基础设施 fixture 都是 `scope="session"`，整个测试 session 只启动一次 ergo/zellij，测试之间共享状态。这意味着测试是**有序且有状态的**（Phase 1 创建的 agent 在 Phase 8 才被 stop）。
2. **Evidence 不依赖被测系统** — 证据采集走独立的 IRC 连接（IrcProbe），不依赖 zchat 自身的功能来验证 zchat，避免了"用自己测自己"的问题。
3. **双层验证** — IRC 层用 `IrcProbe.nick_exists()` / `wait_for_message()` 验证网络可见性；终端层用 `zellij.dump_screen()` 验证 UI 输出。
`─────────────────────────────────────────────

... (共 3551 字符，已截断) ...

"alice-agent0")
Phase 3: agent send → wait_for_message("Hello from agent0")
Phase 4: @mention → wait_for_message("alice-agent0")
Phase 5: 第二个 agent → wait_for_nick("alice-agent1")
Phase 6: agent 间通信 → wait_for_message("alice-agent1")
Phase 7: 用户间对话 → bob_probe/irc_probe 互相验证
Phase 8: agent stop → wait_for_nick_gone("alice-agent1")
Phase 9: shutdown → wait_for_nick_gone("alice-agent0")
```

### 已知限制

- Phase 3/4/5/6 涉及 MCP → Claude Code 实际响应，在 CI 环境下有 **30s 超时问题**
- Phase 1/2/7/8/9 是纯基础设施操作，稳定通过

```

</details>

---

### Skill 5 功能 1: Skill 5 模拟模式 (simulate agent DM)

**状态**: error | **耗时**: 300.1s

**提示词**: `使用 feature-eval skill 的模拟模式。模拟一下：如果 zchat 支持 agent 间通过 IRC DM 直接私聊（不经过频道），预期各场景的效果如何？请生成 eval-doc 并保存到 .artifacts/eval-d...`

**错误**: 超时 (300s)

**断言**:

| # | 描述 | 结果 | 证据 |
|---|------|------|------|
| 1 | 输出包含 testcase | — |  |
| 2 | 包含正常路径 | — |  |
| 3 | 包含边界情况 | — |  |
| 4 | eval-docs 目录有新文件 | — |  |

<details>
<summary>输出摘要 (20 chars)</summary>

```
[TIMEOUT after 300s]
```

</details>

---

### Skill 5 功能 3: Skill 5 验证模式 (verify scoped_name bug)

**状态**: passed | **耗时**: 147.8s

**提示词**: `使用 feature-eval skill 的验证模式。发现一个 bug：scoped_name('alice-helper', 'alice') 返回了 'alice-alice-helper' 而不是 'alice-helper'。请收...`

**断言**:

| # | 描述 | 结果 | 证据 |
|---|------|------|------|
| 1 | 输出包含 bug 分析 | PASS | 匹配: 'Bug' |
| 2 | 包含 eval-doc 或 verify | PASS | 匹配: 'eval-doc' |

<details>
<summary>输出摘要 (583 chars)</summary>

```
完成。eval-doc 已生成并注册：

**Artifact**: `eval-doc-002` (draft)
**路径**: `.artifacts/eval-docs/eval-scoped-name-002.md`

`★ Insight ─────────────────────────────────────`
**Bug 根因**：`naming.py:11` 的 `return f"{username}{AGENT_SEPARATOR}{name}"` 无条件拼接，缺少 `AGENT_SEPARATOR in name` 的前置检查。

**测试与实现的矛盾**：测试用例定义了三种场景的预期行为（裸名加前缀、自身前缀幂等、他人前缀保留），但实现只覆盖了第一种。docstring 把错误行为当作"预期"记录，说明这可能是 TDD 中"先写测试、实现未跟上"的典型案例。

**影响链**：`scoped_name` → `AgentManager.scoped()` → 6 个 CLI 命令。用户如果传入全名 `alice-helper` 给任何 agent 命令，都会生成无效 nick `alice-alice-helper`。
`─────────────────────────────────────────────────`

```

</details>

---

### Skill 2 功能 2: Skill 2 从 coverage-gap 生成 test-plan

**状态**: passed | **耗时**: 168.1s

**提示词**: `使用 test-plan-generator skill。分析 coverage-matrix 中未覆盖的用户流程，为 "Agent 重启" 流程生成测试计划。保存到 .artifacts/test-plans/ 并注册到 registry...`

**断言**:

| # | 描述 | 结果 | 证据 |
|---|------|------|------|
| 1 | 输出包含测试用例 | PASS | 匹配: 'TC-010' |
| 2 | 包含 restart 相关内容 | PASS | 匹配: 'restart' |
| 3 | 包含优先级 | PASS | 匹配: 'P0' |
| 4 | test-plans 目录有新文件 | PASS | exit=0 |

<details>
<summary>输出摘要 (850 chars)</summary>

```
`★ Insight ─────────────────────────────────────`
**测试计划设计决策：**
1. **10 个用例全部来源于 coverage-gap** — 因为没有 code-diff 触发，完全是从覆盖矩阵的空白出发
2. **Unit 优先（8/10）**：restart 的核心逻辑（配置保留、状态转换、异常处理）都可以通过 mock zellij 来验证，无需启动真实 ergo
3. **TC-010 关联已知 protocol bug** — scoped_name 双前缀问题在 restart 路径上是隐藏的组合风险
`─────────────────────────────────────────────────`

测试计划已生成并注册：

- **文件**: `.artifacts/test-plans/plan-agent-restart-001.md`
- **ID**: `test-plan-001`
- **状态**: draft
- **关联**: coverage-matrix-002

**计划摘要：**

| 指标 | 值 |
|------|-----|
| 总用例数 | 10 |
| P0 (必须) | 4 — 正常重启、配置保留(channels/type)、未知 agent 异常 |
| P1 (重要) | 6 — 状态转换、workspace 清理、E2E restart+send、offline 重启、双前缀 |
| 建议 Unit | 8 个 (TC-001~006, 009, 010) |
| 建议 E2E | 2 个 (TC-007, 008) |

**高风险区域：** restart 是 stop + create 串联操作，任一环节失败会导致 agent 处于不一致状态。TC-010 还覆盖了已知的 scoped_name 双前缀 bug 在 restart 路径上的表现。

```

</details>

---

## 修复建议汇总

### Skill 5 功能 1: Skill 5 模拟模式 (simulate agent DM)
- **问题**: 超时 (300s)
- **建议**: 增加超时时间或检查 skill 执行逻辑
