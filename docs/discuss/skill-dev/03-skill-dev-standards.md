# 03-Skill开发规范

> 7个skill的开发标准、依赖关系、打包方式。给到Claude Code执行时需遵循的规范。

## 开发工具要求

### 必须使用 /skill-creator skill

所有skill的创建必须通过Claude Code的`/skill-creator` skill进行。不允许手动创建SKILL.md。

**流程**：
1. 加载 `/skill-creator` skill
2. 提供skill的需求描述（参考02-skill-definitions.md中的对应章节）
3. skill-creator引导讨论 → 明确需求 → 生成SKILL.md + 配套文件
4. 使用skill-creator的eval功能验证skill质量

### Skill质量验证

每个skill创建后，必须通过三层验证：

**第一层：脚本自测**
- 每个skill目录下必须有`self-test.sh`，一键验证所有配套脚本能正常运行
- 每个`.sh`脚本必须支持`--dry-run`模式，验证逻辑正确但不产生副作用
- `self-test.sh`内容：依次调用每个脚本的`--dry-run`或用mock数据跑一遍，全部返回0才通过
- skill交付前必须运行`self-test.sh`且全部通过

**第二层：skill-creator eval**
- 使用skill-creator的eval功能验证：
- **触发准确性**：给出10个prompt，验证skill是否在该触发时正确触发、不该触发时不触发
- **输出格式**：验证产出的artifact是否符合schema

**第三层：集成验证**
- **跨skill兼容**：验证产出的artifact能否被下游skill正确消费
- 至少用一个真实场景跑通上下游链路（如Skill 2产出test-plan → Skill 3能消费）

---

## Skill包结构

### 7个skill作为一个skill包

这7个skill构成一个完整的开发闭环，应作为一个skill包（skill pack）管理：

```
dev-loop-skills/                        # 包根目录（参考 superpowers plugin 结构）
├── README.md                           # 包说明：7个skill的关系、使用流程
├── package.json                        # plugin 元数据（转 plugin 时添加）
└── skills/                             # 所有 skill 放在 skills/ 子目录下
    ├── skill-0-project-builder/
    │   ├── SKILL.md
    │   └── ...
    ├── skill-1-project-discussion/     # 注意：这是模板/骨架，实际内容由Skill 0生成
    │   ├── SKILL.md.template
    │   └── ...
    ├── skill-2-test-plan-generator/
    │   ├── SKILL.md
    │   └── ...
    ├── skill-3-test-code-writer/
    │   ├── SKILL.md
    │   └── ...
    ├── skill-4-test-runner/
    │   ├── SKILL.md
    │   └── ...
    ├── skill-5-feature-eval/
    │   ├── SKILL.md
    │   └── ...
    └── skill-6-artifact-registry/
        ├── SKILL.md
        └── ...
```

### 本地开发与测试

开发时包放在 `~/.claude/skills/dev-loop-skills/`。由于 Claude Code 本地 skill 扫描深度为 1（`~/.claude/skills/<name>/SKILL.md`），需要为每个 skill 创建 symlink：

```bash
# 本地测试安装
ln -s ~/.claude/skills/dev-loop-skills/skills/skill-6-artifact-registry \
      ~/.claude/skills/artifact-registry
```

转 plugin 后通过 plugin 系统自动发现 `skills/` 下的所有 skill，无需 symlink。

### 安装方式

作为skill包整体安装，不需要特定顺序。所有7个skill一次性安装到Claude Code。

Skill 1是特殊情况：skill包中只包含模板/骨架，实际内容由Skill 0在Phase 0针对具体项目生成。

---

## Skill间依赖关系

```
Skill 0 (builder) → 生成 Skill 1 + 初始化artifact空间

Skill 1 (discussion) ← Skill 3 读取项目pipeline格式
                     ← Phase 2 开发时加载上下文
                     ← Phase 8 分流讨论（查代码+跑测试+查已有知识，提供实证）
                     → 操作 issue（Phase 8 结论为"不是bug"时关闭）
                     → 操作 artifact（更新 eval-doc 状态为 archived + rejection_reason）

Skill 2 (test-plan) ← 消费 eval-doc, code-diff, coverage-matrix, issue
                     → 产出 test-plan

Skill 3 (test-code) ← 消费 test-plan
                     → 产出 test-diff（追加到项目E2E套件）

Skill 4 (test-runner) → 产出 e2e-report
                       → 更新 coverage-matrix

Skill 5 (feature-eval) → 产出 eval-doc, issue

Skill 6 (registry) ← 可选增强，不是硬依赖
```

### Skill 6的可选性

Skill 6（artifact-registry）是增强组件，不是前置依赖。当Skill 6存在时，各skill通过它进行索引、交叉引用和状态追踪。当Skill 6不存在时，各skill直接往约定的默认目录（`.artifacts/`）读写，使用固定的目录结构和文件命名约定：

```
.artifacts/
├── eval-docs/          # Skill 5 读写
├── code-diffs/         # Phase 2 写，Skill 2 读
├── test-plans/         # Skill 2 写，Skill 3 读
├── test-diffs/         # Skill 3 写，Skill 4 读
├── e2e-reports/        # Skill 4 写
├── issues/             # Skill 5 写
└── coverage/           # Skill 0/4 写，Skill 2 读
```

有了Skill 6：多了索引（快速查询）、交叉引用（追溯链条）、状态追踪（draft/confirmed/archived）。没有Skill 6：靠目录约定和文件命名，功能完整但管理能力弱一些。

### 依赖类型说明

| 依赖类型 | 说明 | 示例 |
|----------|------|------|
| **artifact依赖** | 一个skill需要消费另一个skill产出的artifact | Skill 3 ← test-plan（来自Skill 2） |
| **知识依赖** | 一个skill需要查询另一个skill的内容 | Skill 3 → Skill 1（查pipeline格式） |
| **生成依赖** | 一个skill的产出是另一个skill本身 | Skill 0 → Skill 1 |
| **可选增强** | 有了更好，没有也能工作 | 所有skill ↔ Skill 6 |

---

## SKILL.md编写规范

### 必须包含的章节

每个SKILL.md必须包含以下章节：

```markdown
# Skill名称

> 一句话定位

## 触发条件
- 什么prompt/场景下触发这个skill
- 什么情况下不应该触发

## 输入
- 从registry读取的artifact类型和字段
- 从其他skill查询的信息
- 人提供的输入

## 执行流程
- 分步骤描述skill做什么
- 每步的输入输出
- 分支条件

## 输出
- 产出的artifact类型和格式
- 注册到registry的字段
- 给人看的展示格式

## 配套脚本说明
- 每个.sh脚本的用途和参数
```

### 脚本规范

- 所有bash脚本必须有`#!/bin/bash`和`set -euo pipefail`
- 脚本必须有usage说明（`--help`参数）
- 脚本必须支持`--dry-run`模式（验证逻辑但不产生副作用）
- 脚本必须处理错误并给出有意义的错误信息
- 脚本的输入输出路径通过参数传入，不硬编码
- 与artifact空间交互时：有Skill 6则调用`register.sh`/`query.sh`，无则直接读写`.artifacts/`目录
- 每个skill必须包含`self-test.sh`，内容为依次调用所有脚本的`--dry-run`模式，全部返回0才算通过

### Artifact格式规范

所有artifact使用markdown格式，头部包含YAML front matter：

```markdown
---
type: eval-doc          # artifact类型
id: eval-001            # 唯一标识
status: draft           # draft / confirmed / executed / archived
producer: skill-5       # 产出者
created_at: 2026-04-09
related:                # 关联的其他artifact
  - test-plan-003
  - issue-012
---

# 文档正文
...
```

---

## Skill 1的特殊性

Skill 1与其他skill不同：

1. **它不是预先写好的**——它的内容由Skill 0针对具体项目生成
2. **skill包中只包含模板/骨架**——`SKILL.md.template`，不是完整的`SKILL.md`
3. **它会自我演进**——在使用过程中，FAQ和已知边界会持续更新
4. **它是可分发的**——其他人/session可以直接使用它，不需要重新bootstrap

因此Skill 0的`generate-skill1.sh`需要：
- 读取`SKILL.md.template`
- 填入项目特定的索引、模块列表、测试脚本
- 输出完整的Skill 1目录，可直接安装到Claude Code

---

## 开发顺序建议

在具体项目中开发这7个skill时，建议按以下顺序：

### 第一轮：基础设施
1. **Skill 6**（artifact-registry）：先把artifact空间建好
2. **Skill 0**（project-builder）：能bootstrap项目，生成Skill 1

### 第二轮：E2E核心链路
3. **Skill 2**（test-plan-generator）
4. **Skill 3**（test-code-writer）
5. **Skill 4**（test-runner）

验证：Skill 2→3→4能跑通一个完整的"生成计划→写测试→跑测试"循环

### 第三轮：闭环
6. **Skill 5**（feature-eval）

验证：Skill 5的输出能被Skill 2消费，闭环跑通

---

## 跨项目复用

- **Skill 0, 2, 3, 4, 5, 6**是通用的，跨项目复用
- **Skill 1**是项目特定的，由Skill 0针对每个项目生成
- 不同项目类型（终端/Web/API）的差异在Skill 3和Skill 4中通过pattern适配处理

当接入一个新项目时，只需要：
1. 安装skill包（如果还没装）
2. 运行Skill 0进行bootstrap
3. Skill 0自动生成项目特定的Skill 1
4. 开始使用
