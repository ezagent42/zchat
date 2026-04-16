# Dev-Loop 各阶段详细指南

> 每个 Phase 的入口条件、详细操作步骤、出口条件、异常回退方案。
>
> 配合 [开发手册](dev-loop-guide.md) 阅读；frontmatter 模板见 [templates](dev-loop-templates.md)。

---

## Phase 1：需求评估

### 入口条件
- 人类提出了一个 feature 想法或改进需求

### 在哪个分支
- **`feat/{feature-name}`**（Phase 1 开始时即创建 feature 分支，后续所有 artifact 和代码都在此分支上）

### 谁来启动
- **人类**在 IRC/飞书 描述需求，例如："我想给 zchat 加一个 `dm send` 命令"
- **Agent** 收到后主动进入 Phase 1

### 操作步骤

| 步骤 | 执行者 | 动作 | 产出 |
|------|--------|------|------|
| 0 | Agent/人类 | `git checkout -b feat/{feature-name}` 创建 feature 分支 | 新分支 |
| 1 | Agent | 读相关代码，分析 feature 可行性 | — |
| 2 | Agent | 生成 eval-doc（mode=simulate），列 testcases 表格 | `.artifacts/eval-docs/eval-{feature}-{seq}.md` (status: draft) |
| 3 | Agent | 创建 GitHub parent issue，body 包含 eval-doc 摘要 | `{repo}#N` |
| 4 | Agent | 通知人类："eval-doc 已生成，请在 issue #N 确认" | IRC/飞书消息 |
| 5 | 人类 | 在 issue comment 审阅 testcases，提修改意见或确认 | issue comment |
| 6 | Agent | 根据人类反馈修改 eval-doc，status: draft → confirmed | 更新文件 |

### 出口条件
- eval-doc status = `confirmed`
- parent issue 已创建
- Agent 已 `git add + commit` eval-doc 到 `feat/{feature}` 分支（commit message: `artifact: add eval-{feature}-{seq}`）

### 异常回退

| 情况 | 处理 |
|------|------|
| 人类觉得 feature 不可行 | eval-doc status 保持 draft，在 issue comment 记录原因，issue 标 `wontfix` 关闭 |
| 需求变更 | 更新 eval-doc 内容 + updated_at，不新建文件 |
| eval-doc 的 testcases 需要大改 | 在同一文件上修改；如果方向完全不同，新建 eval-doc 并关联旧的 |

---

## Phase 2：编码

### 入口条件
- eval-doc status = `confirmed`

### 谁来启动
- **人类**在 `feat/{feature-name}` 分支（Phase 1 已创建）上开始编码

### 操作步骤

| 步骤 | 执行者 | 动作 | 产出 |
|------|--------|------|------|
| 1 | 人类 | 确认在 `feat/{feature-name}` 分支上（`git branch --show-current`） | — |
| 2 | 人类 | 编写产品代码（可请 Agent 辅助） | `src/**` / `zchat/**` 等 |
| 3 | 人类/Agent | （可选）写 code-diff artifact 记录关键设计决策 | `.artifacts/code-diffs/code-diff-{seq}.md` |
| 4 | 人类 | 本地跑单元测试 / lint / type check 确保基础质量 | — |
| 5 | 人类 | commit 到 feature 分支（不 push、不开 PR，等 Phase 3-5 完成） | git history |

### 编码规范
- **一个 PR 只做一件事**：feature 代码 + 对应测试 + artifacts，不夹带无关重构
- **commit message**：动词开头（add / fix / update），首行 < 72 字符
- **不改无关代码**：即使看到旁边有 TODO，不在本 PR 处理

### 出口条件
- 产品代码在 feature 分支上
- 本地基础检查通过（lint / type / 单元测试）

### 异常回退

| 情况 | 处理 |
|------|------|
| 编码中发现 eval-doc 的预期不合理 | 回到 Phase 1 更新 eval-doc，在 issue comment 说明 |
| 编码中发现依赖模块有 bug | 为该 bug 单独走 Phase 7（Skill 5 verify）开 issue，不在当前 PR 修 |
| 代码方案需要重大调整 | 在 issue comment 讨论，达成共识后继续 |

---

## Phase 3：测试计划

### 入口条件
- eval-doc status = `confirmed`
- （理想情况）产品代码已在 feature 分支（Phase 2 完成），但也允许先写红灯测试

### 谁来启动
- **人类**说"写测试计划"或"进入 Phase 3"
- **Agent** 执行 Skill 2

### 操作步骤

| 步骤 | 执行者 | 动作 | 产出 |
|------|--------|------|------|
| 1 | Agent | 读 eval-doc，拆 TC-001 … TC-00N | — |
| 2 | Agent | 写 test-plan（status: draft） | `.artifacts/test-plans/plan-{feature}-{seq}.md` |
| 3 | Agent | 在 parent issue 发 comment：TC 表格 + review checklist | issue comment |
| 4 | 人类 | 在 comment 勾选 4 项 checklist，提修改意见 | issue comment |
| 5 | Agent | 根据反馈修改 plan，status: draft → confirmed | 更新文件 |

### Review checklist（必须全部勾选）
- [ ] 用例 / 范围是否齐全？
- [ ] 优先级分配是否合理？
- [ ] 前置条件 / 预期结果是否准确？
- [ ] 是否漏掉相关依赖 / 回归影响？

### 出口条件
- test-plan status = `confirmed`
- review checklist 4 项全部勾选
- Agent 已 `git add + commit` plan 到 `feat/{feature}` 分支（commit message: `artifact: confirm test-plan-{seq}`）

### 异常回退

| 情况 | 处理 |
|------|------|
| 人类认为 TC 缺失 | Agent 补充后重新 review |
| 人类认为优先级不对 | Agent 调整后重新 review |
| 整个 plan 方向错误 | 重新读 eval-doc，从头生成新 plan（保留旧 plan 做参考，不删除） |

---

## Phase 4：写测试代码

### 入口条件
- test-plan status = `confirmed`

### 谁来启动
- **人类**说"继续"或"进入 Phase 4"
- **Agent** 执行 Skill 3

### 操作步骤

| 步骤 | 执行者 | 动作 | 产出 |
|------|--------|------|------|
| 1 | Agent | 读 plan 的每个 TC + 现有 conftest.py / 测试文件 | — |
| 2 | Agent | 决定每个 TC 的文件归属、fixture 复用、order 编号 | — |
| 3 | Agent | 写测试代码 | `tests/e2e/test_{domain}.py` |
| 4 | Agent | （如需）在 conftest.py 新增 fixture | `tests/e2e/conftest.py` |
| 5 | Agent | `python -c "import ast; ast.parse(...)"` 语法校验 | — |
| 6 | Agent | `pytest --collect-only` 确认用例可发现 | — |
| 7 | Agent | 写 test-diff artifact | `.artifacts/test-diffs/test-diff-{seq}.md` |
| 8 | Agent | plan status → executed；test-diff status → confirmed | 更新文件 |
| 9 | Agent | 在 issue comment 贴 TC → 函数映射表 | issue comment |

### 关键规则
- **不真跑测试**（Phase 5 的事）；只做语法 + 收集校验
- **优先复用 fixture**，无新增就不加
- **order 编号不冲突**：检查现有测试的 order 范围，新增的 range 不重叠
- **断言消息要具体**：`"agent0 not on IRC after create"` 而非 `"assertion failed"`

### 出口条件
- 所有 TC 有对应的 test 函数
- `ast.parse()` + `--collect-only` 通过
- test-diff status = `confirmed`
- plan status = `executed`
- Agent 已 `git add + commit` 测试文件 + test-diff（commit message: `artifact: add test-diff-{seq} + tests/e2e/test_{domain}.py`）

### 异常回退

| 情况 | 处理 |
|------|------|
| 现有 fixture 不满足需求 | 在 conftest.py 新增，加 docstring，用 yield 管理 cleanup |
| order 编号冲突 | 调整新测试的 order range，在 test-diff 中说明 |
| plan 中某个 TC 无法实现为自动化测试 | 在 test-diff 中标注"手动验证"，不勉强自动化 |

---

## Phase 5：跑全量 E2E

### 入口条件
- test-diff status = `confirmed`
- 环境就绪（tmux / zellij / ergo / uv）

### 谁来启动
- **人类**说"跑测试"或"进入 Phase 5"
- **Agent** 执行 Skill 4

### 操作步骤

| 步骤 | 执行者 | 动作 | 产出 |
|------|--------|------|------|
| 1 | Agent | 环境预检：tmux session / zellij / ergo 可用 / uv 已装 | — |
| 2 | Agent | `uv run pytest tests/e2e/ -v --tb=short` **全量**（不只跑新用例） | — |
| 3 | Agent | 保存 raw log | `.artifacts/e2e-reports/report-{name}-{seq}/raw-output.log` |
| 4 | Agent | 从 test-diff 提取新用例列表，分类 new vs regression | — |
| 5 | Agent | 写 report.md（总览 + 新功能表 + regression 表 + 根因 + 次级发现） | `report.md` |
| 6 | Agent | 在 issue comment 贴报告摘要 | issue comment |
| 7 | 人类 | 看报告，决策下一步 | issue comment |

### 结果分类规则

| 类别 | 判定依据 | 严重性 |
|------|----------|--------|
| **New-case PASS** | 函数在 test-diff 中 + 通过 | 好消息：新功能工作 |
| **New-case FAIL** | 函数在 test-diff 中 + 失败 | 预期中（红灯测试）或需修代码 |
| **Regression PASS** | 函数不在 test-diff 中 + 通过 | 正常 |
| **Regression FAIL** | 函数不在 test-diff 中 + 失败 | **高严重性**：旧功能被破坏 |

报告 top-level status：
- `all-pass`：全绿
- `partial-pass`：仅 new-case FAIL，regression 全绿
- `regression-failure`：有 regression FAIL（最高优先级修复）

### 出口条件
- report.md 写入 `.artifacts/e2e-reports/`
- issue comment 已发
- Agent 已 `git add + commit` report + raw log（commit message: `artifact: add report-{name}-{seq}`）

### 异常回退

| 情况 | 处理 |
|------|------|
| 环境预检不通过 | 报告缺什么，不跑测试（误导性结果比没结果更糟） |
| Regression FAIL | **优先修复回归**，然后重跑 Phase 5；不要先做新功能 |
| 环境 flakiness（ergo 中途挂了） | 根因诊断拆开，环境问题走 Phase 7 单开 issue；隔离 rerun 验证新功能 |
| 全部 FAIL | 检查是否是环境问题（端口、进程）而非代码问题 |

---

## Phase 6：Artifact 登记

### 说明
这不是一个独立阶段，而是**贯穿全流程**的动作。每次产出新 artifact 时：

1. 更新 `.artifacts/registry.json`
2. 更新关联 artifact 的 `related` / `status` / `consumers`
3. `git add` + `commit`

### 规则
- registry.json 的 `id` 是全局唯一的（如 `eval-doc-008`、`test-plan-009`）
- `path` 字段指向实际的 markdown 文件路径
- `consumers` 数组记录下游消费者
- 每个 artifact 的 frontmatter 中 `related` 字段与 registry 双向一致

---

## Phase 7：反馈归档

### 入口条件
- Phase 5 发现异常 / 非预期行为
- 或人类主动报告 bug / 问题

### 谁来启动
- **人类**说"发现 bug"或"归档发现"
- **Agent** 执行 Skill 5 verify

### 操作步骤

| 步骤 | 执行者 | 动作 | 产出 |
|------|--------|------|------|
| 1 | Agent | 从 e2e-report 提取失败信息，或引导人类描述问题 | — |
| 2 | Agent | 写 eval-doc（mode=verify），含 testcases + 证据区 + 分流建议 | `.artifacts/eval-docs/eval-{finding}-{seq}.md` |
| 3 | Agent | 创建 GitHub issue（bug label），body 含 testcases + 证据 | `{repo}#M` |
| 4 | Agent | 回填 eval-doc 的 `github_issue` 字段 | 更新文件 |
| 5 | Agent | 写 issue-ref 索引 | `.artifacts/issues/issue-{finding}-{seq}.md` |
| 6 | Agent | 在 parent issue comment 贴 Phase 7 总结 + pipeline 状态表 | issue comment |
| 7 | 人类 | 补充复现细节 / 截图 / 优先级意见 | issue comment |

### 引导人类描述问题（5 问法）
当人类主动报告 bug 时，Agent 按顺序追问：
1. **你做了什么操作？**（具体步骤）
2. **你期望看到什么？**（预期行为）
3. **实际发生了什么？**（实际行为）
4. **每次都会出现吗？**（复现性）
5. **有截图或日志吗？**（证据）

### 分流建议类型

| 类型 | 含义 | 何时用 |
|------|------|--------|
| 疑似 bug | 行为明确违反预期（崩溃/数据丢失/错误输出） | 有 traceback 或明确的预期 vs 实际差异 |
| 疑似不合理 | 技术上正确但体验差 | 流程繁琐/提示不清/性能差 |
| 需要讨论 | 无法判断是 bug 还是设计意图 | 信息不足或涉及产品决策 |

### 出口条件
- eval-doc (verify) 已写入
- GitHub issue 已创建
- issue-ref 已写入
- parent issue comment 已更新
- Agent 已 `git add + commit` eval-doc + issue-ref（commit message: `artifact: add eval-{finding}-{seq} + issue #{N}`）

### 异常回退

| 情况 | 处理 |
|------|------|
| 人类无法提供证据 | eval-doc 证据区标"待补充"，issue 标 `needs-info`，不阻断创建 |
| 发现的问题其实是已知行为 | eval-doc 中说明"已确认为设计意图"，不开 issue |
| 问题涉及多个模块 | 一个 eval-doc 覆盖所有，但可拆多个 issue |

---

## 异常回退总结

```
Phase 5 regression FAIL
  ├── 根因是代码 → 修代码 → 重跑 Phase 5
  ├── 根因是环境 → Phase 7 开 issue → 修环境 → 重跑 Phase 5
  └── 根因不明 → 隔离 rerun 单个文件 → 缩小范围

Phase 5 new-case FAIL（非红灯预期）
  └── 修代码 → 重跑 Phase 5

Phase 3 review 不通过
  └── Agent 修改 plan → 重新 review

Phase 1 需求变更
  └── 更新 eval-doc → 如已到 Phase 3+，评估影响范围 → 必要时重走 Phase 3-5
```

**核心原则**：回退时更新 artifact 的 `updated_at`，在 issue comment 记录回退原因，不删除历史产物。
