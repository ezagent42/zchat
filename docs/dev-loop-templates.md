# Dev-Loop 模板与命名规范

> Artifact frontmatter 模板、文件命名规则、seq 编号规则、术语表。
>
> 配合 [开发手册](dev-loop-guide.md) 和 [phases-guide](dev-loop-phases.md) 使用。

---

## 1. Frontmatter 模板

### 1.1 eval-doc（Phase 1 simulate / Phase 7 verify）

```yaml
---
id: eval-{feature-slug}-{seq}        # 如 eval-dm-support-008
title: "feat: 简短标题"               # 或 "bug: 简短标题"
type: eval-doc
mode: simulate                        # simulate | verify
status: draft                         # draft → confirmed
created_at: "2026-04-15"
updated_at: "2026-04-15"              # 每次修改时更新
author: "skill-5"                     # 或人类用户名
trigger: "用户需求描述 / report-xxx"   # 是什么触发了这个 eval
github_issue: "owner/repo#N"          # 创建 issue 后回填
related:
  - report-dm-cli-007                 # 关联的其他 artifact id
modules:                              # 涉及的代码模块
  - zchat.cli
  - channel-server
---
```

### 1.2 test-plan（Phase 3）

```yaml
---
type: test-plan
id: test-plan-{seq}                   # 全局序号，如 test-plan-009
status: draft                         # draft → confirmed → executed
producer: skill-2
created_at: "2026-04-15"
updated_at: "2026-04-15"
trigger: "eval-doc-008 (简短描述)"
related:
  - eval-doc-008                      # 来源 eval-doc
  - test-diff-006                     # 下游 test-diff（executed 后回填）
---
```

### 1.3 test-diff（Phase 4）

```yaml
---
type: test-diff
id: test-diff-{seq}                   # 全局序号，如 test-diff-006
status: draft                         # draft → confirmed → executed
producer: skill-3
created_at: "2026-04-15"
updated_at: "2026-04-15"
related:
  - test-plan-009                     # 来源 test-plan
  - eval-doc-008                      # 关联 eval-doc
evidence: []                          # Phase 5 后可补充
---
```

### 1.4 e2e-report（Phase 5）

```yaml
---
type: e2e-report
id: report-{name}-{seq}              # 如 report-dm-cli-007
status: all-pass                      # all-pass | partial-pass | regression-failure
producer: skill-4
created_at: "2026-04-15"
trigger: "test-diff-006 (描述)"
related:
  - test-diff-006
  - test-plan-009
evidence:
  - .artifacts/e2e-reports/report-dm-cli-007/raw-output.log
---
```

### 1.5 issue-ref（Phase 7）

```yaml
---
type: issue-ref
id: issue-{finding-slug}-{seq}       # 如 issue-ergo-midrun-stability-009
github_issue: "owner/repo#N"
title: "bug: 简短标题"
state: open                           # open | closed
created_at: "2026-04-15"
related:
  - eval-ergo-midrun-stability-009    # 来源 eval-doc
  - report-dm-cli-007                 # 关联 report
---
```

### 1.6 code-diff（Phase 2，可选）

```yaml
---
type: code-diff
id: code-diff-{seq}                   # 全局序号
status: draft                         # draft → confirmed
producer: "human / agent"
created_at: "2026-04-15"
related:
  - eval-doc-008                      # 关联 eval-doc
---
```

---

## 2. 文件命名规则

### 2.1 Artifact 文件

| 类型 | 文件名模板 | 示例 |
|------|-----------|------|
| eval-doc | `eval-{feature-slug}-{seq}.md` | `eval-dm-support-008.md` |
| test-plan | `plan-{feature-slug}-{seq}.md` | `plan-dm-support-009.md` |
| test-diff | `test-diff-{seq}.md` | `test-diff-006.md` |
| e2e-report | `report-{name}-{seq}/report.md` | `report-dm-cli-007/report.md` |
| issue-ref | `issue-{finding-slug}-{seq}.md` | `issue-ergo-midrun-stability-009.md` |
| code-diff | `code-diff-{seq}.md` | `code-diff-004.md` |

### 2.2 测试文件

| 项目 | 规则 | 示例 |
|------|------|------|
| 文件名 | `test_{domain}.py` | `test_cli_dm.py`、`test_agent_dm.py` |
| 函数名 | `test_{action}_{target}` | `test_cli_dm_send_basic`、`test_dm_help_exists` |
| Fixture | 描述性名词，小写下划线 | `irc_probe`、`bob_probe`、`ergo_server` |

### 2.3 分支名

| 类型 | 格式 | 示例 |
|------|------|------|
| Feature | `feat/{feature-slug}` | `feat/dm-support` |
| Bug fix | `fix/{issue-number}-{slug}` | `fix/55-ergo-stability` |
| Hotfix | `hotfix/{slug}` | `hotfix/ergo-crash` |

---

## 3. Seq 编号规则

### 3.1 全局序号

`{seq}` 是**全局递增**的，跨所有 artifact 类型共享一个序列：

```
eval-wsl2-proxy-003     → seq = 003
eval-ergo-languages-004 → seq = 004
test-plan-005           → seq = 005
eval-weechat-cache-006  → seq = 006
eval-ctrl-c-orphan-007  → seq = 007
eval-dm-support-008     → seq = 008
test-plan-009           → seq = 009
```

### 3.2 如何确定下一个 seq

1. 打开 `.artifacts/registry.json`
2. 找到所有 artifact 的 id，提取最大 seq 数字
3. 新 artifact 的 seq = 最大值 + 1
4. 如果没有 registry.json，扫描 `.artifacts/` 下所有文件名中的数字取最大值

### 3.3 特殊情况

- e2e-report 的 seq 独立于主序列（因为格式是 `report-{name}-{seq}`），但建议与主序列对齐以减少混淆
- 如果多人同时操作导致冲突，以先 commit 的为准，后 commit 的调整 seq

---

## 4. Registry.json 结构

```json
{
  "version": 1,
  "artifacts": [
    {
      "id": "eval-doc-008",
      "name": "feat: person-to-person DM in zchat",
      "type": "eval-doc",
      "status": "confirmed",
      "producer": "skill-5",
      "consumers": ["test-plan-009"],
      "path": ".artifacts/eval-docs/eval-dm-support-008.md",
      "created_at": "2026-04-15T00:00:00Z",
      "updated_at": "2026-04-15T00:00:00Z",
      "related_ids": ["test-plan-009", "test-diff-006"]
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `id` | 全局唯一，格式 `{type}-{seq}` |
| `name` | 人类可读标题 |
| `type` | eval-doc / test-plan / test-diff / e2e-report / issue-ref / code-diff |
| `status` | 当前状态（与 frontmatter 一致） |
| `producer` | 产出者（skill-2 / skill-3 / ... / human） |
| `consumers` | 下游消费者 id 列表 |
| `path` | 文件相对路径 |
| `related_ids` | 关联 artifact id 列表 |

### 4.1 Registry id 与 Frontmatter id 的关系

项目中存在两种 id 格式，各有用途：

| 格式 | 出现位置 | 示例 | 用途 |
|------|----------|------|------|
| `{type}-{seq}` | registry.json 的 `id` 字段 | `eval-doc-008` | 机器索引的主键，全局唯一，格式统一 |
| `{type-slug}-{feature}-{seq}` | 文件 frontmatter 的 `id` 字段 | `eval-dm-support-008` | 人类可读，包含 feature 语义 |

**映射规则**：
- registry 的 `path` 字段将 registry id 映射到实际文件
- **查找 artifact 时以 registry id 为主键**
- 文件 frontmatter id 允许包含 feature-slug 便于人类浏览目录时识别
- `related` 字段中引用其他 artifact 时，**统一使用 registry id 格式**（如 `test-plan-009`），不用文件名格式

**示例映射**：
```
registry id:     eval-doc-008
registry path:   .artifacts/eval-docs/eval-dm-support-008.md
frontmatter id:  eval-dm-support-008
```

---

## 5. 术语表

| 术语 | 全称 | 含义 |
|------|------|------|
| **Skill 1** | project-discussion | 项目知识问答：回答"代码怎么工作"的问题 |
| **Skill 2** | test-plan-generator | 从 eval-doc / code-diff 生成结构化测试计划 |
| **Skill 3** | test-code-writer | 把 confirmed 的 test-plan 转为可运行的 pytest 代码 |
| **Skill 4** | test-runner | 跑全量 E2E 测试，区分 new vs regression，生成报告 |
| **Skill 5** | feature-eval | 两种模式：simulate（需求评估）和 verify（bug 归档） |
| **Skill 6** | artifact-registry | 管理 `.artifacts/` 的索引、查询、状态更新 |
| **eval-doc** | evaluation document | 预期 vs 实际/模拟的对比文档 |
| **test-plan** | — | 结构化的测试用例列表（TC-001 … TC-00N） |
| **test-diff** | — | 记录新增/修改了哪些测试函数 |
| **e2e-report** | end-to-end report | 一次全量 E2E 跑测的结构化报告 |
| **TC** | test case | 单个测试用例 |
| **P0/P1/P2** | priority 0/1/2 | P0 = 核心功能 / P1 = 重要 / P2 = 锦上添花 |
| **RACI** | Responsible, Accountable, Consulted, Informed | 角色职责矩阵 |
| **regression** | — | 原本通过的测试现在失败了 |
| **new-case** | — | 本次新增的测试用例 |
| **red-light test** | — | 故意在功能实现前写的测试，预期 FAIL，实现后转绿 |
| **parent issue** | — | 每个 feature 的 GitHub issue 入口，所有讨论在此 |
| **artifact** | — | pipeline 产出的结构化文档，存在 `.artifacts/` |
| **frontmatter** | — | Markdown 文件头部的 YAML 元数据块（`---` 包围） |
| **seq** | sequence number | 全局递增编号 |
