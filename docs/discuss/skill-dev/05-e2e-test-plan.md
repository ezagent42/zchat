# Dev-Loop Skills E2E 测试计划

## 概述

### 什么是 dev-loop-skills

dev-loop-skills 是一个由 7 个 Claude Code skill 组成的开发闭环 pipeline，覆盖从项目接入到持续迭代的完整生命周期：

| 编号 | 名称 | 职责 | 阶段 |
|------|------|------|------|
| Skill 0 | project-builder | 将代码仓库转化为可运转的开发闭环 | Phase 0 (bootstrap) |
| Skill 1 | project-discussion-zchat | 项目知识问答，有实证支撑 | Phase 2 及全流程 |
| Skill 2 | test-plan-generator | 从 code-diff/coverage-gap/eval-doc 生成测试计划 | Phase 3 |
| Skill 3 | test-code-writer | 将 confirmed test-plan 转化为 pytest E2E 代码 | Phase 4 |
| Skill 4 | test-runner | 执行完整 E2E 套件，生成结构化报告 | Phase 5 |
| Skill 5 | feature-eval | 预期 vs 实际对比（模拟/验证双模式） | Phase 1, Phase 7 |
| Skill 6 | artifact-registry | 统一 artifact 空间管理 | 全流程 |

Skill 之间通过 `.artifacts/` 中的结构化 artifact（YAML frontmatter + markdown）解耦。每个 skill 产出固定格式的 artifact，下一个 skill 消费。Skill 6 提供索引层，管理 artifact 的注册、查询、状态追踪和交叉引用。

### 测试目标

验证每个 skill 的**每个功能**都能正确执行，包括：
1. 每个 skill 独立触发后能按 SKILL.md 描述的步骤完成工作
2. skill 之间通过 artifact 正确传递数据（生产者写入 → 消费者读取）
3. 一个完整的 Phase 1 → Phase 5 循环能走通
4. artifact-registry 全程正确追踪 artifact 状态和关联

### 项目上下文

zchat 是 dev-loop-skills 的第一个接入项目。项目已完成 Skill 0 bootstrap，Skill 1 已生成并通过自验证。所有 7 个 skill 已开发完成。

---

## Skill 包位置

### 包根目录

```
/home/yaosh/.claude/skills/dev-loop-skills/skills/
```

### 每个 skill 的路径

| Skill | 路径 |
|-------|------|
| Skill 0 | `/home/yaosh/.claude/skills/dev-loop-skills/skills/skill-0-project-builder/` |
| Skill 1 | `/home/yaosh/.claude/skills/skill-1-project-discussion-zchat-local/` (项目特定，不在包内) |
| Skill 2 | `/home/yaosh/.claude/skills/dev-loop-skills/skills/skill-2-test-plan-generator/` |
| Skill 3 | `/home/yaosh/.claude/skills/dev-loop-skills/skills/skill-3-test-code-writer/` |
| Skill 4 | `/home/yaosh/.claude/skills/dev-loop-skills/skills/skill-4-test-runner/` |
| Skill 5 | `/home/yaosh/.claude/skills/dev-loop-skills/skills/skill-5-feature-eval/` |
| Skill 6 | `/home/yaosh/.claude/skills/dev-loop-skills/skills/skill-6-artifact-registry/` |

### Symlink 位置

所有 skill 在 `~/.claude/skills/` 有 symlink，可被 Claude Code skill 系统直接加载：

| Skill | Symlink |
|-------|---------|
| Skill 0 | `~/.claude/skills/project-builder` → `dev-loop-skills/skills/skill-0-project-builder` |
| Skill 1 | `~/.claude/skills/project-discussion-zchat` → `skill-1-project-discussion-zchat-local` |
| Skill 2 | `~/.claude/skills/test-plan-generator` → `dev-loop-skills/skills/skill-2-test-plan-generator` |
| Skill 3 | `~/.claude/skills/test-code-writer` → `dev-loop-skills/skills/skill-3-test-code-writer` |
| Skill 4 | `~/.claude/skills/test-runner` → `dev-loop-skills/skills/skill-4-test-runner` |
| Skill 5 | `~/.claude/skills/feature-eval` → `dev-loop-skills/skills/skill-5-feature-eval` |
| Skill 6 | `~/.claude/skills/artifact-registry` → `dev-loop-skills/skills/skill-6-artifact-registry` |
| 路由 | `~/.claude/skills/using-dev-loop` → `dev-loop-skills/skills/using-dev-loop` |

### .artifacts/ 位置

```
/home/yaosh/projects/zchat/.artifacts/
```

### 已有的 bootstrap 产出

Skill 0 已在 2026-04-10 完成 bootstrap，`.artifacts/` 中已有：

| 产出 | 路径 | 说明 |
|------|------|------|
| registry.json | `.artifacts/registry.json` | artifact 索引（含 2 个 coverage-matrix 条目） |
| coverage-matrix | `.artifacts/coverage/coverage-matrix.md` | 覆盖矩阵 v2（15 模块，9/24 E2E 流程覆盖） |
| bootstrap-report | `.artifacts/bootstrap/bootstrap-report.md` | bootstrap 执行报告（7 个 bug 记录） |
| module-reports | `.artifacts/bootstrap/module-reports/*.json` | 15 个模块的结构化分析（agent_manager, app, auth, config_cmd, defaults, doctor, irc_manager, layout, migrate, paths, project, runner, template_loader, update, zellij） |

空目录（待后续 pipeline 填充）：`code-diffs/`, `e2e-reports/`, `eval-docs/`, `issues/`, `test-diffs/`, `test-plans/`

---

## 前置条件

### 环境要求

| 依赖 | 要求 | 验证命令 |
|------|------|---------|
| ergo IRC server | 已安装，`zchat irc daemon start` 可启动 | `which ergo` |
| zellij | >= 0.44 | `zellij --version` |
| uv | >= 0.7 | `uv --version` |
| WeeChat | 已安装 | `which weechat` |
| Python | >= 3.14 | `python --version` |
| pytest | >= 9.0.2 | `uv run pytest --version` |
| gh (GitHub CLI) | 已安装并登录（Skill 5 创建 issue 需要） | `gh auth status` |
| git | 已安装 | `git --version` |

### 已完成的 bootstrap

以下条件在执行本测试计划前必须为真：

1. Skill 0 已执行过 bootstrap（`.artifacts/` 目录已初始化）
2. Skill 1 (project-discussion-zchat) 已生成并通过自验证
3. Skill 6 (artifact-registry) 的所有脚本可执行：
   ```bash
   bash /home/yaosh/.claude/skills/artifact-registry/scripts/self-test.sh --dry-run
   ```
4. registry.json 存在且包含 coverage-matrix 条目：
   ```bash
   bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh \
     --project-root /home/yaosh/projects/zchat --summary
   ```

### 项目根目录

所有脚本中 `--project-root` 参数统一使用：

```
/home/yaosh/projects/zchat
```

---

## 测试场景

---

### Skill 1: project-discussion-zchat

**触发方式**：在 Claude Code 中使用 Skill tool 加载 `project-discussion-zchat`，或在对话中提问 zchat 项目相关问题。

#### 功能 1：项目知识问答（Step 1-5）

**描述**：被问到项目相关问题时，Skill 1 应定位模块 → 读取代码 → 运行测试 → 用实证回答。

**输入**：提问 "zchat 的 agent_manager 模块是如何管理 agent 生命周期的？create/stop/restart 的核心逻辑在哪里？"

**操作步骤**：
1. 加载 Skill 1（`/project-discussion-zchat`）
2. 提出上述问题

**预期输出**：
- 回答中包含 `zchat/cli/agent_manager.py` 的具体 file:line 引用（如 `agent_manager.py:42`）
- 回答中引用至少一个关键函数的签名或逻辑描述
- 回答中包含运行 `uv run pytest tests/unit/test_agent_manager.py tests/unit/test_agent_focus_hide.py -v` 的**实际测试输出**（19/19 passed 或当前实际结果）
- 不包含 `[unverified]` 标注的猜测

**验证方式**：
- 检查回答是否有 file:line 引用（至少 1 处）
- 检查回答是否附带了 pytest 运行输出
- 手动验证引用的 file:line 是否指向实际存在的代码

#### 功能 2：自动刷新检测（Step 0）

**描述**：每次回答前，Skill 1 检查 `.artifacts/` 中是否有比生成时间更新的 code-diff 或 e2e-report。

**输入**：在 `.artifacts/code-diffs/` 中手动创建一个测试用 code-diff artifact（内容指向 agent_manager 模块），然后提问 agent_manager 相关问题。

**操作步骤**：
1. 创建测试 code-diff 文件：
   ```bash
   cat > /home/yaosh/projects/zchat/.artifacts/code-diffs/test-diff.md << 'EOF'
   ---
   type: code-diff
   id: code-diff-test-001
   status: draft
   producer: manual-test
   created_at: "2026-04-10"
   ---
   # Test Code Diff
   ## Changes
   - Modified: zchat/cli/agent_manager.py (test change)
   EOF
   ```
2. 通过 Skill 6 注册该 artifact：
   ```bash
   bash /home/yaosh/.claude/skills/artifact-registry/scripts/register.sh \
     --project-root /home/yaosh/projects/zchat \
     --type code-diff --name "测试用 code-diff" \
     --producer manual-test \
     --path .artifacts/code-diffs/test-diff.md \
     --status draft
   ```
3. 加载 Skill 1 并提问 "agent_manager 模块最近有什么改动？"

**预期输出**：
- Skill 1 在 Step 0 检测到新的 code-diff artifact
- 回答中提到检测到了新的 code-diff
- 重新读取 agent_manager.py 并运行测试

**验证方式**：
- 检查回答中是否提到 code-diff-test-001
- 检查是否有重新读取代码和运行测试的迹象

**清理**：测试后删除 `.artifacts/code-diffs/test-diff.md` 并从 registry 中移除。

#### 功能 3：分流判断（Step 6）

**描述**：当讨论涉及 `.artifacts/` 中的 eval-doc 或 issue 时，Skill 1 在回答后继续进行分流判断。

**输入**：先在 `.artifacts/eval-docs/` 中创建一个模拟的 verify 模式 eval-doc（描述一个疑似 bug），然后带着这个 eval-doc 与 Skill 1 讨论。

**操作步骤**：
1. 创建测试 eval-doc：
   ```bash
   cat > /home/yaosh/projects/zchat/.artifacts/eval-docs/eval-test-triage-001.md << 'EOF'
   ---
   type: eval-doc
   id: eval-doc-test-001
   status: draft
   mode: verify
   feature: "scoped_name 双前缀 bug"
   producer: skill-5
   created_at: "2026-04-10"
   ---
   # Eval: scoped_name 双前缀 bug
   ## Testcase
   | # | 场景 | 预期效果 | 实际效果 | 差异 | 优先级 |
   |---|------|---------|---------|------|--------|
   | 1 | scoped_name("alice-helper", "alice") | 返回 "alice-helper" | 返回 "alice-alice-helper" | 双前缀 | P0 |
   EOF
   ```
2. 注册到 registry
3. 加载 Skill 1，说 "我们来讨论一下这个 eval-doc-test-001，scoped_name 的双前缀问题是不是 bug？"

**预期输出**：
- Skill 1 读取代码（`zchat-protocol/` 中的 naming 模块）
- Skill 1 运行 protocol 测试（`cd zchat-protocol && uv run pytest tests/ -v`），确认 2/9 failed
- Skill 1 提出分析结论（应判断为 bug，因为测试已失败）
- Skill 1 询问人是否确认结论
- 如果人确认"是 bug"，Skill 1 告知 eval-doc 将进入 Phase 3

**验证方式**：
- 检查回答中是否引用了 protocol 模块的 file:line
- 检查回答中是否有 pytest 运行输出（7/9 或当前结果）
- 检查是否明确提出了"这是 bug"的结论
- 检查是否询问人确认

#### 功能 4：Artifact 交互

**描述**：Skill 1 能查询和操作 `.artifacts/` 中的 artifact。

**输入**：要求 Skill 1 查询所有 artifact 的状态概览。

**操作步骤**：
1. 加载 Skill 1
2. 说 "查一下当前 .artifacts/ 中有哪些 artifact，各自什么状态？"

**预期输出**：
- Skill 1 调用 Skill 6 的 `query.sh --summary`
- 返回 artifact 统计表（至少包含 2 个 coverage-matrix 条目）

**验证方式**：
- 检查输出中是否有 registry 查询结果
- 比对结果与 `registry.json` 的实际内容

#### 功能 5：自我演进（驳回结论归档）

**描述**：当 Phase 8 结论为"不是 bug"时，Skill 1 更新 eval-doc 状态为 archived 并追加 rejection_reason。

**输入**：接续功能 3 的分流讨论，但这次人确认结论为"不是 bug"。

**操作步骤**：
1. 创建一个新的测试 eval-doc（描述一个非 bug 场景，如"希望 zchat doctor 检查 Docker"）
2. 注册到 registry
3. 加载 Skill 1，讨论这个 eval-doc
4. 人确认"这不是 bug，是 feature request"

**预期输出**：
- Skill 1 调用 `update-status.sh --id <id> --status archived`
- Skill 1 在 eval-doc 文件中追加 `rejection_reason` 和 `rejected_at`
- Git commit 追踪变更

**验证方式**：
- 检查 registry.json 中该 eval-doc 状态是否变为 archived
- 检查 eval-doc 文件中是否有 rejection_reason 字段
- 检查 git log 是否有对应 commit

#### 功能 6：测试 Pipeline 信息查询

**描述**：Skill 1 提供项目测试 pipeline 的详细信息，供 Skill 3 (test-code-writer) 查询。

**输入**：提问 "这个项目的 E2E 测试 pipeline 是什么样的？用什么框架？fixture 有哪些？怎么采集证据？"

**操作步骤**：
1. 加载 Skill 1
2. 提出上述问题

**预期输出**：
- 回答包含：测试框架（pytest 9.0.2 + pytest-order + pytest-asyncio）
- 回答包含：E2E 目录（tests/e2e/）
- 回答包含：fixture 列表（e2e_port, zellij_session, e2e_context, ergo_server, zchat_cli, zellij_send, irc_probe, bob_probe, weechat_tab）
- 回答包含：证据采集工具（IrcProbe, zellij helpers）
- 回答包含：测试命名规范（`test_{action}_{target}`）
- 回答包含：marker（`@pytest.mark.e2e`）

**验证方式**：
- 检查回答是否覆盖上述全部 6 项信息
- 检查信息是否与 Skill 1 SKILL.md 的 "测试 Pipeline 信息" 一节一致

---

### Skill 2: test-plan-generator

**触发方式**：在 Claude Code 中说 "生成测试计划"、"test plan"、"Phase 3"，或当 `.artifacts/` 中出现新的 code-diff artifact。

#### 功能 1：从 code-diff 生成 test-plan

**描述**：读取 code-diff artifact，分析改动影响范围，对比 coverage-matrix，输出结构化测试计划。

**输入**：在 `.artifacts/code-diffs/` 中准备一个 code-diff（描述对 agent_manager 模块的修改）。

**操作步骤**：
1. 创建 code-diff artifact：
   ```bash
   cat > /home/yaosh/projects/zchat/.artifacts/code-diffs/diff-agent-restart-001.md << 'EOF'
   ---
   type: code-diff
   id: code-diff-001
   status: draft
   producer: phase-2
   created_at: "2026-04-10"
   ---
   # Code Diff: Agent restart 逻辑重构
   ## 变更文件
   - M zchat/cli/agent_manager.py (restart_agent 函数重构)
   - A tests/unit/test_agent_restart.py (新增单元测试)
   ## 影响模块
   - agent_manager
   ## 改动类型
   - 修改：restart_agent() 现在先 graceful stop 再 create，而不是 kill + create
   EOF
   ```
2. 注册到 registry：
   ```bash
   bash /home/yaosh/.claude/skills/artifact-registry/scripts/register.sh \
     --project-root /home/yaosh/projects/zchat \
     --type code-diff --name "Agent restart 重构" \
     --producer phase-2 \
     --path .artifacts/code-diffs/diff-agent-restart-001.md \
     --status draft
   ```
3. 触发 Skill 2：说 "根据 code-diff-001 生成测试计划"

**预期输出**：
- Skill 2 读取 code-diff-001 内容
- Skill 2 读取 coverage-matrix（发现 "Agent 重启" 流程标记为 ❌ not covered）
- 输出测试计划包含：
  - YAML frontmatter（type: test-plan, status: draft, producer: skill-2）
  - 测试用例列表，每个用例有唯一 TC-ID（如 TC-001）
  - 至少一个 P0 用例（验证 restart 功能正确）
  - 至少一个 P1 用例（回归测试，确保 stop/create 不受影响）
  - 每个用例标注来源（code-diff）
  - 统计表（总用例数、优先级分布）

**验证方式**：
- 检查 `.artifacts/test-plans/` 中是否生成了新的 plan 文件
- 打开文件验证 YAML frontmatter 格式正确
- 验证每个用例有 TC-ID、来源、优先级、操作步骤、预期结果
- 验证 registry.json 中是否新增了 test-plan 条目

#### 功能 2：从 coverage-gap 生成 test-plan

**描述**：直接从 coverage-matrix 的未覆盖流程生成补充覆盖的测试计划。

**输入**：要求 Skill 2 针对 coverage-matrix 中标记为 ❌ 的用户流程生成测试计划。

**操作步骤**：
1. 说 "分析 coverage-matrix 中未覆盖的用户流程，为 '创建项目' 和 'Agent 重启' 两个流程生成测试计划"

**预期输出**：
- Skill 2 读取 coverage-matrix，识别"创建项目"和"Agent 重启"为 ❌
- 生成的 test-plan 中：
  - 每个用例标注来源为 `coverage-gap`
  - "创建项目" 用例的前置条件包含 `zchat project create local`
  - "Agent 重启" 用例的操作步骤包含 `zchat agent restart`
  - 统计表中来源分布显示 coverage-gap 为主

**验证方式**：
- 验证 plan 文件中每个用例的 source 字段包含 `coverage-gap`
- 验证用例覆盖了请求的两个用户流程

#### 功能 3：从 eval-doc 生成 test-plan

**描述**：读取 eval-doc 中的 testcase 列表，转换为可执行的测试用例。

**输入**：在 `.artifacts/eval-docs/` 中准备一个 confirmed 状态的 eval-doc。

**操作步骤**：
1. 创建 eval-doc（模拟模式产出）：
   ```bash
   cat > /home/yaosh/projects/zchat/.artifacts/eval-docs/eval-agent-dm-001.md << 'EOF'
   ---
   type: eval-doc
   id: eval-doc-001
   status: confirmed
   mode: simulate
   feature: "Agent 间私聊 (DM)"
   producer: skill-5
   created_at: "2026-04-10"
   ---
   # Eval: Agent 间私聊
   ## Testcase
   | # | 场景 | 前置条件 | 操作步骤 | 预期效果 | 模拟效果 | 差异 | 优先级 |
   |---|------|---------|---------|---------|---------|------|--------|
   | 1 | Agent0 私聊 Agent1 | 两个 agent 在线 | @alice-agent1 hello | agent1 收到消息 | channel-server 处理 PRIVMSG | 无 | P0 |
   | 2 | Agent 回复私聊 | agent1 收到消息 | agent1 MCP reply | alice 在 WeeChat 看到回复 | MCP reply 通过 PRIVMSG 发送 | 无 | P0 |
   | 3 | 离线 agent 私聊 | agent1 不在线 | @alice-agent1 hello | 提示 agent 离线 | IRC WHOIS 返回空 | 需要错误处理 | P1 |
   EOF
   ```
2. 注册并设为 confirmed 状态
3. 触发 Skill 2：说 "从 eval-doc-001 生成测试计划"

**预期输出**：
- eval-doc 中的 3 个 testcase 全部转换为 test-plan 中的用例
- 用例的来源标注为 `eval-doc`
- 优先级保持与 eval-doc 一致（2 个 P0, 1 个 P1）

**验证方式**：
- 验证 plan 中有 3 个用例且 TC-ID 唯一
- 验证来源全部为 eval-doc
- 验证优先级与 eval-doc 原始数据一致

#### 功能 4：人 review + confirm 流程

**描述**：test-plan 以 draft 状态产出，需要人 review 后确认。

**操作步骤**：
1. 接续功能 1 产出的 test-plan（draft 状态）
2. 审查计划，要求修改：删除一个低优先级用例，增加一个边界场景
3. 说 "确认这个测试计划"

**预期输出**：
- Skill 2 根据人的反馈修改 plan 内容
- Skill 2 调用 `update-status.sh` 将 test-plan 状态从 draft 更新为 confirmed
- 输出确认结果

**验证方式**：
- 检查 registry.json 中该 test-plan 状态是否为 `confirmed`
- 检查 plan 文件中是否反映了人的修改

#### 功能 5：注册到 .artifacts/

**描述**：test-plan 生成后自动注册到 artifact-registry。

**预期**：在功能 1-3 的每次执行中，test-plan 文件都应：
1. 保存在 `.artifacts/test-plans/` 目录
2. 在 registry.json 中有对应条目
3. 条目包含正确的 type、producer（skill-2）、status（draft）、path
4. 如果有关联的输入 artifact（code-diff、eval-doc），related_ids 字段包含它们的 ID

**验证方式**：
- 每次功能测试后检查 registry.json 变化
- 验证 plan 文件路径与 registry 中记录一致

---

### Skill 3: test-code-writer

**触发方式**：在 Claude Code 中说 "write tests from plan"、"implement test-plan"、"Phase 4"。

#### 功能 1：读取 confirmed test-plan

**描述**：从 `.artifacts/test-plans/` 中找到 confirmed 状态的 test-plan 并完整读取。

**输入**：`.artifacts/test-plans/` 中已有一个 confirmed 的 test-plan（由 Skill 2 产出）。

**操作步骤**：
1. 确保至少一个 test-plan 为 confirmed 状态
2. 触发 Skill 3：说 "根据最新的 confirmed test-plan 编写 E2E 测试"

**预期输出**：
- Skill 3 通过 Skill 6 查询 `--type test-plan --status confirmed`
- 正确读取 plan 文件内容
- 列出将要实现的 TC-ID 列表

**验证方式**：
- 检查 Skill 3 是否正确识别了 confirmed plan
- 检查列出的 TC-ID 与 plan 文件中的一致

#### 功能 2：查询 Skill 1 获取 pipeline 信息

**描述**：Skill 3 加载 Skill 1 获取项目的测试 pipeline 格式信息。

**预期输出**：
- Skill 3 读取 Skill 1 的 "测试 Pipeline 信息" 部分
- 确认框架（pytest）、E2E 目录（tests/e2e/）、fixture 列表、命名规范
- 实际读取 `tests/e2e/conftest.py` 了解 fixture 实现

**验证方式**：
- 检查 Skill 3 是否引用了正确的 E2E 目录
- 检查 Skill 3 是否列出了已有 fixture

#### 功能 3：生成 E2E 测试代码

**描述**：根据 plan 中的用例，生成符合项目规范的 pytest E2E 测试代码。

**预期输出**：
- 生成的测试文件在 `tests/e2e/` 目录下
- 每个测试函数有 `@pytest.mark.e2e` 标记
- 每个测试函数有 `@pytest.mark.order(N)` 排序标记（N 不与已有测试冲突）
- 每个测试函数有 docstring
- 函数命名遵循 `test_{action}_{target}` 规范
- 使用已有 fixture（e2e_context, ergo_server, zchat_cli, irc_probe 等）
- 断言消息具体且可操作
- 无 hardcoded 端口、路径或凭据

**验证方式**：
- 打开生成的文件，检查 marker、docstring、命名、fixture 使用
- 运行 `python -c "import ast; ast.parse(open('test_file.py').read())"` 验证语法
- 检查 import 是否正确

#### 功能 4：追加 vs 新建文件判断

**描述**：根据 `references/append-rules.md` 的规则，决定追加到已有文件还是新建文件。

**预期输出**：
- 如果 plan 中的用例域与已有 test 文件匹配且文件 < 300 行，追加到已有文件
- 如果域是全新的或已有文件太大，新建 `test_{domain}.py`
- 在 Skill 3 的输出中明确说明了追加/新建的决策和理由

**验证方式**：
- 检查 Skill 3 的日志/输出中是否有追加/新建的决策说明
- 验证决策是否符合规则

#### 功能 5：生成 test-diff artifact

**描述**：测试代码编写完成后，生成 test-diff artifact 记录所有变更。

**预期输出**：
- `.artifacts/test-diffs/` 中生成了 test-diff 文件
- 文件有 YAML frontmatter（type: test-diff, status: draft, producer: skill-3）
- 包含新增测试函数表（File / Function / Order / Domain / Validates）
- 包含新增 fixture 表（如有）
- 包含修改文件列表
- 包含验证记录（语法检查、import 检查、fixture 图、命名规范、排序冲突）
- 注册到 registry
- 源 test-plan 的状态更新为 `executed`

**验证方式**：
- 检查 `.artifacts/test-diffs/` 中的文件
- 检查 registry.json 中新增了 test-diff 条目
- 检查源 test-plan 状态是否变为 executed

---

### Skill 4: test-runner

**触发方式**：在 Claude Code 中说 "run e2e"、"run tests"、"regression check"、"Phase 5"。

#### 功能 1：env-check 预检

**描述**：执行前验证所有 E2E 依赖可用。

**操作步骤**：
1. 触发 Skill 4：说 "执行 E2E 测试"
2. 观察 Skill 4 是否首先运行 env-check

**预期输出**：
- Skill 4 运行 `scripts/env-check.sh --project-root /home/yaosh/projects/zchat`
- 输出结构化 JSON：检查 pytest、uv、ergo、zellij、E2E 目录
- 如果任何 hard dependency 缺失，停止并报告
- 如果环境就绪，输出 `"overall": "ready"` 或 `"ready_with_warnings"`

**验证方式**：
- 检查 env-check 输出中是否包含所有关键依赖的检查结果
- 如果环境确实就绪，验证 Skill 4 继续执行后续步骤

#### 功能 2：执行完整 E2E 套件

**描述**：运行项目的完整 E2E 测试套件（不只是新增用例）。

**操作步骤**：
1. 确保 ergo 和 zellij 运行中
2. 触发 Skill 4 执行

**预期输出**：
- Skill 4 运行 `uv run pytest tests/e2e/ -v --tb=long -q`（或通过 `scripts/run-e2e.sh`）
- 捕获完整的 stdout + stderr + exit code
- 不遗漏任何测试文件

**验证方式**：
- 检查输出中是否包含所有已有 E2E 测试的执行结果
- 比对测试数量与实际 `tests/e2e/` 目录中的测试数量

#### 功能 3：新增 vs 回归分类

**描述**：根据 test-diff artifact 区分新增 case 和回归 case。

**输入**：`.artifacts/test-diffs/` 中有 Skill 3 产出的 test-diff。

**预期输出**：
- test-diff 中列出的测试函数标记为 "new case"
- 其余所有测试标记为 "regression case"
- 如果没有 test-diff，所有测试标记为 "regression"

**验证方式**：
- 检查 e2e-report 中的分类是否正确
- 验证 new case 列表与 test-diff 中的函数名一致

#### 功能 4：证据采集

**描述**：在关键验证点采集证据（终端 capture、IRC probe 结果等）。

**预期输出**：
- 每个测试的证据引用记录在 report 中
- 失败测试有完整 traceback
- 失败测试有自动收集的上下文（日志片段、进程状态、环境信息）

**验证方式**：
- 检查 report 中 evidence 字段是否非空
- 检查失败测试是否有 failure_detail

#### 功能 5：生成 e2e-report

**描述**：生成结构化 E2E 测试报告。

**预期输出**：
- 报告保存在 `.artifacts/e2e-reports/report-{name}-{seq}/report.md`
- 包含 YAML frontmatter（type: e2e-report）
- 包含结果汇总表（new-case vs regression 的 pass/fail 统计）
- 回归失败突出标注（如有）
- 每个测试的详细结果（步骤、预期、实际、证据引用）
- 注册到 registry

**验证方式**：
- 打开 report 文件验证结构完整性
- 检查 registry.json 中是否新增了 e2e-report 条目
- 验证 pass/fail 数量与实际 pytest 输出一致

#### 功能 6：更新 coverage-matrix

**描述**：根据测试结果更新 `.artifacts/coverage/coverage-matrix.md`。

**预期输出**：
- 新通过的测试对应的用户流程在 coverage-matrix 中标记为 "E2E covered"
- 回归失败的流程标记（如有）
- 更新 pass/fail 计数
- 时间戳更新

**验证方式**：
- 比对 coverage-matrix 更新前后的差异
- 验证新覆盖的流程是否正确标记

---

### Skill 5: feature-eval

**触发方式**：在 Claude Code 中说 "simulate"、"模拟"、"verify"、"发现 bug"、"eval"。

#### 功能 1：模拟模式（simulate）—— feature idea → eval-doc

**描述**：产品/开发者描述 feature 想法，AI 模拟各 testcase 的预期效果。

**输入**：描述一个 feature idea："如果 zchat 支持 agent 间通过 IRC DM 直接私聊（不经过频道），效果会怎样？"

**操作步骤**：
1. 触发 Skill 5 模拟模式：说 "模拟一下：agent 间通过 IRC DM 直接私聊"
2. 等待 Skill 5 生成 testcase 列表和模拟分析

**预期输出**：
- Skill 5 提取 feature 描述：agent 间 IRC DM 直接私聊
- 生成 testcase 列表覆盖：
  - 正常路径（至少 1 个）：agent0 向 agent1 发 DM
  - 边界情况（至少 2 个）：离线 agent、不存在的 nick、自己发给自己
  - 错误处理
- 每个 testcase 有：前置条件、操作步骤、预期效果、模拟效果、差异描述、优先级
- AI 模拟分析基于实际代码（读取 channel-server 源码）
- 标注风险点（如 MCP 超时问题）
- 使用 `templates/eval-doc.md` 模板格式
- 展示给用户确认

**验证方式**：
- 检查 testcase 是否覆盖正常路径 + 至少 2 个边界情况
- 检查模拟效果列是否基于代码分析（引用了 channel-server 代码）
- 检查 eval-doc 格式是否符合模板

#### 功能 2：用户确认后注册

**描述**：用户 review testcase 后，eval-doc 从 draft → confirmed 并注册到 registry。

**操作步骤**：
1. 接续功能 1，审查 testcase 列表
2. 要求调整：增加一个 testcase、修改一个优先级
3. 说 "确认这个 eval-doc"

**预期输出**：
- Skill 5 修改 eval-doc 内容
- eval-doc 写入 `.artifacts/eval-docs/`
- 状态更新为 confirmed
- 注册到 registry

**验证方式**：
- 检查 `.artifacts/eval-docs/` 中的文件
- 检查 registry.json 中的条目（status: confirmed, producer: skill-5）

#### 功能 3：验证模式（verify）—— bug report → eval-doc + issue

**描述**：用户报告问题，Skill 5 引导收集结构化信息并创建 GitHub issue。

**输入**：报告一个实际存在的 bug（protocol scoped_name 双前缀 bug）。

**操作步骤**：
1. 触发 Skill 5 验证模式：说 "发现一个 bug：scoped_name('alice-helper', 'alice') 返回了 'alice-alice-helper' 而不是 'alice-helper'"
2. 配合 Skill 5 的引导回答问题

**预期输出**：
- Skill 5 按 `references/feedback-guide.md` 引导收集信息：
  - 操作步骤
  - 预期行为
  - 实际行为
  - 复现性
  - 证据
- 生成 eval-doc（mode: verify）
- 提供分流建议（应为 "疑似 bug"，因为测试已失败）
- 分流建议有具体理由

**验证方式**：
- 检查 eval-doc 格式是否完整（mode: verify, 有证据区, 有分流建议）
- 检查分流建议是否合理且有理由

#### 功能 4：创建 GitHub issue（create-issue.sh）

**描述**：从 eval-doc 自动创建 GitHub issue。

**操作步骤**：
1. 接续功能 3，Skill 5 应提议创建 issue
2. 使用 `--dry-run` 模式测试：
   ```bash
   bash /home/yaosh/.claude/skills/dev-loop-skills/skills/skill-5-feature-eval/scripts/create-issue.sh \
     --eval-doc /home/yaosh/projects/zchat/.artifacts/eval-docs/eval-scoped-name-001.md \
     --repo ezagent42/zchat \
     --dry-run
   ```

**预期输出**：
- 脚本解析 eval-doc 提取 title 和 body
- `--dry-run` 模式显示将要创建的 issue 内容但不实际创建
- title 包含 feature 名称
- body 包含 testcase 表格和证据

**验证方式**：
- 检查 `--dry-run` 输出是否包含正确的 title 和 body
- 检查 body 是否包含 testcase 表格

#### 功能 5：添加 watcher（add-watcher.sh）

**描述**：为 issue 添加 watcher。

**操作步骤**：
1. 使用 `--dry-run` 模式测试：
   ```bash
   bash /home/yaosh/.claude/skills/dev-loop-skills/skills/skill-5-feature-eval/scripts/add-watcher.sh \
     --issue-url https://github.com/ezagent42/zchat/issues/1 \
     --watcher testuser \
     --dry-run
   ```

**预期输出**：
- `--dry-run` 模式显示将要执行的操作
- 不实际调用 GitHub API

**验证方式**：
- 检查脚本输出是否显示了正确的 issue URL 和 watcher

#### 功能 6：Artifact 注册（验证模式完整流程）

**描述**：验证模式产出 eval-doc 和 issue 引用都注册到 registry。

**预期输出**：
- eval-doc 注册（type: eval-doc, mode: verify）
- issue 引用注册（type: issue，如果实际创建了 issue）
- 两者通过 `related_ids` 关联

**验证方式**：
- 检查 registry.json 中的条目
- 检查 related_ids 是否正确建立了关联

---

### Skill 6: artifact-registry

**触发方式**：在 Claude Code 中说 "registry"、"artifact"、".artifacts/"、"pipeline status"。

#### 功能 1：init-artifact-space

**描述**：初始化项目的 `.artifacts/` 目录结构。

**操作步骤**：
1. 在一个临时目录测试（不要覆盖已有的 .artifacts/）：
   ```bash
   mkdir -p /tmp/test-init-artifact
   bash /home/yaosh/.claude/skills/artifact-registry/scripts/init-artifact-space.sh \
     --project-root /tmp/test-init-artifact
   ```

**预期输出**：
- 创建 `.artifacts/` 目录结构：registry.json, eval-docs/, code-diffs/, test-plans/, test-diffs/, e2e-reports/, issues/, coverage/
- registry.json 内容为 `{"version": 1, "artifacts": []}`
- `.gitattributes` 配置 git-lfs（*.png, *.gif, *.cast）

**验证方式**：
```bash
ls -R /tmp/test-init-artifact/.artifacts/
cat /tmp/test-init-artifact/.artifacts/registry.json
cat /tmp/test-init-artifact/.artifacts/.gitattributes
```

**清理**：`rm -rf /tmp/test-init-artifact`

#### 功能 2：register

**描述**：注册新 artifact 到 registry。

**操作步骤**：
```bash
# 先初始化
bash /home/yaosh/.claude/skills/artifact-registry/scripts/init-artifact-space.sh \
  --project-root /tmp/test-register
# 创建测试文件
mkdir -p /tmp/test-register/.artifacts/eval-docs
echo "test" > /tmp/test-register/.artifacts/eval-docs/eval-test-001.md
# 初始化 git（register.sh 需要 git commit）
cd /tmp/test-register && git init && git add . && git commit -m "init"
# 注册
bash /home/yaosh/.claude/skills/artifact-registry/scripts/register.sh \
  --project-root /tmp/test-register \
  --type eval-doc \
  --name "测试 eval-doc" \
  --producer skill-5 \
  --path .artifacts/eval-docs/eval-test-001.md \
  --status draft
```

**预期输出**：
- registry.json 中新增一个条目，ID 格式为 `eval-doc-001`
- 条目包含所有字段：id, name, type, status, producer, path, created_at, updated_at
- git 有新 commit（message: `artifact: register eval-doc-001 (eval-doc)`）

**验证方式**：
```bash
cat /tmp/test-register/.artifacts/registry.json
cd /tmp/test-register && git log --oneline -1
```

**清理**：`rm -rf /tmp/test-register`

#### 功能 3：query

**描述**：按 type、status、id 查询 artifact。

**操作步骤**：在 zchat 项目上测试查询（已有 bootstrap 数据）。

```bash
# 按 type 查询
bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat --type coverage-matrix

# 按 status 查询
bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat --status draft

# 按 id 查询
bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat --id coverage-matrix-001

# 全局概览
bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat --summary
```

**预期输出**：
- 按 type 查询返回 2 个 coverage-matrix 条目
- 按 status 查询返回所有 draft 状态的条目
- 按 id 查询返回精确匹配的 1 个条目
- `--summary` 返回各类型各状态的数量统计表

**验证方式**：
- 比对查询结果与 `registry.json` 的实际内容
- 验证 JSON 输出格式正确

#### 功能 4：update-status

**描述**：更新 artifact 状态，验证合法的状态流转。

**操作步骤**：
```bash
# 在临时环境中测试
# (沿用功能 2 的注册结果，或重新创建)
# 正常流转：draft → confirmed
bash /home/yaosh/.claude/skills/artifact-registry/scripts/update-status.sh \
  --project-root /tmp/test-register \
  --id eval-doc-001 \
  --status confirmed

# 继续流转：confirmed → executed
bash /home/yaosh/.claude/skills/artifact-registry/scripts/update-status.sh \
  --project-root /tmp/test-register \
  --id eval-doc-001 \
  --status executed

# 非法流转测试：executed → draft（应被拒绝）
bash /home/yaosh/.claude/skills/artifact-registry/scripts/update-status.sh \
  --project-root /tmp/test-register \
  --id eval-doc-001 \
  --status draft
```

**预期输出**：
- draft → confirmed：成功，registry.json 更新，git commit
- confirmed → executed：成功
- executed → draft：失败，脚本报错（非零退出码），registry 不变

**验证方式**：
- 每步检查 registry.json 中的 status 和 updated_at
- 非法流转检查退出码 `$?` 是否非零

#### 功能 5：link

**描述**：建立两个 artifact 之间的双向关联。

**操作步骤**：
```bash
# 在临时环境注册两个 artifact
# (沿用功能 2 的环境)
echo "test plan" > /tmp/test-register/.artifacts/test-plans/plan-test-001.md
cd /tmp/test-register && git add . && git commit -m "add test plan"

bash /home/yaosh/.claude/skills/artifact-registry/scripts/register.sh \
  --project-root /tmp/test-register \
  --type test-plan --name "测试 plan" \
  --producer skill-2 \
  --path .artifacts/test-plans/plan-test-001.md \
  --status draft

# 建立关联
bash /home/yaosh/.claude/skills/artifact-registry/scripts/link.sh \
  --project-root /tmp/test-register \
  --from eval-doc-001 \
  --to test-plan-001
```

**预期输出**：
- eval-doc-001 的 related_ids 包含 `test-plan-001`
- test-plan-001 的 related_ids 包含 `eval-doc-001`
- 双向关联

**验证方式**：
```bash
cat /tmp/test-register/.artifacts/registry.json | python3 -m json.tool
```
检查两个条目的 related_ids 字段。

---

## 端到端循环测试

这是最关键的测试：走完一个完整的 Phase 1 → Phase 5 循环，验证 artifact 在 skill 之间正确流转。

### 循环场景：zchat agent DM 功能

选择 "agent 间通过 IRC DM 直接私聊" 作为测试场景，因为这是 coverage-matrix 中标记为 ❌ 的真实用户流程。

### Step 1: Phase 1 — Skill 5 (simulate) → 产出 eval-doc

**操作**：
1. 触发 Skill 5 模拟模式
2. 描述 feature："如果 zchat 支持 agent 间通过 IRC DM 直接私聊（不经过频道），预期各场景的效果"
3. 审查 testcase 列表，确认后发布

**预期产出**：
- `.artifacts/eval-docs/eval-agent-dm-{seq}.md`（status: confirmed）
- registry.json 中新增 eval-doc 条目

**验证**：
```bash
bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat --type eval-doc --status confirmed
```
确认返回至少 1 个 confirmed 的 eval-doc。

### Step 2: Phase 3 — Skill 2 → 消费 eval-doc → 产出 test-plan

**操作**：
1. 触发 Skill 2
2. 说 "从最新的 confirmed eval-doc 和 coverage-matrix 生成测试计划"
3. Skill 2 应同时读取 eval-doc 和 coverage-matrix

**预期产出**：
- `.artifacts/test-plans/plan-agent-dm-{seq}.md`（status: draft）
- plan 中的用例来源包含 `eval-doc` 和 `coverage-gap`（因为该流程在 coverage-matrix 中是 ❌）
- 注册到 registry，related_ids 包含 eval-doc 的 ID

**验证**：
```bash
bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat --type test-plan --status draft
```
读取 plan 文件验证用例完整性。

### Step 3: 人 confirm test-plan

**操作**：
1. 审查 test-plan 内容
2. 可选：调整用例
3. 说 "确认这个测试计划"

**预期**：
- test-plan 状态从 draft → confirmed

**验证**：
```bash
bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat --type test-plan --status confirmed
```

### Step 4: Phase 4 — Skill 3 → 消费 confirmed test-plan → 产出 test-diff + E2E 代码

**操作**：
1. 触发 Skill 3
2. 说 "根据 confirmed test-plan 编写 E2E 测试代码"

**预期产出**：
- `tests/e2e/` 中新增或追加了测试代码
- `.artifacts/test-diffs/test-diff-{seq}.md`
- 源 test-plan 状态更新为 executed
- test-diff 注册到 registry

**验证**：
```bash
# 检查新文件
ls tests/e2e/test_agent_dm*.py 2>/dev/null || echo "检查是否追加到已有文件"

# 检查 test-diff
bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat --type test-diff

# 检查 test-plan 状态已更新
bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat --type test-plan --status executed
```

验证生成的代码语法正确：
```bash
python -c "import ast; ast.parse(open('tests/e2e/<new_file>.py').read())"
```

### Step 5: Phase 5 — Skill 4 → 执行 E2E → 产出 e2e-report → 更新 coverage-matrix

**操作**：
1. 确保 ergo 和 zellij 运行中（`zchat irc daemon start` + zellij session）
2. 触发 Skill 4
3. 说 "运行完整 E2E 套件并生成报告"

**预期产出**：
- `.artifacts/e2e-reports/report-agent-dm-{seq}/report.md`
- report 中区分 new-case 和 regression-case
- 回归测试不应有新增失败（除了已知的 4 个 MCP 超时）
- coverage-matrix 更新
- 注册到 registry

**验证**：
```bash
# 检查 report
bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat --type e2e-report

# 检查 coverage-matrix 是否更新
git diff .artifacts/coverage/coverage-matrix.md
```

### Step 6: 验证 artifact 链条完整性

走完上述 5 步后，验证整个 artifact 链条：

```bash
# 全局概览
bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat --summary
```

**预期的完整链条**：

```
eval-doc (confirmed) 
  → test-plan (executed)    [related: eval-doc]
    → test-diff (draft)     [related: test-plan]
      → e2e-report (draft)  [related: test-diff]
```

**逐项验证**：

| 检查项 | 命令 | 预期 |
|--------|------|------|
| eval-doc 存在且 confirmed | `query.sh --type eval-doc --status confirmed` | 至少 1 个 |
| test-plan 存在且 executed | `query.sh --type test-plan --status executed` | 至少 1 个 |
| test-diff 存在 | `query.sh --type test-diff` | 至少 1 个 |
| e2e-report 存在 | `query.sh --type e2e-report` | 至少 1 个 |
| related_ids 链条完整 | 逐个检查 related_ids | 每个 artifact 关联到上游 |
| coverage-matrix 已更新 | `git diff .artifacts/coverage/` | 有变更 |
| 所有 artifact 文件都实际存在 | 逐个检查 registry 中 path 指向的文件 | 全部存在 |

---

## 执行说明

### 新 session 冷启动清单

新 session 开始时，按以下顺序准备环境：

1. **确认项目目录**：
   ```bash
   cd /home/yaosh/projects/zchat
   ```

2. **确认 .artifacts/ 已初始化**：
   ```bash
   ls .artifacts/registry.json
   ```

3. **确认 skill 可加载**：
   - Skill 1 symlink 存在：`ls -la ~/.claude/skills/project-discussion-zchat`
   - Skill 6 symlink 存在：`ls -la ~/.claude/skills/artifact-registry`
   - 其他 skill 的 SKILL.md 存在：
     ```bash
     for i in 0 2 3 4 5; do
       ls ~/.claude/skills/dev-loop-skills/skills/skill-${i}-*/SKILL.md
     done
     ```

4. **确认环境依赖**：
   ```bash
   which ergo zellij uv weechat python3 git gh
   ```

5. **确认测试基线**：
   ```bash
   uv run pytest tests/unit/ -v --tb=short -q 2>&1 | tail -5
   ```

### 逐个验证 vs 完整循环

**逐个验证**（推荐先执行）：

按上面"测试场景"的顺序，逐个 skill 验证。每个 skill 内部按功能编号顺序测试。优先顺序：

1. **Skill 6** — 基础设施，所有其他 skill 依赖它
2. **Skill 1** — 知识层，Skill 2/3 依赖它
3. **Skill 5** — pipeline 的入口（Phase 1）和出口（Phase 7）
4. **Skill 2** → **Skill 3** → **Skill 4** — pipeline 中间链条，按顺序测试

每个 skill 的每个功能独立测试，失败时修复后重跑该功能，不需要从头开始。

**每个 skill 执行后必须运行验证脚本**：

验证脚本位于 `docs/discuss/skill-dev/verify-skill-output.sh`，独立于被测 skill，直接检查磁盘上的文件。

```bash
VERIFY="./docs/discuss/skill-dev/verify-skill-output.sh"

# 每个 skill 执行前：快照 registry
cp .artifacts/registry.json /tmp/registry-before.json

# Skill 1 执行后：验证回答包含 file:line + 测试输出
$VERIFY 1 --artifact <skill1-output.md>

# Skill 2 执行后：验证 test-plan 生成 + registry 更新
$VERIFY 2 --before /tmp/registry-before.json --artifact .artifacts/test-plans/plan-xxx.md

# Skill 3 执行后：验证 E2E 代码写入 + @pytest.mark.e2e
$VERIFY 3 --before /tmp/registry-before.json

# Skill 4 执行后：验证 pytest 确实跑了 + e2e-report 生成
$VERIFY 4 --before /tmp/registry-before.json --artifact .artifacts/e2e-reports/report-xxx.md

# Skill 5 执行后：验证 eval-doc 生成 + testcase 表格
$VERIFY 5 --before /tmp/registry-before.json --artifact .artifacts/eval-docs/eval-xxx.md

# Skill 6 执行后：验证 registry.json 合法
$VERIFY 6 --before /tmp/registry-before.json
```

验证脚本检查的内容（防幻觉）：
- **文件存在性** — artifact 文件是否真的在磁盘上
- **YAML frontmatter** — type/id/status 字段是否齐全
- **registry diff** — 执行前后 registry.json 是否新增了条目
- **file:line 交叉验证** — 提取引用的 `xxx.py:123`，验证源码该行存在
- **pytest 时间戳** — `.pytest_cache` 是否在最近几分钟被修改（证明 pytest 真跑了）

**完整循环**（逐个验证都通过后执行）：

按"端到端循环测试"部分的 Step 1-6 顺序执行。完成后运行链条验证：

```bash
$VERIFY chain
```

这会检查 eval-doc → test-plan → test-diff → e2e-report 完整链条是否存在且互相引用。

### 失败处理

| 失败类型 | 处理方式 |
|----------|---------|
| 脚本不存在或不可执行 | 检查 skill 目录结构，确认 `chmod +x` |
| 脚本运行报错 | 先用 `--dry-run` 模式测试，检查参数是否正确 |
| Skill 未正确触发 | 检查 SKILL.md 的 description 字段是否包含触发词 |
| Artifact 未注册 | 检查 `--project-root` 参数是否指向正确目录 |
| 状态流转失败 | 检查当前状态是否允许目标状态（draft → confirmed → executed → archived） |
| E2E 测试失败（环境原因） | 检查 ergo/zellij 是否运行中：`pgrep ergo` / `zellij list-sessions` |
| E2E 测试失败（代码原因） | 检查 traceback，定位具体失败原因。如果是已知的 MCP 超时 bug（4 个测试），记录并继续 |
| Skill 回答无 file:line 引用 | Skill 1 的问答流程有缺陷，检查 SKILL.md 的 Step 2-3 |
| Registry 数据不一致 | 手动检查 `registry.json`，必要时用 `query.sh` 交叉验证 |

### 测试产出清理

本测试计划会在 `.artifacts/` 中产生测试数据。完成后，如需清理：

```bash
# 查看所有测试过程中产生的 artifact
bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat --summary

# 决定哪些保留（真实循环产出的 eval-doc / test-plan / e2e-report 建议保留）
# 决定哪些清理（功能测试中创建的临时 artifact）
```

临时测试文件（如功能 2 的 code-diff-test-001）应在对应功能测试完成后立即清理。端到端循环产出的 artifact 建议保留，作为 pipeline 的第一次真实运行记录。
