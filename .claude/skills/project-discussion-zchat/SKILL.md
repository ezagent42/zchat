---
name: "project-discussion-zchat"
description: "Project knowledge Q&A skill for zchat (multi-agent IRC-based CS system). Provides evidence-backed answers about code structure, module relationships, feature internals, test status, CLI commands, E2E pipeline info (for Skill 3), and bug triage (Phase 8 feedback routing). Trigger this skill for any zchat project question — even simple ones — as well as when discussing eval-docs, debugging module interactions, or querying test coverage gaps."
---

# zchat 项目知识库

> 由 Skill 0 (project-builder) 于 2026-04-22 规范化生成（V6 finalize 后）。
> 这是一个**行为引擎**——指导如何查询和回答，数据存储在 `.artifacts/` 中。

## 项目概览

- **项目根目录**：/home/yaosh/projects/zchat
- **语言/框架**：Python 3.12+ (requires-python ≥3.12) + Typer CLI + asyncio + MCP
- **测试框架**：pytest + pytest-asyncio + pytest-order
- **模块数**：11 (主库) + 2 submodules (zchat-channel-server, zchat-protocol)
- **Artifact 空间**：/home/yaosh/projects/zchat/.artifacts/
- **Skill 6 可用**：是（artifact-registry 路径见用户 ~/.claude/skills/artifact-registry 或 plugin cache）
- **当前 dev 分支**：69f4f78（V6 finalize 合入）

## 问答流程

被问到项目相关问题时，按以下步骤回答。目标是**每个回答都有实证**，不编造。

### Step 0: 检测更新（自动刷新）

每次回答前，检查 `.artifacts/` 中的新 artifact：

1. 查询 `.artifacts/code-diffs/` + `.artifacts/e2e-reports/`，找出比 Skill 1 生成时间（2026-04-22）更新的条目
2. 有新 code-diff → 读 diff → 识别受影响模块 → 重新读源文件 + 重跑对应 test-runner
3. 有新 e2e-report → 读 report → 更新覆盖认知
4. 无新增 → 跳过

**异常处理**：若索引中的路径不存在（文件被移动/重命名），运行 `scripts/refresh-index.sh`。

### Step 1: 解析问题 → 定位模块

查下方"模块索引"或"用户流程→模块映射"。新增模块（不在索引）：运行 `scripts/refresh-index.sh --module <name>`。

### Step 2: 读代码

Read 当前源文件（不是 bootstrap 时的快照），引用 file:line。

### Step 3: 跑测试验证

```bash
bash scripts/test-<module>.sh
```
以实际运行结果为准。

### Step 4: 查已有知识

查 `.artifacts/`：
- 被驳回 eval-doc（`status: archived`）—— 已知边界/FAQ
- e2e-report —— 最近测试历史
- code-diff —— 最近代码变更
- coverage-matrix —— 覆盖现状

**有 Skill 6**：
```bash
bash ~/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat \
  --type eval-doc --status archived
```

### Step 5: 组织回答

1. 直接回答
2. 附证据：file:line + 测试输出
3. 相关已驳回 eval-doc 作为已知边界

无法确认的断言标 `[unverified]`，不猜。

### Step 6: 分流判断（仅当涉及 eval-doc/issue）

基于代码证据给出 bug / 非 bug / 信息不足判断 → 询问人确认。

**结论是 bug**：保留 issue open，告知用户将进 Phase 3（Skill 2 生成 test-plan）。

**结论不是 bug**：
```bash
bash scripts/close-issue.sh --issue-url <url> --reason "<说明>"
bash ~/.claude/skills/artifact-registry/scripts/update-status.sh \
  --project-root /home/yaosh/projects/zchat --id <eval-doc-id> --status archived
```
eval-doc frontmatter 追加 `rejection_reason` + `rejected_at`。Git commit 追踪。

---

## 自我演进

### 动态层：自动刷新（Step 0）
- 新 code-diff → 重读源 + 重跑 test-runner
- 新 e2e-report → 更新覆盖认知
- 路径失效 → `scripts/refresh-index.sh`

不重新 bootstrap 也能获取最新状态。

### 知识层：artifact 积累
- 驳回结论：eval-doc archived + rejection_reason
- Bug 修复历史：eval-doc → test-plan → e2e-report 链路
- 覆盖变化：新 e2e-report 更新 coverage-matrix

### 何时需要重跑 Skill 0
- 大规模重构（多模块重命名/合并/拆分）
- 新增独立模块（不在现有路径下）
- 测试框架更换

---

## 模块索引

| 模块 | 路径 | 职责 | 测试命令 | 基线 | 用户流程 |
|------|------|------|---------|------|---------|
| agent_manager | `zchat/cli/agent_manager.py` | Agent lifecycle (create/stop/restart/list) + zellij tab 绑定 + ready marker | `bash scripts/test-agent_manager.sh` | 25 passed | 创建/停止/重启 agent |
| app | `zchat/cli/app.py` | Typer 根 + 所有子命令 (project/irc/agent/bot/channel/audit/template/...) | `bash scripts/test-app.sh` | 52 passed | 全部 CLI 入口 |
| auth | `zchat/cli/auth.py` + `ergo_auth_script.py` | OIDC device-code + SASL + ergo auth-script (stdin/stdout JSON 子进程) | `bash scripts/test-auth.sh` | 19 passed | 登录/凭证刷新 |
| doctor_update | `zchat/cli/doctor.py` + `update.py` + `audit_cmd.py` | 环境诊断 + 自动升级 + audit.json 只读 CLI (admin-agent 使用) | `bash scripts/test-doctor_update.sh` | 43 passed | `zchat doctor`, `zchat audit status/report`, 自升级 |
| irc_manager | `zchat/cli/irc_manager.py` | ergo daemon 生命周期 + WeeChat zellij tab + SASL auth 注入 | `bash scripts/test-irc_manager.sh` | 32 passed | `zchat irc daemon start`, `zchat irc start` |
| project | `zchat/cli/project.py` + `paths.py` + `defaults.py` + `config_cmd.py` + `migrate.py` | project CRUD + 全局 paths + 默认值 + tmux→zellij migrator | `bash scripts/test-project.sh` | 65 passed | `zchat project create/use/list/remove` |
| routing | `zchat/cli/routing.py` | routing.toml CRUD (V6 schema `[bots.*]` + `[channels.*]`) | `bash scripts/test-routing.sh` | 67 passed | `zchat bot add`, `zchat channel create`, 路由热加载 |
| runner | `zchat/cli/runner.py` + `template_loader.py` | template 解析 + .env 渲染 (runner.py 是 V6 API；template_loader.py 是 legacy) | `bash scripts/test-runner.sh` | 11 passed | agent 启动时自动调用 |
| templates | `zchat/cli/templates/` | 5 个内置 agent 模板（claude/fast-agent/deep-agent/admin-agent/squad-agent）soul.md + skills/ + start.sh + template.toml + .env.example | `bash scripts/test-templates.sh` | 11 passed | `zchat template list/show/set/create` |
| tests | `tests/` | 三层测试套件 (unit 29 文件 + e2e 31 tests + pre_release walkthrough) | `bash scripts/test-unit-all.sh` / `test-e2e.sh` / `test-pre-release.sh` | 304 unit passed / 31 e2e collected | 所有测试执行 |
| zellij | `zchat/cli/zellij.py` + `layout.py` | `zellij action` subprocess 封装 + KDL layout 生成 | `bash scripts/test-zellij.sh` | 31 passed | agent/weechat tab 管理 |

**Submodules**（独立 repo，tests 单独跑）：
- `zchat-channel-server/`：channel-server + plugins + feishu_bridge + agent_mcp（`bash scripts/test-channel-server.sh`）
- `zchat-protocol/`：`irc_encoding.py` + `ws_messages.py` + `naming.py`（`bash scripts/test-protocol.sh`）

## 详细模块描述

详见 `references/module-details.md`（从 `.artifacts/bootstrap/module-reports/*.json` 汇总生成）。

## 用户流程 → 模块映射

| 用户流程 | 操作步骤 | 涉及模块 | 入口 file:line | E2E 覆盖 | test-runner |
|---------|---------|---------|---------------|---------|------------|
| 创建 project | `zchat project create prod` | project, routing | `project.py::create_project_config` | ❌ | test-project.sh |
| 注册 bot | `zchat bot add customer --app-id ... --template fast-agent [--supervises X] [--lazy]` | app, routing | `app.py::bot_add` | ❌ | test-routing.sh |
| 注册 channel | `zchat channel create conv-001 --bot customer --external-chat oc_xxx --entry-agent ...` | app, routing | `app.py::channel_create` | ❌ | test-routing.sh |
| 一键启动 | `zchat up` → ergo + zellij session + cs tab + bridge-* tabs + agent tabs | app, irc_manager, agent_manager, zellij, layout | `app.py::cmd_up` | ⚠️ 手动 walkthrough | test-e2e.sh |
| 启动单 agent | `zchat agent create fast-001 --type fast-agent --channel conv-001` | agent_manager, runner, zellij | `agent_manager.py::AgentManager.create` | ⚠️ e2e fixture 起 | test-agent_manager.sh |
| 飞书客户发问 → agent 回复 | 完整消息生命周期（bridge→CS→IRC→agent→回路）| 主库 + CS/protocol submodule | CS router.py + agent_mcp.py | ⚠️ pre_release 脚本 | test-pre-release.sh |
| /hijack / /release 接管 | squad 点接管 → mode plugin → agent 切副驾驶 | CS plugins/mode + bridge | CS `plugins/mode/plugin.py` | ❌ 主库未覆盖 | (CS 单元测试) |
| CSAT 评分 | 客户评分 → csat plugin → audit.record_csat → recall+resend | CS plugins/csat + audit | CS `plugins/csat/plugin.py` | ❌ | (CS 单元测试) |
| /review admin 查报告 | admin 发 /review → run_zchat_cli audit report | doctor_update, templates | `audit_cmd.py::audit_report` | ❌ | test-doctor_update.sh |
| OIDC 登录 | `zchat auth login` device-code flow | auth | `auth.py::device_code_flow` | ❌ | test-auth.sh |
| 环境诊断 | `zchat doctor` | doctor_update | `doctor.py::run_doctor` | ❌ | test-doctor_update.sh |
| 自动升级 | `zchat update run` | doctor_update | `update.py::run_upgrade` | ❌ | test-doctor_update.sh |

## 测试 Pipeline 信息

供 Skill 3 (test-code-writer) 参考：

- **测试框架**：pytest + pytest-asyncio + pytest-order
- **E2E 测试目录**：`tests/e2e/`（31 tests collected）
- **E2E conftest 位置**：`tests/conftest.py`（若无特定 conftest），shared helper 在 `tests/shared/`
- **E2E marker**：`@pytest.mark.e2e`（默认不跑，`-m e2e` 显式开启）
- **E2E 运行命令**：`uv run pytest tests/e2e/ -v -m e2e`
- **已有 fixture 模式**：
  - 子进程调用：`uv run python -m zchat.cli` 包装（不直接 import CLI 函数）
  - 临时 workspace：`tmp_path` + `ZCHAT_PROJECT_DIR` env 覆盖
  - tmux/zellij 生命周期：setup-teardown 显式清理 session
- **测试命名规范**：`tests/unit/test_<module>.py::test_<behavior>`；E2E 用 `test_<flow>_lifecycle.py`
- **证据采集工具**：pre_release 用 asciinema + agg；unit/e2e 仅 pytest -v stdout
- **证据采集方式**：`.cast` 文件 + 自动生成 `.gif`（见 `tests/pre_release/walkthrough.sh`）

## Test Runners

每个模块对应一个 test-runner 脚本，所有脚本 `--help` / `--dry-run` 支持。

| 脚本 | 模块 | 命令 | 基线结果 |
|------|------|------|---------|
| `scripts/test-agent_manager.sh` | agent_manager | `uv run pytest tests/unit/test_agent_manager.py tests/unit/test_agent_focus_hide.py -v` | 25 passed |
| `scripts/test-app.sh` | app | `uv run pytest tests/unit/test_channel_cmd.py test_list_commands.py test_project_cli_flow.py test_project_create_params.py test_project_use_command.py -v` | 52 passed |
| `scripts/test-auth.sh` | auth | `uv run pytest tests/unit/test_auth.py tests/unit/test_ergo_auth_script.py -v` | 19 passed |
| `scripts/test-doctor_update.sh` | doctor_update | `uv run pytest tests/unit/test_doctor.py tests/unit/test_update.py tests/unit/test_audit_cli.py -v` | 43 passed |
| `scripts/test-irc_manager.sh` | irc_manager | `uv run pytest tests/unit/test_irc_manager_*.py tests/unit/test_irc_check.py tests/unit/test_wsl2_proxy_rewrite.py -v` | 32 passed |
| `scripts/test-project.sh` | project | `uv run pytest tests/unit/test_project*.py test_paths.py test_defaults.py test_config_cmd.py -v` | 65 passed |
| `scripts/test-routing.sh` | routing | `uv run pytest tests/unit/test_routing_cli.py tests/unit/test_channel_cmd.py -v` | 67 passed |
| `scripts/test-runner.sh` | runner | `uv run pytest tests/unit/test_template_loader.py tests/unit/test_start_sh.py -v` | 11 passed |
| `scripts/test-templates.sh` | templates | `uv run pytest tests/unit/test_template_loader.py tests/unit/test_start_sh.py -v` | 11 passed |
| `scripts/test-zellij.sh` | zellij | `uv run pytest tests/unit/test_zellij_helpers.py tests/unit/test_layout.py -v` | 31 passed |
| `scripts/test-unit-all.sh` | (全量 unit) | `uv run pytest tests/unit/ -v` | **304 passed** |
| `scripts/test-e2e.sh` | (E2E) | `uv run pytest tests/e2e/ -v -m e2e` | 31 collected (需 ergo+zellij) |
| `scripts/test-pre-release.sh` | (pre_release) | `./tests/pre_release/walkthrough.sh` | 手动 review `.cast` |
| `scripts/test-channel-server.sh` | submodule CS | `cd zchat-channel-server && uv run pytest tests/ -v` | ~540 passed (V6 finalize) |
| `scripts/test-protocol.sh` | submodule protocol | `cd zchat-protocol && uv run pytest tests/ -v` | passes |

## Artifact 交互

### 有 Skill 6 时（推荐）

```bash
# 查询被驳回的 eval-doc
bash ~/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat --type eval-doc --status archived

# 注册新 artifact（如新 eval-doc）
bash ~/.claude/skills/artifact-registry/scripts/register.sh \
  --project-root /home/yaosh/projects/zchat \
  --type eval-doc --name "新 bug 分流" --producer skill-1 \
  --path .artifacts/eval-docs/eval-xyz.md --status draft

# 更新状态
bash ~/.claude/skills/artifact-registry/scripts/update-status.sh \
  --project-root /home/yaosh/projects/zchat --id eval-doc-xyz --status archived
```

### 无 Skill 6 时（fallback）

- 查询：`ls .artifacts/eval-docs/` 并读 frontmatter
- 创建：直接写入对应子目录，带 YAML frontmatter (`type / producer / status / created_at`)
- 更新：编辑 frontmatter

## 自验证记录

Skill 1 生成后所有 test-runner 已运行并与基线比对通过（自验证时间：2026-04-22）。

| test-runner | 基线结果 | 验证结果 | 匹配 |
|-------------|---------|---------|------|
| test-agent_manager.sh | 25 passed | 25 passed | ✅ |
| test-app.sh | 52 passed | 52 passed | ✅ |
| test-auth.sh | 19 passed | 19 passed | ✅ |
| test-doctor_update.sh | 43 passed | 43 passed | ✅ |
| test-irc_manager.sh | 32 passed | 32 passed | ✅ |
| test-project.sh | 65 passed | 65 passed | ✅ |
| test-routing.sh | 67 passed | 67 passed | ✅ |
| test-runner.sh | 11 passed | 11 passed | ✅ |
| test-templates.sh | 11 passed | 11 passed | ✅ |
| test-zellij.sh | 31 passed | 31 passed | ✅ |
| test-unit-all.sh | 304 passed | 304 passed | ✅ |

E2E + pre_release + submodule tests 未在 Skill 1 生成期跑（需外部服务），请按 test-runner 基线命令手动验证。

## 环境依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| uv | 必需 | Python 依赖管理 |
| Python 3.12+ | 必需 | 项目运行时 |
| zellij | 必需（E2E）| Session/tab 管理，E2E 测试依赖 |
| claude (Claude Code CLI) | 必需（agent 运行）| agent 后端 |
| zchat-channel-server | 必需（运行时）| 安装为 CLI tool 或 submodule uv sync |
| ergo | 可选（本地 IRC）| 可用外部 IRC server 替代 |
| weechat | 可选（GUI）| 用户监控 IRC；无 GUI 不影响 API |
| jq | 可选（scripting）| audit JSON 解析，非必需 |
| asciinema + agg | 可选（pre_release）| 录制 walkthrough，仅验收阶段用 |
| tmux | 已废弃 | V5+ 迁移到 zellij，`migrate.py` 保留兼容转换 |

## 关联文档

`docs/guide/` 是面向用户的阅读顺序（新 V6 整理）：
- 001 architecture / 002 quick-start / 003 e2e-pre-release / 004 migrate (AutoService)
- 005 dev-guide (Q&A 红线) / 006 routing-config / 007 plugin-guide

设计历史 `docs/discuss/`，归档 `docs/archive/`。
