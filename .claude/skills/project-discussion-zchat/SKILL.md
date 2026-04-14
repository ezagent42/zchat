---
name: "project-discussion-zchat"
description: "Project knowledge Q&A skill for zchat. Provides evidence-backed answers about code structure, module relationships, feature internals, test status, CLI commands, E2E pipeline info (for Skill 3), and bug triage (Phase 8 feedback routing). Trigger this skill for any zchat project question — even simple ones — as well as when discussing eval-docs, debugging module interactions, or querying test coverage gaps."
---

# zchat 项目知识库

> 由 Skill 0 (project-builder) 于 2026-04-10 自动生成。
> 这是一个**行为引擎**——指导如何查询和回答，数据存储在 `.artifacts/` 中。

## 项目概览

- **项目根目录**：/home/yaosh/projects/zchat
- **语言/框架**：Python 3.14 + Typer CLI + asyncio
- **测试框架**：pytest 9.0.2 + pytest-order 1.3.0 + pytest-asyncio
- **模块数**：15 (13 核心 + channel-server + protocol)
- **Artifact 空间**：/home/yaosh/projects/zchat/.artifacts/
- **Skill 6 可用**：是（/home/yaosh/.claude/skills/artifact-registry）

## 问答流程

被问到项目相关问题时，按以下步骤回答。目标是**每个回答都有实证**，不编造。

### Step 0: 检测更新（自动刷新）

每次回答前，检查是否有新的代码变更需要刷新索引：

1. 查询 `.artifacts/` 中的 `code-diff` 和 `e2e-report`，找出比 Skill 1 生成时间（2026-04-10）更新的条目
2. 如果有新的 code-diff：
   - 读取 diff 内容，识别受影响的模块
   - 对受影响的模块：**重新读取源文件**（更新 file:line 引用）
   - 对受影响的模块：**重新运行测试命令**（更新基线结果）
   - 用新数据回答，而不是依赖过时的索引
3. 如果有新的 e2e-report（说明 bug 修复周期完成）：
   - 读取 report 了解哪些测试新增/修复
   - 更新覆盖认知（之前标记为 ❌ 的用户流程可能已变为 ✅）

如果没有新 artifact，跳过此步骤直接进入 Step 1。

**异常处理**：如果索引中的文件路径不存在（文件已移动/重命名），重新扫描受影响模块的文件。如果测试命令执行失败（命令过时），检查 coverage-matrix 和 module-details 获取最新路径。

### Step 1: 解析问题 → 定位模块

查阅下方"模块索引"，找到问题涉及的模块。如果不确定涉及哪个模块，查"用户流程→模块映射"表。

如果问题涉及的模块不在索引中（可能是新增模块），扫描项目根目录 `zchat/cli/` 下的 `.py` 文件查找。

### Step 2: 读取代码

根据索引中的文件路径，用 Read 工具读取**当前**代码（不是 bootstrap 时的快照）。引用具体的 file:line。

如果 Step 0 已刷新了该模块，使用刷新后的路径。

### Step 3: 跑测试验证

运行对应的测试命令，捕获**当前**输出作为证据。测试命令见下方"模块索引"的测试命令列。

结果可能与索引中记录的基线不同（代码已变更），以实际运行结果为准。

### Step 4: 查询已有知识

查询 `.artifacts/` 中的相关 artifact，特别是：
- 被驳回的 eval-doc（status=archived）——已知边界/FAQ
- e2e-report——了解最近的测试结果和修复历史
- code-diff——了解最近的代码变更
- coverage-matrix——测试覆盖现状

使用 Skill 6 (artifact-registry) 查询：
```bash
bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh --project-root /home/yaosh/projects/zchat --type eval-doc --status archived
```

### Step 5: 组织回答

回答格式：
1. 直接回答问题
2. 附上证据：file:line 引用 + 测试输出
3. 如果在 `.artifacts/` 中找到相关的被驳回 eval-doc，引用它作为已知边界

如果无法确认某个断言，标注为 `[unverified]` 而不是猜测。

### Step 6: 分流判断（自然延伸，非独立模式）

如果本次讨论涉及 `.artifacts/` 中的 eval-doc 或 issue（比如用户带着一个问题报告来讨论"这是不是 bug"），在 Step 5 回答后继续：

1. **明确提出分析结论**：基于代码证据和测试结果，给出判断（确认 bug / 不是 bug / 需要更多信息）
2. **询问人是否确认**结论
3. **人确认后执行对应操作**：

**结论是 bug**：
- Issue 保持 open
- 告知用户：eval-doc 将进入 Phase 3（Skill 2 生成 test-plan）

**结论不是 bug**：
```bash
# 更新 eval-doc 状态
bash /home/yaosh/.claude/skills/artifact-registry/scripts/update-status.sh \
  --project-root /home/yaosh/projects/zchat --id <eval-doc-id> --status archived
```
同时在 eval-doc 文件的 frontmatter 中追加：
```yaml
rejection_reason: "<具体原因，引用代码证据>"
rejected_at: "2026-04-10"
```
Git commit 追踪变更。

如果讨论**不涉及**任何 eval-doc/issue（只是普通的项目问题），则 Step 5 回答完即结束，不执行 Step 6。

---

## 自我演进

Skill 1 通过两层机制保持知识最新：

### 动态层：自动刷新（Step 0）

每次回答前，Step 0 检查 `.artifacts/` 中的新 artifact：
- **新 code-diff** → 重新读取受影响模块的源文件 + 重新跑测试 → 更新 file:line 引用和测试基线
- **新 e2e-report** → 更新覆盖认知（哪些用户流程已有 E2E 测试）
- **文件路径失效** → 扫描 `zchat/cli/` 重建索引

这确保 bug 修复后 Skill 1 自动获取最新代码状态和测试结果，不需要重新 bootstrap。

### 知识层：artifact 积累

- **驳回结论** → eval-doc archived + rejection_reason → Step 4 查询时自动获取
- **Bug 修复历史** → eval-doc → test-plan → e2e-report 链条 → Step 4 查询时可追溯完整修复过程
- **覆盖变化** → 新 e2e-report 更新 coverage-matrix → 覆盖缺口逐步缩小

### 何时需要重新 bootstrap

以下情况 Step 0 的刷新不够，需要重跑 Skill 0：
- 大规模重构（多模块重命名/合并/拆分）
- 新增了完全独立的模块（不在任何已有模块路径下）
- 测试框架更换

知识增长发生在 `.artifacts/` + 实时代码读取，Skill 1 的 SKILL.md 保持轻量。

---

## 模块索引

| 模块 | 路径 | 职责 | 测试命令 | 基线结果 | 用户流程 |
|------|------|------|---------|---------|---------|
| agent_manager | `zchat/cli/agent_manager.py` | Agent 生命周期管理 (create/stop/restart/list/send) | `uv run pytest tests/unit/test_agent_manager.py tests/unit/test_agent_focus_hide.py -v` | 19/19 passed | 创建agent, 停止agent, 重启agent, focus/hide |
| irc_manager | `zchat/cli/irc_manager.py` | Ergo IRC daemon + WeeChat 管理 | `uv run pytest tests/unit/test_irc_check.py -v` | 3/4 (1 WSL2 bug) | IRC daemon 启停, WeeChat 连接 |
| auth | `zchat/cli/auth.py` | OIDC device code flow, token cache, credentials | `uv run pytest tests/unit/test_auth.py -v` | 15/15 passed | OIDC 登录, 本地登录 |
| ergo_auth | `zchat/cli/ergo_auth_script.py` | Ergo SASL auth-script (Keycloak userinfo) | `uv run pytest tests/unit/test_ergo_auth_script.py -v` | 4/4 passed | OIDC 登录 |
| project | `zchat/cli/project.py` | Project CRUD, config.toml, resolve | `uv run pytest tests/unit/test_project.py tests/unit/test_project_create_params.py -v` | 22/22 passed | 创建/列出/删除/切换项目 |
| layout | `zchat/cli/layout.py` | KDL layout 生成 (Zellij sessions) | `uv run pytest tests/unit/test_layout.py -v` | 8/8 passed | Zellij tab 创建 |
| zellij | `zchat/cli/zellij.py` | Zellij CLI helpers (session/tab/pane) | `uv run pytest tests/unit/test_zellij_helpers.py -v` | 22/22 passed | Zellij tab 创建/关闭 |
| config_cmd | `zchat/cli/config_cmd.py` | 全局 config (~/.zchat/config.toml) | `uv run pytest tests/unit/test_config_cmd.py -v` | 11/11 passed | 配置管理 |
| defaults | `zchat/cli/defaults.py` | 内置默认值 (data/defaults.toml) | `uv run pytest tests/unit/test_defaults.py -v` | 6/6 passed | 配置管理 |
| paths | `zchat/cli/paths.py` | 集中路径解析 (env > config > defaults) | `uv run pytest tests/unit/test_paths.py -v` | 24/24 passed | (基础设施, 全模块依赖) |
| runner | `zchat/cli/runner.py` | Runner 解析: global config + template 合并 | `uv run pytest tests/unit/test_runner.py -v` | 16/16 passed | 模板管理 |
| template_loader | `zchat/cli/template_loader.py` | Template 发现、加载、env 渲染 | `uv run pytest tests/unit/test_template_loader.py -v` | 8/8 passed | 模板管理 |
| migrate | `zchat/cli/migrate.py` | Config/state migration (tmux → Zellij) | `uv run pytest tests/unit/test_migrate.py -v` | 4/4 passed | (内部迁移) |
| update | `zchat/cli/update.py` | 版本检查 (git/PyPI) + 原子升级 | `uv run pytest tests/unit/test_update.py -v` | 19/19 passed | 版本更新 |
| doctor | `zchat/cli/doctor.py` | 环境诊断, WeeChat plugin setup | - | 无测试 | 环境诊断 |
| app | `zchat/cli/app.py` | Main Typer CLI app, 命令树, session 管理 | `uv run pytest tests/unit/test_list_commands.py tests/unit/test_plugin_integration.py -v` | 11/11 passed | (CLI 入口) |
| channel-server | `zchat-channel-server/` | MCP server 桥接 IRC ↔ Claude Code | `cd zchat-channel-server && uv run pytest tests/ -v` | 12/12 passed | Agent MCP 消息, @mention 回复 |
| protocol | `zchat-protocol/` | 协议规范 (naming, sys_messages) | `cd zchat-protocol && uv run pytest tests/ -v` | 7/9 (2 scoped_name bugs) | Agent 命名 |

## 详细模块描述

详见 `references/module-details.md`（从 `.artifacts/bootstrap/module-reports/*.json` 汇总生成）。

该文件包含每个模块的：
- 职责（一句话，含 file:line 引用）
- 关键接口表（接口名、位置、说明）
- 依赖关系（模块间调用方向）
- 对应用户流程（CLI 命令映射）
- 模块依赖图（全局视图）

## 用户流程 → 模块映射

| 用户流程 | 操作步骤 | 涉及模块 | E2E 覆盖 |
|---------|---------|---------|---------|
| WeeChat 连接到 IRC | `zchat irc start` | irc_manager, zellij, auth | ✅ test_weechat_connects |
| 创建 agent 并加入 IRC | `zchat agent create helper` | agent_manager, irc_manager, zellij, runner | ✅ test_agent_joins_irc |
| Agent 向频道发消息 | Agent MCP reply tool | channel-server | ⚠️ test_agent_send_to_channel (30s 超时) |
| @mention 触发 agent 回复 | `@alice-agent0 question` | channel-server | ⚠️ test_mention_triggers_reply (30s 超时) |
| 创建第二个 agent | `zchat agent create agent1` | agent_manager, zellij, runner | ⚠️ test_second_agent (30s 超时) |
| Agent 间通信 | `@alice-agent1 from agent0` | channel-server | ⚠️ test_agent_to_agent (30s 超时) |
| 用户间对话 | alice ↔ bob IRC PRIVMSG | (IRC 原生) | ✅ test_alice_bob_conversation |
| 停止 agent | `zchat agent stop helper` | agent_manager, zellij | ✅ test_agent_stop |
| 全局 shutdown | `zchat shutdown` | agent_manager, irc_manager, zellij | ✅ test_shutdown |
| Zellij tab 创建/关闭 | (内部) | zellij | ✅ test_tab_create_exists_close |
| Zellij pane 发送/读取 | (内部) | zellij | ✅ test_send_and_read |
| 创建项目 | `zchat project create local` | project, paths, defaults | ❌ |
| 列出/删除/切换项目 | `zchat project list/remove/use` | project | ❌ |
| IRC daemon 启停 | `zchat irc daemon start/stop` | irc_manager, zellij | ❌ |
| OIDC 登录 | `zchat auth login` | auth, ergo_auth | ❌ |
| 本地模式登录 | `zchat auth login --method local` | auth | ❌ |
| 环境诊断 | `zchat doctor` | doctor | ❌ |
| 模板管理 | `zchat template list/show/set/create` | template_loader, runner | ❌ |
| 配置管理 | `zchat config get/set/list` | config_cmd, defaults | ❌ |
| 版本更新 | `zchat update/upgrade` | update | ❌ |
| Agent 重启 | `zchat agent restart helper` | agent_manager, zellij | ❌ |
| Agent focus/hide | `zchat agent focus/hide helper` | agent_manager, zellij | ❌ |
| Agent 发送文本 | `zchat agent send agent0 "..."` | agent_manager | ❌ |

## 测试 Pipeline 信息

供 Skill 3 (test-code-writer) 查询，了解如何在此项目中追加 E2E 测试用例。

- **测试框架**：pytest 9.0.2 + pytest-order 1.3.0 + pytest-asyncio
- **E2E 测试目录**：tests/e2e/
- **E2E conftest 位置**：tests/e2e/conftest.py
- **已有 fixture 列表**：e2e_port, zellij_session, e2e_context, ergo_server, zchat_cli, zellij_send, irc_probe, bob_probe, weechat_tab
- **fixture 模式**：session-scoped 共享基础设施——所有 fixture 使用 `scope="session"` 避免重复启动 ergo/zellij。e2e_context 提供临时 ZCHAT_HOME 和项目配置。
- **测试命名规范**：`test_{action}_{target}`（如 test_agent_joins_irc, test_weechat_connects）
- **证据采集工具**：IrcProbe (tests/shared/irc_probe.py) + zellij helpers (tests/shared/zellij_helpers.py)
- **证据采集方式**：IrcProbe 通过 IRC WHOIS/PRIVMSG 验证 nick 存在和消息到达；zellij dump_screen 验证终端输出
- **E2E 标记/marker**：`@pytest.mark.e2e`
- **运行 E2E 的命令**：`uv run pytest tests/e2e/ -v -m e2e`
- **Shared helpers**：tests/shared/ 目录，包含 irc_probe.py, cli_runner.py, zellij_helpers.py, tmux_helpers.py（遗留）

## Artifact 交互

查询 artifact：
```bash
bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat --type eval-doc --status archived
```

注册新 artifact：
```bash
bash /home/yaosh/.claude/skills/artifact-registry/scripts/register.sh \
  --project-root /home/yaosh/projects/zchat --type eval-doc --id <id> --status open
```

更新状态：
```bash
bash /home/yaosh/.claude/skills/artifact-registry/scripts/update-status.sh \
  --project-root /home/yaosh/projects/zchat --id <id> --status archived
```

关联 artifact：
```bash
bash /home/yaosh/.claude/skills/artifact-registry/scripts/link.sh \
  --project-root /home/yaosh/projects/zchat --from <id-a> --to <id-b>
```

## 自验证记录

Skill 1 生成后，所有测试命令已运行并与基线比对通过。

| 模块 | 基线结果 | 验证结果 | 匹配 |
|------|---------|---------|------|
| agent_manager | 19/19 | 19/19 passed | ✅ |
| irc_manager | 3/4 | 3/4 (1 WSL2) | ✅ |
| auth | 15/15 | 15/15 passed | ✅ |
| ergo_auth_script | 4/4 | 4/4 passed | ✅ |
| project | 22/22 | 22/22 passed | ✅ |
| layout | 8/8 | 8/8 passed | ✅ |
| zellij | 22/22 | 22/22 passed | ✅ |
| config_cmd | 11/11 | 11/11 passed | ✅ |
| defaults | 6/6 | 6/6 passed | ✅ |
| paths | 24/24 | 24/24 passed | ✅ |
| runner | 16/16 | 16/16 passed | ✅ |
| template_loader | 8/8 | 8/8 passed | ✅ |
| migrate | 4/4 | 4/4 passed | ✅ |
| update | 19/19 | 23/23 passed | ⬆️ 新增 4 个测试 |
| app | 11/11 | 11/11 passed | ✅ |
| channel-server | 12/12 | 12/12 passed | ✅ |
| protocol | 7/9 | 7/9 (2 bugs) | ✅ |

验证时间：2026-04-10，全部 17 个 test-runner 已运行。

## 环境依赖

运行 E2E 测试所需的环境：

| 依赖 | 状态 | 说明 |
|------|------|------|
| ergo IRC server (port 6667) | 必需 | E2E 测试需要 IRC 连接，fixture 自动在随机高端口启动 |
| zellij ≥0.44 | 必需 | E2E 测试通过 zellij 管理 session/tab/pane |
| WeeChat | 必需 | E2E 测试 test_weechat_connects 需要 WeeChat 二进制 |
| uv ≥0.7 | 必需 | 项目依赖管理 + 测试运行 |
| asciinema | 可选 | pre-release walkthrough 录制，不影响 E2E |
| docker | 可选 | 当前无测试依赖 docker |

## 已知问题

1. **protocol scoped_name 双前缀 bug**：`scoped_name("alice-helper", "alice")` 返回 `"alice-alice-helper"` 而非 `"alice-helper"`；`scoped_name("bob-helper", "alice")` 返回 `"alice-bob-helper"` 而非 `"bob-helper"`。测试文件：`zchat-protocol/tests/test_naming.py`，2/9 failed。
2. **test_irc_check 环境敏感**：`test_unreachable_server_raises` 在 WSL2 下失败——192.0.2.1 连接被快速拒绝而非超时。测试文件：`tests/unit/test_irc_check.py`，1/4 failed。
3. **4 个 E2E MCP 超时**：test_agent_send_to_channel, test_mention_triggers_reply, test_second_agent, test_agent_to_agent 均因 Claude Code MCP reply 在 30s 内未完成而超时。根因是 MCP channel-server 需要 Claude Code 实际响应，CI 环境下无法保证响应时间。
