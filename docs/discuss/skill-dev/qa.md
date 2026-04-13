# Skill 套件开发 QA

> 基于 01~04 四份文档的理解确认和待澄清问题。

## 理解确认 ✅

### 整体定位
- 这是一个 **通用的** 开发闭环 skill 包，不仅用于 zchat，可以接入任何 60%+ 的项目
- zchat 是第一个接入项目，但 Skill 0/2/3/4/5/6 是跨项目复用的
- 唯一项目特定的是 Skill 1，由 Skill 0 动态生成

### 核心约束
- E2E 测试 = **必须通过 UI/终端实际操作**，API 测试和单元测试不算
- E2E 证据 = **截图 / terminal capture / asciinema 录制**，不是 assert 通过就行
- E2E 套件 **只增不减** — 每次 bug 修复都追加 case
- 每次跑 **完整套件**，不只跑新增的

### Skill 间协作
- Skill 之间 **不自动串联** — 人控制何时触发下一个 skill
- Skill 之间通过 `.artifacts/` 目录的 artifact 文件交换数据
- Artifact 格式统一为 **markdown + YAML front matter**

### 开发标准
- 必须用 `/skill-creator` skill 创建，不手动写 SKILL.md
- 每个 skill 有 `self-test.sh`，所有脚本支持 `--dry-run`
- 三层验证：脚本自测 → skill-creator eval → 跨 skill 集成验证

---

## 已澄清问题

### Q1: Skill 安装位置
**答：`.claude/skills/` 目录**。遵循 `/skill-creator` 标准。后续可配置为 plugin 分发。

### Q2: Skill 0 的触发方式
**答：都可以**。遵循 skill-creator 和 Claude Code 使用 skill 的标准方式（slash command 或自然语言触发均可）。

### Q3: Skill 1 的分发机制
**答：文件夹直接复制到 `.claude/skills/` 下即可使用。** 最简分发方式。

### Q4: 证据采集的实现
**答：**
- 终端应用：`zellij capture_pane` + `asciinema`
- Web 应用：`agent-browser` 是一个已有的 skill，如果没有需要去寻找并下载安装
- 截图统一存储在 `.artifacts/` 中，**目录路径只需能区分是哪一次测试即可**（如按日期+test-id）

### Q5: Skill 6 优先级
**答：先做 Skill 6。** 定好 `.artifacts/` 目录结构，然后再开发其他 skill。但其他 skill 是解耦的——没有 Skill 6 时，artifact 放在 skill 默认路径中也能工作。

### Q6: zchat 作为第一个项目的特殊处理
**答：复用已有基础设施。** Skill 0 的作用是完整扫描项目 → 跑全部测试 → 留存证据证明可用。这样生成的 Skill 1 是准确的，别人拿到就能用。现有的 `test_e2e.py`、`IrcProbe`、`zellij_helpers` 都是 Skill 0 需要识别和纳入的资产。

### Q7: coverage-matrix 的粒度
**答：细粒度，完整覆盖。** 操作级别（如"在 WeeChat 输入 @agent 消息并收到回复"），不是功能级别。

### Q8: 与已有 superpowers skill 的关系
**答：完全独立。** 可以同时使用，互不干扰。

### Q9: 人工介入点
**答：Phase 4-5（写测试+跑测试）全自动。** Phase 2（开发）不在这个 skill 包的范围内——skill 包管的是测试闭环，不管开发过程本身。

人工介入点确认：
1. Phase 1: 产品描述需求 ✅
2. Phase 3: 人确认 test-plan ✅
3. Phase 6: 人使用产品 ✅
4. Phase 7: 人描述问题 ✅（Skill 5 自动创建 issue + eval-doc）
5. Phase 8: 人 + Skill 1 讨论分流 ✅（Skill 1 提供实证，人拍板）

### Q10: 开发顺序
**答：按文档建议的顺序做。** Skill 6 → Skill 0 → Skill 2 → Skill 3 → Skill 4 → Skill 5。

---

## Git 集成策略

### Q11: `.artifacts/` 入 git 吗？
**答：是，全部入 git。** 包括 draft 状态的 artifact。通过文件命名区分（日期+id+状态）。

### Q12: 证据文件（截图/capture）存储
**答：图片/截图用 git-lfs，其余 markdown artifact 直接入 git。** git-lfs 是 Git Large File Storage，把大二进制文件（PNG/GIF/cast）存在单独存储里，git 仓库只保留指针。需要在项目中配置 `.gitattributes` 追踪 `*.png`、`*.gif`、`*.cast` 等。

### Q13: Git commit 时机
**答：每生成新 artifact 时提交。** 即：
- Skill 5 产出 eval-doc → commit
- Skill 2 产出 test-plan → commit
- Skill 3 产出 test-diff + E2E 代码 → commit
- Skill 4 产出 e2e-report + 证据 → commit
- Phase 2 代码改动 → 正常开发 commit

### Q14: GitHub Issue 创建时机（已修正）
**答：Phase 7 问题反馈 → 自动创建 issue（不需要人确认）。** Phase 1 需求模拟 → 只创建 eval-doc，不创建 issue。

详细流程：
- **Phase 7（用户发现问题）**：Skill 5 verify mode 自动创建 eval-doc + issue + 配置 watcher → 都注册到 .artifacts/
- **Phase 8（分流）**：人 + Skill 1 讨论，Skill 1 提供代码证据和测试结果，人拍板：
  - **确认是 bug** → issue 保持 open → eval-doc 进入 Phase 3（Skill 2 生成 test-plan）
  - **不是 bug** → issue 关闭 → eval-doc 状态更新为 archived + rejection_reason
- **Phase 1（产品提需求）**：Skill 5 simulate mode 只产出 eval-doc，不创建 issue
- 所有状态变更通过 Skill 6（或直接 .artifacts/）+ git commit 追踪

### Q15: Phase 8 的执行方式
**答：Phase 8 = 人 + Skill 1 讨论得出结论。** 不是人单独判断。Skill 1 查代码、跑测试、查 .artifacts/ 中已有知识，提供实证分析。人根据 Skill 1 的分析拍板。结论通过 artifact 状态更新 + git commit 自动流转。

---

## 开发就绪状态

理解已完整，可以开始开发。执行计划：

1. **Skill 6** (artifact-registry) — 定义 `.artifacts/` 目录结构、registry.json schema、CRUD 脚本
2. **Skill 0** (project-builder) — bootstrap 流程，以 zchat 为第一个项目验证
3. **Skill 2** (test-plan-generator) — 从 code-diff + coverage-matrix 生成测试计划
4. **Skill 3** (test-code-writer) — 追加 E2E case 到项目测试套件
5. **Skill 4** (test-runner) — 跑完整套件，采集证据，生成 report
6. **Skill 5** (feature-eval) — 需求模拟 + 问题反馈双模式

每个 skill 开发时使用 `/skill-creator` skill 创建。
