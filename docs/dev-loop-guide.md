# Dev-Loop 开发手册

> 功能开发流水线。所有 feature / bug 修复统一走这个流程。

## 流程总览

```
Phase 1  需求评估  →  eval-doc          ⬅ 你介入：提需求 + 确认评估
Phase 2  编码      →  产品代码          ⬅ 你介入：写代码
Phase 3  测试计划  →  test-plan         ⬅ 你介入：review checklist
Phase 4  写测试    →  测试代码          ⏳ Agent 自动，你不用管
Phase 5  跑测试    →  测试报告          ⬅ 你介入：看报告做决策
Phase 7  归档发现  →  bug issue         ⏳ Agent 自动，你不用管
```

## 你需要做什么

整个流程中，**大部分工作由 Agent 自动完成**。你只在以下节点介入：

### 1. 提需求（Phase 1）

在飞书或 IRC 中用自然语言描述你想要的功能：

> "我想给 zchat 加一个 dm send 命令"

Agent 会自动创建 feature 分支、分析可行性、生成评估文档、创建 GitHub issue。你在 issue 中确认即可。

### 2. 写代码（Phase 2）

在 `feat/{feature-name}` 分支上编写产品代码。可以请 Agent 辅助。

### 3. Review 测试计划（Phase 3）

Agent 会把测试计划发到 GitHub issue comment，包含一个 checklist：

- [ ] 用例是否齐全？
- [ ] 优先级是否合理？
- [ ] 前置条件 / 预期结果是否准确？
- [ ] 是否漏掉回归影响？

全部勾选后 Agent 继续。有意见直接在 comment 里说。

### 4. 看报告、做决策（Phase 5）

Agent 跑完测试后在 issue comment 贴报告摘要。你决定下一步：
- 全绿 → 开 PR 合并
- 新功能红灯 → 继续改代码
- 回归失败 → 优先修回归
- 环境问题 → Agent 单独开 issue 跟踪

### 5. 等 Agent 干活的时候，你可以走开

在以下阶段，**Agent 会独立工作，你不需要在线等待**：

| 阶段 | Agent 在做什么 | 大约耗时 | 什么时候回来 |
|------|---------------|---------|-------------|
| Phase 1 创建分支 + 生成文档 | 分析代码、写评估文档、开 issue | 2-5 分钟 | 收到 issue 链接后打开确认 |
| Phase 3 → Phase 4 写测试 | 根据你确认的计划自动生成测试代码 | 3-5 分钟 | 不用回来，Agent 写完会直接跑测试 |
| Phase 4 → Phase 5 跑测试 | 执行全量 E2E 测试、生成报告 | 5-10 分钟 | Agent 在 issue comment 贴出报告摘要时回来做决策 |
| Phase 7 归档 | 分析根因、开 bug issue、更新状态 | 1-3 分钟 | 不用回来，Agent 会发通知告诉你结果 |

**简单来说**：你勾完 Phase 3 的 checklist 后可以去做别的事，等飞书/IRC 收到 Agent 的测试报告通知再回来做决策。中间 Phase 4 写测试 + Phase 5 跑测试大约 10-15 分钟，全程不需要你。

## 分支规则

- Phase 1 开始时创建 `feat/{feature-name}`
- **所有文件**（代码 + 测试 + artifact）都在 feature 分支上
- 最终通过 PR 合入 `main`，不往 `main` 直接提交

## 产出文件

所有过程文档在 `.artifacts/` 下，按类型分目录：

```
.artifacts/
├── eval-docs/       需求评估文档
├── test-plans/      测试计划
├── test-diffs/      测试代码变更记录
├── e2e-reports/     测试报告（含原始日志）
├── issues/          bug issue 索引
└── registry.json    全局索引
```

测试代码在 `tests/e2e/test_{功能}.py`。

## 沟通渠道

| 内容 | 在哪说 |
|------|--------|
| 快速确认 / 催进度 | 飞书 / IRC |
| Review / 讨论 / 长内容 | GitHub issue comment |
| 代码审查 | PR |

**不要**在聊天里 review 长文档 → 让 Agent 发到 issue comment。

## 关键规则

1. **回归优先**：旧功能被破坏比新功能没做完更严重
2. **证据说话**：每个 PASS/FAIL 都有日志支撑
3. **一个 PR 一件事**：不夹带无关改动
4. **异常不遮掩**：环境问题也要如实报告，单独开 issue

## 异常处理

| 情况 | 怎么做 |
|------|--------|
| 测试计划不满意 | 在 issue comment 说哪里要改，Agent 修改后重新 review |
| 编码中发现需求有问题 | 在 issue comment 讨论，Agent 更新评估文档 |
| 测试全挂 | 先确认是环境问题还是代码问题，环境问题单独开 issue |
| 需求缩减 | 在 issue comment 说明，Agent 更新文档 + skip 对应测试 |

---

## 操作示例：DM 功能全流程

> 以 "zchat dm send" 功能为例，展示完整流程。实际耗时约 40 分钟。

### 前置准备

确保已安装：Git、gh CLI、tmux、zellij、uv、ergo。

连接 Agent：在飞书群聊或 IRC `#general` 频道发消息即可。

### Phase 1：提需求

**你说**："我想给 zchat 加一个 dm send 命令"

**Agent 做**：创建 `feat/dm-support` 分支 → 分析代码 → 生成评估文档 → 创建 GitHub issue #54

**你做**：打开 issue #54，看评估内容，回复 "OK"

### Phase 2：写代码

**你做**：

```bash
git checkout feat/dm-support
# 编写 zchat/cli/app.py 新增 dm send 命令
git add zchat/cli/app.py
git commit -m "add: zchat dm send command"
```

### Phase 3：Review 测试计划

**你说**："写测试计划"

**Agent 做**：在 issue #54 发 comment，列出 7 个测试用例 + checklist

**你做**：在 comment 中勾选 4 项 checklist，回复 "OK"

### ☕ 你可以离开了

勾完 checklist 后，Agent 会自动写测试 + 跑测试，大约 10-15 分钟。去喝杯咖啡，等飞书通知。

### Phase 5 结果：你回来做决策

**Agent 报告**：20 PASS / 13 FAIL（8 条回归是 ergo 中途退出导致，非代码问题）

| 选项 | 何时选 |
|------|--------|
| "开 PR" | 全绿 |
| "继续改代码" | 新功能红灯 |
| "归档发现" | 发现了环境/基础设施问题 |
| "重跑测试" | 怀疑是偶发问题 |

**你说**："归档发现"

### Phase 7：归档（Agent 自动完成）

**Agent 做**：分析回归根因（ergo 稳定性）→ 创建 bug issue #55 → 在 issue #54 贴完整 pipeline 状态

**结果**：DM 功能和 ergo 问题解耦，各有各的 issue 跟踪。你会收到通知，不需要操作。

### 最终产出

```
feat/dm-support 分支：
├── zchat/cli/app.py                          产品代码
├── tests/e2e/test_cli_dm.py                  测试代码
├── .artifacts/eval-docs/eval-dm-support-008.md
├── .artifacts/test-plans/plan-dm-support-009.md
├── .artifacts/test-diffs/test-diff-006.md
├── .artifacts/e2e-reports/report-dm-cli-007/
└── .artifacts/eval-docs/eval-ergo-midrun-stability-009.md

GitHub：
├── issue #54  DM 功能（parent issue，所有讨论在此）
└── issue #55  ergo 稳定性（从 #54 拆出的 bug）
```

---

## Agent 参考文档

以下文档供 Agent 执行时查阅，人类一般不需要看：
- [phases-guide](dev-loop-phases.md) — 各阶段详细操作步骤、入口出口条件
- [templates](dev-loop-templates.md) — artifact 文件格式、命名规则、术语表
