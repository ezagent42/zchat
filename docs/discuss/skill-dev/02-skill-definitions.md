# 02-Skill定义

> 7个skill的功能、部件和命名。每个skill是一个独立的Claude Code skill，包含SKILL.md和配套脚本。

## Skill总览

| 编号 | 命名 | 一句话定位 | 使用阶段 |
|------|------|-----------|---------|
| Skill 0 | `project-builder` | Pipeline bootstrapper，将代码仓库转化为可运转的开发闭环 | Phase 0 |
| Skill 1 | `project-discussion` | 项目知识问答，有实证支撑，可分发 | Phase 2（及全流程） |
| Skill 2 | `test-plan-generator` | 根据改动和覆盖生成测试计划 | Phase 3 |
| Skill 3 | `test-code-writer` | 往E2E套件追加测试用例 | Phase 4 |
| Skill 4 | `test-runner` | 执行完整E2E套件，生成report | Phase 5 |
| Skill 5 | `feature-eval` | 预期vs实际对比，双模式（模拟/验证） | Phase 1, Phase 7 |
| Skill 6 | `artifact-registry` | 统一artifact空间管理 | 全流程 |

---

## Skill 0: project-builder

> 整个pipeline的bootstrapper。将一个60%+的代码仓库转化为可运转的开发闭环：生成Skill 1、跑初始测试、建立artifact空间。

### 功能

- 强制通读项目所有源代码文件，不允许跳过或采样
- 识别项目使用的语言、框架、测试工具链、目录约定
- **环境检查与配置**：运行测试前，检查所有依赖是否就绪（运行时、外部服务、端口、工具链），缺失的依赖尝试自动安装/配置，无法自动解决的明确列出并标记哪些测试会因此跳过
- 按模块分块调用已有测试，记录每个模块的实际运行结果
- 因环境缺失而跳过的测试，在结果中明确标注原因（如"跳过: 需要ergo服务"），不算通过也不算失败
- 建立索引结构：模块 → 文件位置 → 对应用户流程 → 对应测试脚本 → 覆盖状态
- 识别项目的测试pipeline格式（pytest/agent-browser/playwright等），提取pattern供Skill 3复用
- 运行已有的全部测试，生成初始基线结果
- 分析覆盖情况，生成初始`coverage-matrix`，区分：
  - 代码测试覆盖（单元/集成/API）
  - 操作E2E覆盖（符合pipeline标准的，冷启动时通常大面积空白）
  - 环境受限覆盖（测试存在但因环境缺失无法运行）
- 初始化`.artifacts/`目录结构（如有Skill 6则同时初始化registry.json）
- 将初始coverage-matrix注册到artifact空间
- 最终输出Skill 1

### 部件

```
project-builder/
├── SKILL.md                    # 完整的bootstrap流程指导
├── env-check.sh                # 检查运行环境：语言版本、包管理器、外部服务、端口占用、工具链
├── env-setup.sh                # 尝试自动配置环境：安装缺失依赖、启动所需服务
├── scan-modules.sh             # 遍历源代码目录，输出模块清单
├── run-tests-by-module.sh      # 按模块分别运行测试，收集结果（跳过环境不满足的测试并标注原因）
├── run-full-tests.sh           # 运行已有的全部测试，输出基线结果
├── generate-coverage-matrix.sh # 基于测试结果和代码分析，生成覆盖矩阵（含环境受限标注）
├── init-artifact-space.sh      # 创建.artifacts/目录（如有Skill 6则初始化registry）
├── generate-index.sh           # 汇总扫描和测试结果，生成索引文档
├── generate-skill1.sh          # 将索引+测试脚本+SKILL.md模板打包为Skill 1
├── self-test.sh                 # 一键验证所有脚本正常工作
└── templates/
    └── skill1-skeleton.md      # Skill 1的SKILL.md骨架，含占位符
```

---

## Skill 1: project-discussion

> 项目知识问答skill。被分发给新人/新session，提供有实证支撑的项目知识服务。这是Skill 0的产出物。

### 功能

- 维护索引：模块 → 文件 → 用户流程 → 测试脚本的映射关系
- 包含大量bash脚本，能规范化执行对应模块的测试
- **问答**：被问到问题时，解析问题 → 定位索引中的对应模块 → 找到代码段 → 跑对应测试 → 给出答案+测试输出作为证据
- **Phase 8 分流讨论**：人带着 issue 讨论时，Skill 1 查代码+跑测试+查已有知识，提供实证分析帮助判断是否 bug
- **操作 issue**：Phase 8 结论为"不是 bug"时，关闭 GitHub issue（附结论说明）
- **操作 artifact**：更新 eval-doc 状态（archived + rejection_reason）、注册/查询 artifact（通过 Skill 6 或直接 .artifacts/）
- 自我演进：新结论作为 artifact 管理（eval-doc archived），不嵌入 SKILL.md。下次查询时自动获取最新知识
- 可被分发给新人/新session直接使用（SKILL.md 轻量行为引擎，数据在 .artifacts/ 中随项目仓库走）
- 提供项目测试pipeline格式信息，供Skill 3查询

### 部件

```
project-discussion/
├── SKILL.md                    # 行为引擎：问答流程 + 分流讨论协议 + artifact交互 + pipeline信息
├── scripts/
│   ├── test-auth.sh            # 模块 test-runner（按项目实际模块生成）
│   ├── test-agent-lifecycle.sh
│   ├── test-xxx.sh
│   ├── close-issue.sh          # 关闭 GitHub issue（附结论说明）
│   └── ...
└── self-test.sh                # 一键验证所有脚本正常工作
```

**注意**：Skill 1 的 SKILL.md 是轻量行为引擎——指导如何查询和操作，不嵌入大量数据。模块索引、FAQ/已知边界等数据通过引用 `.artifacts/` 路径获取。

**注意**：这个skill的具体内容由Skill 0针对每个项目生成，上面的目录是结构规范，实际文件名和内容因项目而异。

---

## Skill 2: test-plan-generator

> 根据代码改动和已有覆盖，生成结构化的测试计划。

### 功能

- 从registry读取：code-diff、coverage-matrix、eval-doc中的testcase、历史issue
- 对比改动范围与已有E2E覆盖，识别需要新增的场景
- 将来自不同来源的测试需求统一为同一种用例格式
- 标注每个用例的来源（PRD / code-diff / bug-feedback）和优先级
- 输出结构化summary，供人review

### 部件

```
test-plan-generator/
├── SKILL.md                    # 测试计划生成流程 + 用例格式规范
├── templates/
│   ├── test-case.md            # 统一用例格式模板
│   │                             字段：场景 / 前置条件 / 操作步骤 / 预期结果 / 优先级 / 来源
│   └── plan-summary.md         # 输出格式（用例列表 + 统计 + 风险标注）
├── diff-analysis-guide.md      # 如何从code-diff提取影响范围
├── coverage-gap-guide.md       # 如何对比改动与已有矩阵找缺口
└── self-test.sh                # 一键验证所有脚本正常工作
```

---

## Skill 3: test-code-writer

> 将确认的测试计划转化为E2E测试用例，追加到项目已有的E2E测试套件中。

### 功能

- 从registry读取confirmed test-plan
- 从Skill 1获取项目的测试pipeline格式（框架、fixture模式、目录结构、命名规范）
- 在项目已有E2E测试目录中追加新case，复用已有fixture和helper
- 不创建独立的测试包——新case是项目测试套件的永久组成部分
- 如需新fixture或helper，追加到已有的conftest/shared目录中
- 追加配套测试数据到已有配置中（不覆盖）
- 适配不同项目类型：
  - 终端应用：pytest + Zellij helpers + IrcProbe
  - Web应用：agent-browser + 多session + 截图

### 部件

```
test-code-writer/
├── SKILL.md                    # 测试代码编写规范 + 追加用例流程 + 适配指导
├── patterns/
│   ├── pytest-pattern.md       # 如何在已有conftest中添加fixture
│   │                             如何在已有test文件中追加case
│   │                             何时新建test文件
│   └── agent-browser-pattern.md # 如何复用已有session配置
│                                  截图规范、Web操作模式
├── append-rules.md             # 什么情况下在已有文件追加
│                                 什么情况下新建文件
│                                 如何避免与已有case冲突
├── naming-convention.md        # 文件命名、函数命名、目录归属规则
└── self-test.sh                # 一键验证所有脚本正常工作
```

---

## Skill 4: test-runner

> 执行项目完整E2E测试套件，生成区分新增和回归的结构化report。

### 功能

- 执行项目的完整E2E测试套件（不只是新增case，包括所有已有case）
- 区分"新增case"和"回归case"的结果，分别统计
- 关键验证节点采集证据：
  - Web应用：agent-browser截图
  - 终端应用：Zellij capture_pane / asciinema录制
  - API：response body保存
- 失败时自动收集上下文（日志片段、进程状态、环境信息）
- 回归case失败 = 新功能break了已有功能，需要特别标注
- 生成结构化E2E report

### 部件

```
test-runner/
├── SKILL.md                    # 测试执行流程 + 证据采集规范 + report格式要求
├── run-e2e.sh                  # 统一入口脚本
├── evidence-rules.md           # 证据采集规范
│                                 截图命名规则：{date}-{test-id}-{step}.png
│                                 截图内容要求：必须能独立证明测试结果
│                                 terminal capture格式
├── templates/
│   └── e2e-report.md           # report模板
│                                 基本信息（日期 / 分支 / 触发原因）
│                                 测试结果汇总表（分新增和回归两部分）
│                                 回归失败高亮标注
│                                 每个用例详细结果（步骤/预期/实际/证据引用）
│                                 新发现的问题列表
├── env-check.sh                # 执行前验证依赖是否就绪
└── self-test.sh                # 一键验证所有脚本正常工作
```

---

## Skill 5: feature-eval

> 统一的"预期 vs 实际"对比工具，服务于需求提出和问题反馈两个场景。

### 功能

**模拟模式**（Phase 1 — 产品提需求时使用）：
- 产品描述feature想法
- AI模拟"如果实现了，各testcase的效果是什么"
- 输出对比文档：testcase表格（场景 / 预期效果 / 模拟实际效果）
- 文档交给研发，作为开发目标和后续验证标准

**验证模式**（Phase 7 — 人发现问题时使用）：
- 引导人描述问题：操作步骤 → 预期效果 → 实际效果
- 要求附上证据（截图 / 录屏 / 日志）
- 输出格式化eval-doc
- 自动在GitHub创建issue + 指定watcher
- 标注分流建议：疑似bug / 疑似不合理 / 需要讨论

### 部件

```
feature-eval/
├── SKILL.md                    # 两种模式的使用流程 + 文档格式规范
├── templates/
│   └── eval-doc.md             # eval文档模板
│                                 头部：feature名称 / 提交人 / 日期 / 模式（模拟/验证）
│                                 testcase表格：场景 / 前置条件 / 操作步骤 /
│                                   预期效果 / 实际效果（或模拟效果）/ 差异描述 / 优先级
│                                 证据区：截图/日志引用
│                                 分流建议区
├── create-issue.sh             # 根据eval-doc自动创建GitHub issue
├── add-watcher.sh              # 为issue添加watcher
├── feedback-guide.md           # step-by-step引导非技术人员描述问题的prompt模板
└── self-test.sh                # 一键验证所有脚本正常工作
```

---

## Skill 6: artifact-registry

> 统一的artifact空间管理，维护所有中间产物的索引和交叉引用。

### 功能

- 注册：每个skill产出artifact后，向registry注册（名称、类型、路径、产出者、时间戳）
- 查询：其他skill通过registry找到需要的输入artifact
- 交叉引用：issue ↔ eval-doc ↔ test-plan ↔ test-diff ↔ e2e-report的关联关系
- 状态追踪：每个artifact的生命周期状态（draft / confirmed / executed / archived）
- 全局视图：当前有哪些待确认的test-plan、未处理的issue、最新的e2e-report

### Artifact类型定义

| 类型 | 说明 | 产出者 | 消费者 |
|------|------|--------|--------|
| `eval-doc` | 预期vs实际对比文档 | Skill 5 | Skill 2 |
| `code-diff` | 代码改动摘要 | Phase 2开发 | Skill 2 |
| `test-plan` | 测试计划（draft → confirmed） | Skill 2 | Skill 3 |
| `test-diff` | 本次追加的E2E用例清单+diff | Skill 3 | Skill 4 |
| `e2e-report` | 测试报告（新增+回归） | Skill 4 | 人 / Skill 2 |
| `issue` | GitHub issue引用 | Skill 5 | Skill 2 / Skill 1 |
| `coverage-matrix` | 覆盖矩阵（持续更新） | Skill 0 / Skill 4 | Skill 2 |

### 部件

```
artifact-registry/
├── SKILL.md                    # registry使用规范 + 其他skill如何读写
├── schema/
│   └── registry-schema.json    # artifact索引字段定义
│                                 id / name / type / status / producer /
│                                 consumers / path / created_at / updated_at / related_ids
├── register.sh                 # 注册新artifact
├── query.sh                    # 按类型/状态/关联查询artifact
├── update-status.sh            # 更新artifact状态
├── link.sh                     # 建立artifact间的关联关系
├── directory-structure.md      # 统一存放路径规范
└── self-test.sh                # 一键验证所有脚本正常工作
                                  .artifacts/
                                  ├── registry.json
                                  ├── eval-docs/
                                  ├── test-plans/
                                  ├── test-diffs/
                                  ├── e2e-reports/
                                  ├── issues/
                                  └── coverage/
```
