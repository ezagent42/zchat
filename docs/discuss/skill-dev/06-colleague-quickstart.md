# Dev-Loop Skills 同事快速上手指南

## 你会得到什么

一套 AI 驱动的测试开发闭环工具，包含 7 个 Claude Code skill + zchat 项目的知识库。装好后 Claude Code 会自动识别并使用这些 skill。

## 安装步骤

### 1. 克隆 skill 包

```bash
git clone git@github.com:ezagent42/dev-loop-skills.git ~/.claude/skills/dev-loop-skills
```

### 2. 拷贝 Skill 1（zchat 项目知识库）

Skill 1 是 zchat 项目特定的，不在 Git 包里。从同事处拷贝：

```bash
# 从同事那里拷贝（或从共享目录）
cp -r /path/to/skill-1-project-discussion-zchat-local ~/.claude/skills/skill-1-project-discussion-zchat-local
```

### 3. 创建 symlink

Claude Code 通过 `~/.claude/skills/` 下的目录发现 skill。每个 skill 需要一个 symlink：

```bash
# 通用 skill（从包里 symlink）
ln -sf ~/.claude/skills/dev-loop-skills/skills/skill-0-project-builder   ~/.claude/skills/project-builder
ln -sf ~/.claude/skills/dev-loop-skills/skills/skill-2-test-plan-generator ~/.claude/skills/test-plan-generator
ln -sf ~/.claude/skills/dev-loop-skills/skills/skill-3-test-code-writer  ~/.claude/skills/test-code-writer
ln -sf ~/.claude/skills/dev-loop-skills/skills/skill-4-test-runner       ~/.claude/skills/test-runner
ln -sf ~/.claude/skills/dev-loop-skills/skills/skill-5-feature-eval      ~/.claude/skills/feature-eval
ln -sf ~/.claude/skills/dev-loop-skills/skills/skill-6-artifact-registry ~/.claude/skills/artifact-registry
ln -sf ~/.claude/skills/dev-loop-skills/skills/using-dev-loop            ~/.claude/skills/using-dev-loop

# 项目特定 Skill 1
ln -sf ~/.claude/skills/skill-1-project-discussion-zchat-local ~/.claude/skills/project-discussion-zchat
```

### 4. 克隆 zchat 项目

```bash
git clone --recurse-submodules git@github.com:ezagent42/zchat.git ~/projects/zchat
cd ~/projects/zchat
uv sync
```

### 5. 安装 ergo languages（E2E 测试必需）

Homebrew 的 ergo 不含 languages 目录，需要手动补：

```bash
wget -qO- https://github.com/ergochat/ergo/releases/download/v2.18.0/ergo-2.18.0-linux-x86_64.tar.gz | tar xz -C /tmp
mkdir -p ~/.local/share/ergo
cp -r /tmp/ergo-2.18.0-linux-x86_64/languages ~/.local/share/ergo/languages
```

### 6. 验证安装

```bash
# 检查 skill 是否被识别（启动 claude 后应能看到）
ls ~/.claude/skills/*/SKILL.md | wc -l
# 应该输出 9（8 个 symlink + 1 个 dev-loop-skills 目录里不算）

# 检查 .artifacts/ 是否存在
ls ~/projects/zchat/.artifacts/registry.json

# 检查 ergo
ergo version
ls ~/.local/share/ergo/languages/ | head -3
```

## 怎么用

### 启动 Claude Code

```bash
cd ~/projects/zchat
./claude.sh   # 或直接 claude
```

Claude Code 会自动加载所有 skill。你可以直接提问：

### 问项目问题（触发 Skill 1）

```
zchat 的 agent 创建流程是什么？
```

Skill 1 会按流程：定位模块 → 读代码 → 跑测试 → 给出带 file:line 引用和测试输出的回答。

### 生成测试计划（触发 Skill 2）

```
根据 coverage-matrix 的缺口，生成一个测试计划
```

### 写 E2E 测试（触发 Skill 3）

```
根据刚才 confirmed 的 test-plan 写 E2E 测试代码
```

### 跑测试（触发 Skill 4）

```
跑一遍完整的 E2E 测试套件
```

### 提需求 / 报 bug（触发 Skill 5）

```
我想给 zchat 加一个 agent 间私聊功能（模拟模式）
```

```
agent create 之后 ready marker 没有出现（验证模式）
```

### 管理 artifact（触发 Skill 6）

```
查一下 .artifacts/ 里有哪些 artifact
```

## 跑 E2E 测试计划

完整的测试计划在 `docs/discuss/skill-dev/05-e2e-test-plan.md`（1187 行），覆盖所有 skill 的所有功能。

在 Claude Code 中：

```
请按照 docs/discuss/skill-dev/05-e2e-test-plan.md 执行 E2E 测试
```

或者逐个 skill 测试：

```
按照 05-e2e-test-plan.md 的 Skill 1 部分，验证项目知识问答功能
```

## 目录结构速查

```
~/.claude/skills/
├── dev-loop-skills/              # Git 包（通用 skill）
│   ├── skills/
│   │   ├── skill-0-project-builder/
│   │   ├── skill-2-test-plan-generator/
│   │   ├── skill-3-test-code-writer/
│   │   ├── skill-4-test-runner/
│   │   ├── skill-5-feature-eval/
│   │   ├── skill-6-artifact-registry/
│   │   └── using-dev-loop/
│   ├── package.json
│   ├── .claude-plugin/
│   └── README.md
├── skill-1-project-discussion-zchat-local/  # 项目特定（手动拷贝）
├── project-builder → dev-loop-skills/...    # symlink
├── project-discussion-zchat → skill-1-...   # symlink
├── test-plan-generator → dev-loop-skills/...
├── test-code-writer → dev-loop-skills/...
├── test-runner → dev-loop-skills/...
├── feature-eval → dev-loop-skills/...
├── artifact-registry → dev-loop-skills/...
└── using-dev-loop → dev-loop-skills/...

~/projects/zchat/.artifacts/         # 项目 artifact 空间
├── registry.json                    # artifact 索引
├── coverage/coverage-matrix.md      # 覆盖矩阵
├── bootstrap/                       # bootstrap 产出
│   ├── bootstrap-report.md
│   └── module-reports/*.json (×15)
├── eval-docs/                       # Phase 1/7 产出（初始为空）
├── test-plans/                      # Phase 3 产出（初始为空）
├── test-diffs/                      # Phase 4 产出（初始为空）
└── e2e-reports/                     # Phase 5 产出（初始为空）
```

## 注意事项

1. **Skill 1 是 zchat 专用的** — 如果要给其他项目用，需要跑 Skill 0 重新 bootstrap
2. **ergo languages 必须安装** — 否则 E2E 测试会失败
3. **.artifacts/ 跟着项目走** — 它在 zchat 仓库里，git clone 就有
4. **Skill 之间不自动串联** — 人控制何时触发下一个 skill
