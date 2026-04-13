# 01-开发流程

> AI驱动的开发闭环流程规范。适用于已完成60%+的项目的持续开发和质量保障。

## 流程概览

```
Phase 0 (bootstrap) → Phase 1 (需求) → Phase 2 (开发) → Phase 3 (测试计划)
    → Phase 4 (编写E2E) → Phase 5 (执行E2E) → Phase 6 (部署+使用)
    → Phase 7 (反馈) → Phase 8 (分流) → 回到 Phase 2 或 Phase 3
```

## 核心原则

1. **E2E测试 = 操作导向测试**：必须通过UI/终端实际操作，必须截图/capture作为证据，必须对应用户流程。API集成测试、单元测试不算E2E。
2. **E2E测试套件持续增长**：每轮循环追加新case到项目仓库，不创建独立测试包。
3. **每次跑完整套件**：确保新功能不break已有功能。
4. **Skill之间通过artifact解耦**：每个skill产出固定格式的artifact，下一个skill消费。不自动串联调用。
5. **所有artifact通过registry管理**：统一索引、交叉引用、状态追踪。

---

## Phase 0: 项目接入（一次性 bootstrap）

**触发**：接手一个新项目（代码已完成60%+）

**执行者**：人启动 → Claude执行

**使用skill**：Skill 0 (project-builder)

**过程**：
1. 人提供项目文档、代码仓库地址
2. Claude强制通读所有源代码
3. 识别项目结构、模块划分、测试框架和pipeline格式
4. **检查运行环境**：依赖是否齐全、外部服务是否在线、端口是否可用。缺失的尝试自动配置，无法解决的明确标注
5. 运行已有的全部测试（包括单元测试、集成测试等），记录结果作为基线。因环境缺失跳过的测试标注原因
6. 分析覆盖情况，生成初始`coverage-matrix`，区分三层：
   - **代码测试覆盖**：已有的单元/集成/API测试覆盖了哪些模块
   - **操作E2E覆盖**：符合pipeline E2E标准的测试覆盖了哪些用户流程（冷启动时通常大面积空白）
   - **环境受限覆盖**：测试存在但因环境缺失无法运行
7. 建立结构化索引 + 配套测试脚本，输出Skill 1
8. 初始化`.artifacts/`目录（如有Skill 6则同时初始化registry）
9. 将初始coverage-matrix注册到artifact空间

**产出**：
- Skill 1（安装到Claude Code skill系统，可分发）
- `.artifacts/`空间就绪，含初始coverage-matrix
- coverage-matrix中的"操作E2E未覆盖"区域 = Skill 2的第一批输入

**注意**：初始coverage-matrix中操作E2E大概率大面积空白，这是正常的。pipeline的第一轮循环就是补这些操作E2E。

---

## Phase 1: 需求输入

**触发**：产品经理有新feature想法，或用户反馈了问题

**执行者**：人操作，Claude辅助

**使用skill**：Skill 5 (feature-eval，模拟模式)

**过程**：
1. 产品描述feature想法
2. AI模拟"如果实现了，各testcase的效果是什么"
3. 产品填写testcase表格：场景 / 预期效果 / 模拟实际效果

**产出artifact**：`eval-doc` → 注册到registry

---

## Phase 2: 开发

**触发**：有了eval-doc或直接的开发任务

**执行者**：Claude执行

**使用skill**：Skill 1 (project-discussion，提供项目上下文)

**过程**：
1. Claude加载Skill 1，获取项目上下文
2. 通过索引定位需要改动的模块
3. 开发新功能

**产出artifact**：`code-diff`（代码改动摘要）→ 注册到registry

---

## Phase 3: 测试计划

**触发**：开发完成

**执行者**：Claude生成 → 人确认

**使用skill**：Skill 2 (test-plan-generator)

**过程**：
1. Skill 2从registry读取：code-diff、已有coverage-matrix、eval-doc中的testcase、历史issue
2. 对比改动范围与已有E2E覆盖，识别需要新增的测试场景
3. 输出测试计划summary
4. 人review并确认

**产出artifact**：`test-plan`（status: confirmed）→ 注册到registry

---

## Phase 4: 编写E2E测试

**触发**：测试计划已确认

**执行者**：Claude执行

**使用skill**：Skill 3 (test-code-writer)

**过程**：
1. Skill 3从registry读取confirmed test-plan
2. 从Skill 1获取项目的测试pipeline格式
3. 在项目已有的E2E测试套件中追加新case，复用已有fixture和helper
4. 如需新fixture或helper，追加到已有的conftest/shared目录中

**产出artifact**：`test-diff`（本次追加的E2E用例清单 + 代码diff）→ 注册到registry

**实际代码**：新case直接写入项目仓库的E2E测试目录，成为套件的永久组成部分

---

## Phase 5: 执行E2E测试

**触发**：新E2E case已写入套件

**执行者**：Claude执行

**使用skill**：Skill 4 (test-runner)

**过程**：
1. Skill 4执行项目的完整E2E测试套件（不只是新增的case）
2. 关键节点采集证据（截图 / terminal capture / API response）
3. 生成结构化report，区分"新增case结果"和"回归case结果"

**产出artifact**：`e2e-report`（新增pass/fail + 回归pass/fail + 证据引用）→ 注册到registry

**分支**：
- 全部通过 → 进入Phase 6
- 有失败 → 回到Phase 2修复，再走Phase 3-5

---

## Phase 6: 部署 + 人使用

**触发**：E2E全部通过

**执行者**：部署自动化 → 人使用产品

**过程**：
1. 部署上线
2. 人（产品/测试/用户）实际使用

**分支**：
- 没问题 → 本轮结束
- 发现问题 → 进入Phase 7

---

## Phase 7: 反馈

**触发**：人在使用中发现问题

**执行者**：人操作，Claude辅助

**使用skill**：Skill 5 (feature-eval，验证模式)

**过程**：
1. Skill 5引导人填写：场景 / 预期效果 / 实际效果 / 截图证据
2. 输出格式化eval-doc
3. 自动在GitHub开issue + 指定watcher

**产出artifact**：`eval-doc` + `issue` → 注册到registry

---

## Phase 8: 分流

**触发**：issue产生（Phase 7 自动创建）

**执行者**：人 + Skill 1 讨论

**过程**：
1. 人带着 issue 和 eval-doc 与 Skill 1 讨论
2. Skill 1 查代码（定位模块 → 读源码 → 引用 file:line）
3. Skill 1 跑相关测试（test-runner），提供实证
4. Skill 1 查 .artifacts/ 中已有的类似 issue / 被驳回记录
5. 人根据 Skill 1 的实证分析，做出判断

**分支A — Bug确认**：
- issue 保持 open
- eval-doc作为新输入 → 进入Phase 3（生成新的test-plan，覆盖这个bug场景）
- 修复 → 走Phase 2-5
- 最终这个场景永久存在于E2E套件中，保证不会回归

**分支B — 不是bug / 不合理**：
- Skill 1 关闭 issue（附结论说明）
- eval-doc 状态更新为 archived + rejection_reason
- 所有变更通过 Skill 6（或直接 .artifacts/）+ git commit 追踪
- 下次遇到同类问题时，Skill 1 查到 archived eval-doc，直接引用驳回记录

---

## Artifact流转总览

```
Phase 0: Skill 0 → coverage-matrix (初始，操作E2E大面积空白)
                  → Skill 1 (安装到skill系统)
                  → .artifacts/ 空间就绪

Phase 1: Skill 5 (simulate) → eval-doc

Phase 2: Skill 1 (context) + Claude → code-diff

Phase 3: Skill 2 ← (code-diff + coverage-matrix + eval-doc + issues)
                  → test-plan → Human confirms

Phase 4: Skill 3 ← confirmed test-plan
                  → test-diff (追加到E2E套件)

Phase 5: Skill 4 (跑完整套件) → e2e-report

Phase 7: Skill 5 (verify) → eval-doc + issue

Phase 8: Skill 1 (讨论分流) + 人拍板
         Bug → issue保持open → 回到Phase 3 (case永久加入套件)
         Not bug → Skill 1关闭issue + eval-doc archived + rejection_reason
```

所有artifact通过Skill 6 (artifact-registry) 管理索引和交叉引用。
