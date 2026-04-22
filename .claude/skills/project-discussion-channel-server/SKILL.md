---
name: "project-discussion-channel-server"
description: "Project knowledge Q&A skill for zchat-channel-server (MCP bridge IRC <-> Claude Code). Provides evidence-backed answers about server architecture, IRC event handling, MCP tool registration, message chunking, sys message protocol, slash commands, and instructions template. Trigger this skill for any channel-server question — code structure, module relationships, test status, E2E pipeline info (for Skill 3), and bug triage (Phase 8 feedback routing). Also trigger when discussing cs-* artifacts, debugging IRC-MCP bridge issues, or querying test coverage gaps in channel-server."
---

# zchat-channel-server 项目知识库

> 由 Skill 0 (project-builder) 于 2026-04-22 规范化生成（V6 finalize 后）。
> 这是一个**行为引擎**——指导如何查询和回答，数据存储在 `.artifacts/` 中。

## 项目概览

- **项目根目录**：`zchat-channel-server/`（zchat 主库的 git submodule；独立 repo: `ezagent42/claude-zchat-channel`）
- **语言/框架**：Python 3.12+ + asyncio + MCP (mcp[cli]) + irc ≥20 + websockets + lark-oapi
- **测试框架**：pytest + pytest-asyncio（`asyncio_mode=auto`）+ pytest-order + pytest-timeout
- **模块数**：6 (agent_mcp / channel_server / feishu_bridge / meta / plugins / tests)
- **Artifact 空间**：主库 `.artifacts/`（所有 CS 相关 artifact 必须以 `cs-` 前缀）
- **Skill 6 可用**：是（artifact-registry 脚本在主库 `~/.claude/skills/artifact-registry/`）
- **当前 dev 分支**：`refactor/v4 = dev`（V6 finalize HEAD = 726540d）

## 问答流程

被问到 channel-server 相关问题时按步骤回答，每个回答都要有实证，不编造。

### Step 0: 检测更新（自动刷新）

1. 查主库 `.artifacts/` 中 ID 以 `cs-` 开头的 `code-diff` 和 `e2e-report`，找比 2026-04-22 更新的条目
2. 有新 cs-code-diff → 重读受影响源文件 + 重跑对应 test-runner
3. 有新 cs-e2e-report → 更新覆盖认知
4. 无新增 → 跳过

路径失效 → 运行 `scripts/refresh-index.sh`。

### Step 1: 解析问题 → 定位模块

查下方"模块索引"或"用户流程→模块映射"。

### Step 2: 读代码

Read 当前源文件（不是 bootstrap 快照），引用 file:line。

### Step 3: 跑测试验证

```bash
bash scripts/test-<module>.sh
```

### Step 4: 查已有知识

查 `.artifacts/` 中 `cs-*` 前缀的 artifact：
- archived eval-doc（已知边界/FAQ）
- e2e-report（最近测试历史）
- code-diff（最近代码变更）

**有 Skill 6**：
```bash
bash ~/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat \
  --type eval-doc --status archived
```

### Step 5: 组织回答

1. 直接回答
2. 附证据：file:line + 测试输出
3. 相关 archived eval-doc 作已知边界

无法确认的断言标 `[unverified]`，不猜。

### Step 6: 分流判断（仅当涉及 eval-doc/issue）

基于代码证据判 bug / 非 bug / 信息不足 → 人确认 →

**是 bug**：保留 issue open；进 Phase 3 生成 test-plan。

**不是 bug**：
```bash
bash scripts/close-issue.sh --issue-url <url> --reason "<说明>"
bash ~/.claude/skills/artifact-registry/scripts/update-status.sh \
  --project-root /home/yaosh/projects/zchat --id cs-eval-doc-xyz --status archived
```
eval-doc frontmatter 加 `rejection_reason` + `rejected_at`。Git commit 追踪。

---

## 自我演进

### 动态层：自动刷新（Step 0）
- 新 cs-code-diff → 重读源 + 重跑 test-runner
- 新 cs-e2e-report → 更新覆盖认知
- 路径失效 → `scripts/refresh-index.sh`

### 知识层：artifact 积累
- 驳回结论：eval-doc archived + rejection_reason
- Bug 修复历史：eval-doc → test-plan → e2e-report 链路
- 覆盖变化：新 e2e-report 更新 coverage-matrix

### 何时需要重跑 Skill 0
- CS 大规模重构（跨模块重命名/合并）
- 新增独立模块（不在现有 6 个路径下）
- 测试框架更换

---

## 模块索引

| 模块 | 路径 | 职责 | 测试命令 | 基线 | 用户流程 |
|------|------|------|---------|------|---------|
| agent_mcp | `agent_mcp.py`（根目录单文件）| MCP stdio server — 每个 Claude Code agent 一实例，暴露 4 tools (reply/join_channel/list_peers/run_zchat_cli) + 订阅 IRC pubmsg/privmsg/sys → 注入为 JSONRPCNotification | `bash scripts/test-agent_mcp.sh` | 15 passed | Claude reply 回 IRC；agent 发现同 channel peers |
| channel_server | `src/channel_server/` (9 files) | V4 核心路由：router + irc_connection + ws_server + plugin framework + plugin_loader (V7) + routing.toml 加载/热加载。纯基础设施，不写业务语义 | `bash scripts/test-channel_server.sh` | 47 passed | bridge→CS→IRC 入站；IRC→CS→bridge 出站；命令分派；NAMES 熔断 |
| feishu_bridge | `src/feishu_bridge/` (13 files) | V6 飞书适配：CardAwareClient WSS 入站 + BridgeAPIClient WS 连 CS + ChannelMapper + supervises 镜像 + lazy_create + CSAT 卡片 | `bash scripts/test-feishu_bridge.sh` | 67 passed | 飞书消息入站；squad 卡片+thread；lazy_create channel；CSAT 回流 |
| meta | `pyproject.toml` + `.claude-plugin/` + `commands/` + CI | 3 个 entry script + wheel 打包 + Claude Code plugin 元数据 (4 个 slash command) + GH Actions publish | — (无测试) | — | `zchat-channel-server` / `zchat-feishu-bridge` / `zchat-agent-mcp` 安装入口 |
| plugins | `src/plugins/` (13 files, 6 plugin 目录) | 6 个业务 plugin 挂到 PluginRegistry：mode / sla / resolve / audit / activation / csat。通过 emit_event 解耦，不互相 import | `bash scripts/test-plugins.sh` | 50 passed | /hijack-/release / /resolve / CSAT 评分 / 求助超时 timer / 客户回访识别 |
| tests | `tests/unit/` (22 files) + `tests/e2e/` (4 files) | 两层测试：unit (~180 case 无外部依赖) + e2e (@pytest.mark.e2e) | `bash scripts/test-all.sh` / `scripts/test-e2e.sh` | **191 passed** (179 unit + 12 e2e) | 所有代码验证 |

## 6 个官方 plugin 速览（`src/plugins/`）

| Plugin | 命令 | 订阅事件 | emit event | 持久化 |
|---|---|---|---|---|
| mode | `/hijack` `/release` `/copilot` | — | `mode_changed` | 内存 dict |
| sla | — | `mode_changed` (takeover timer) + `on_ws_message` (side 检测 @operator 启动 help timer) | `sla_breach` / `help_requested` / `help_timeout` | 内存 asyncio.Task dict |
| resolve | `/resolve` | — | `channel_resolved` | 无状态 |
| audit | — | `on_ws_message` + `mode_changed` / `channel_resolved` | — (只收集) | `<data_dir>/state.json` 落盘 |
| activation | — | `on_ws_message` (更新 last_activity) + `channel_resolved` (标 dormant) | `customer_returned` | `<data_dir>/state.json` 落盘 |
| csat | — | `channel_resolved` / `csat_score` | `csat_request` / `csat_recorded` | 转调 `audit.record_csat` |

注：
- plugin 之间**不互相 import**；V7 起 csat 持有 audit 引用通过 `plugin_loader` 的 **signature-driven DI** 注入（csat `__init__` 的 kw-only `audit=None` 参数）
- V7（2026-04-22）起 plugin 由 `channel_server.plugin_loader` config-driven 自动发现和注册。详见主库 `docs/guide/007-plugin-guide.md`

## 详细模块描述

详见 `references/module-details.md`（从 6 个 `module-reports/*.json` 聚合）。

## 用户流程 → 模块映射

| 用户流程 | 涉及模块 | 入口 file:line | E2E 覆盖 |
|---------|---------|---------------|---------|
| 飞书客户消息入站 → agent 回复 | feishu_bridge + channel_server + agent_mcp | `feishu_bridge/bridge.py::_forward` → CS `router.py::_handle_message` → `agent_mcp.py::on_pubmsg` | ⚠️ pre_release 手工 |
| agent reply → 回流飞书 | agent_mcp + channel_server + feishu_bridge | `agent_mcp.py::_handle_reply` → CS `router.py::forward_inbound_irc` → bridge `_on_bridge_event` | ⚠️ |
| /hijack 接管 | plugins.mode | `plugins/mode/plugin.py::on_command` | ❌ |
| /release 释放 | plugins.mode | 同上 | ❌ |
| takeover 180s SLA 超时 | plugins.sla | `plugins/sla/plugin.py::_timer_task` | ✅ `test_help_request_lifecycle.py` |
| @operator 求助 → help_requested | plugins.sla | `plugins/sla/plugin.py::on_ws_message` | ✅ 同上 |
| help 180s 超时 → help_timeout | plugins.sla | `plugins/sla/plugin.py::_help_timer_task` | ✅ 同上 |
| /resolve 结案 | plugins.resolve + csat | `plugins/resolve/plugin.py::on_command` → `plugins/csat/plugin.py::on_ws_event` | ✅ `test_csat_lifecycle.py` |
| CSAT 客户点星 | plugins.csat + feishu_bridge | `plugins/csat/plugin.py::on_ws_event` (csat_score) + bridge card recall/resend | ✅ |
| Supervisor 卡片 + thread 镜像 | feishu_bridge (supervises) | `feishu_bridge/bridge.py::_handle_supervised_message` | ⚠️ pre_release |
| lazy_create 拉 bot 入新群 | feishu_bridge + CLI subprocess | `feishu_bridge/bridge.py::_on_bot_added` → `zchat channel create` | ✅ `test_bridge_lazy_create.py` |
| agent 发现同 channel peers | agent_mcp (list_peers tool) | `agent_mcp.py::_handle_list_peers` | ❌ |

## 测试 Pipeline 信息

供 Skill 3 (test-code-writer) 参考：

- **测试框架**：pytest + pytest-asyncio (`asyncio_mode=auto`，不用 `@pytest.mark.asyncio`)
- **E2E 目录**：`tests/e2e/` (4 files, ~12 test)
- **E2E conftest**：`tests/conftest.py`（强制 `sys.path.insert(0, "src")` 以免根目录 plugins 污染）
- **Markers**：`e2e` / `prerelease`（pytest.ini 声明）
- **Fixture 模式**：
  - unit 普遍用 `AsyncMock` / `MagicMock` stub 飞书 / IRC / WS
  - e2e 起真 CS 实例（`__main__._main()`）+ fake bridge WS client
- **测试命名**：`tests/unit/test_<module>_plugin.py` / `test_<module>.py`；e2e 用 `test_<flow>_lifecycle.py`
- **证据采集**：pytest -v stdout + e2e 的 fixture 日志
- **运行 e2e**：`cd zchat-channel-server && uv run pytest tests/e2e/ -v -m e2e`（无 `-m e2e` 则跳过）

## Test Runners

| 脚本 | 模块 | 命令 | 基线 |
|------|------|------|------|
| `scripts/test-agent_mcp.sh` | agent_mcp | `cd zchat-channel-server && uv run pytest tests/unit/test_agent_mcp.py -v` | 15 passed |
| `scripts/test-channel_server.sh` | channel_server | `... test_router test_routing test_routing_watcher test_plugin_registry -v` | 47 passed |
| `scripts/test-feishu_bridge.sh` | feishu_bridge | `... test_outbound_router test_group_manager test_routing_reader test_sender test_parsers test_client_extended test_card_action test_visibility_router -v` | 67 passed |
| `scripts/test-plugins.sh` | plugins | `... test_mode_plugin test_sla_plugin test_resolve_plugin test_audit_plugin test_activation_plugin test_csat_plugin -v` | 50 passed |
| `scripts/test-all.sh` | (全量) | `cd zchat-channel-server && uv run pytest tests/ -v` | **191 passed** (179 unit + 12 e2e) |
| `scripts/test-e2e.sh` | (E2E only) | `cd zchat-channel-server && uv run pytest tests/e2e/ -v -m e2e` | 12 passed |

## Artifact 交互

### 有 Skill 6 时（推荐）

```bash
# 查已驳回的 cs-eval-doc
bash ~/.claude/skills/artifact-registry/scripts/query.sh \
  --project-root /home/yaosh/projects/zchat --type eval-doc --id-prefix cs- --status archived

# 注册新 cs-artifact（ID 必须 cs- 前缀）
bash ~/.claude/skills/artifact-registry/scripts/register.sh \
  --project-root /home/yaosh/projects/zchat \
  --type eval-doc --name "CS 新讨论" --producer skill-5 \
  --path .artifacts/eval-docs/eval-cs-xxx.md --status draft

# 更新状态
bash ~/.claude/skills/artifact-registry/scripts/update-status.sh \
  --project-root /home/yaosh/projects/zchat --id cs-eval-doc-xxx --status archived
```

### 无 Skill 6 时（fallback）

- 查询：`ls .artifacts/eval-docs/ | grep ^eval-cs-`
- 创建：写入对应子目录带 YAML frontmatter（`type / producer / status / created_at`）
- 更新：编辑 frontmatter

**规矩**：所有 CS 相关 artifact ID 必须以 `cs-` 前缀，便于和主库 / protocol 的条目分隔。

## 自验证记录

2026-04-22 Step 8 自验证 — 每个 test-runner 实际跑过对照基线。

| test-runner | 基线结果 | 验证结果 | 匹配 |
|-------------|---------|---------|------|
| test-agent_mcp.sh | 15 passed | 15 passed | ✅ |
| test-channel_server.sh | 47 passed | 47 passed | ✅ |
| test-feishu_bridge.sh | 67 passed | 67 passed | ✅ |
| test-plugins.sh | 50 passed | 50 passed | ✅ |
| test-all.sh (unit + e2e) | 191 passed | 191 passed | ✅ |
| test-e2e.sh (仅 e2e) | 12 passed | 12 passed | ✅ |

## 环境依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| uv | 必需 | 依赖管理 |
| Python 3.12+ | 必需 | CS 运行时 |
| zchat-protocol | 必需 | submodule，提供 irc_encoding + ws_messages |
| ergo 或外部 IRC server | 必需（运行时）| CS 要连 IRC |
| lark-oapi ≥1.4 | 必需（运行 feishu_bridge 时）| 飞书 WSS + REST SDK |
| 飞书 app credential | 必需（运行 bridge 时）| `~/.zchat/projects/<proj>/credentials/<bot>.json` |
| pytest + pytest-asyncio + pytest-order + pytest-timeout | 必需（测试）| 见 pyproject.toml [test-deps] |

## 关联文档

主库 `docs/guide/` 相关章节：
- **007-plugin-guide.md** — Plugin 机制 + 6 个官方 plugin 实现剖析 + 外部系统对接示例（Shopify exporter）
- 001 architecture — 完整三层架构图 + 12 步消息生命周期
- 003 e2e-pre-release-test — 真机验收 TC（含 CS 部分）
- 006 routing-config — routing.toml schema（bridge + CS 共用）

CS 自身：
- `instructions.md` — MCP server Claude Code 默认加载的指令
- `docs/dev/` — 架构 / IRC 事件 / 测试层（CS repo 自己的）
- `docs/discuss/` — 设计讨论（CS repo 自己的）
