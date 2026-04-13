---
type: coverage-matrix
id: coverage-matrix-002
status: draft
producer: skill-0
created_at: "2026-04-10"
related:
  - bootstrap-report-001
---

# Coverage Matrix: zchat

## 概览

| 指标 | 值 |
|------|-----|
| 总模块数 | 15 (13 核心 + channel-server + protocol) |
| 代码测试覆盖模块 | 14/15 (doctor 无测试) |
| 操作 E2E 覆盖流程 | 9/24 |
| 已知代码 bug | 7 (1 unit + 4 e2e timeout + 2 protocol) |

## 代码测试覆盖

| 模块 | 测试文件 | 测试命令 | 结果 | 覆盖状态 |
|------|---------|---------|------|---------|
| agent_manager | test_agent_manager.py, test_agent_focus_hide.py | `uv run pytest tests/unit/test_agent_manager.py tests/unit/test_agent_focus_hide.py -v` | 19/19 passed | ✅ covered |
| irc_manager | test_irc_check.py | `uv run pytest tests/unit/test_irc_check.py -v` | 3/4 (1 fail: WSL2 net) | ⚠️ 1 bug |
| auth | test_auth.py | `uv run pytest tests/unit/test_auth.py -v` | 15/15 passed | ✅ covered |
| ergo_auth_script | test_ergo_auth_script.py | `uv run pytest tests/unit/test_ergo_auth_script.py -v` | 4/4 passed | ✅ covered |
| project | test_project.py, test_project_create_params.py | `uv run pytest tests/unit/test_project.py tests/unit/test_project_create_params.py -v` | 22/22 passed | ✅ covered |
| layout | test_layout.py | `uv run pytest tests/unit/test_layout.py -v` | 8/8 passed | ✅ covered |
| zellij | test_zellij_helpers.py | `uv run pytest tests/unit/test_zellij_helpers.py -v` | 22/22 passed | ✅ covered |
| config_cmd | test_config_cmd.py | `uv run pytest tests/unit/test_config_cmd.py -v` | 11/11 passed | ✅ covered |
| defaults | test_defaults.py | `uv run pytest tests/unit/test_defaults.py -v` | 6/6 passed | ✅ covered |
| paths | test_paths.py | `uv run pytest tests/unit/test_paths.py -v` | 24/24 passed | ✅ covered |
| runner | test_runner.py | `uv run pytest tests/unit/test_runner.py -v` | 16/16 passed | ✅ covered |
| template_loader | test_template_loader.py | `uv run pytest tests/unit/test_template_loader.py -v` | 8/8 passed | ✅ covered |
| migrate | test_migrate.py | `uv run pytest tests/unit/test_migrate.py -v` | 4/4 passed | ✅ covered |
| update | test_update.py | `uv run pytest tests/unit/test_update.py -v` | 19/19 passed | ✅ covered |
| doctor | (无测试文件) | - | - | ❌ no tests |
| app | test_list_commands.py, test_plugin_integration.py | `uv run pytest tests/unit/test_list_commands.py tests/unit/test_plugin_integration.py -v` | 11/11 passed | ✅ covered |
| channel-server | test_channel_server.py | `cd zchat-channel-server && uv run pytest tests/ -v` | 12/12 passed | ✅ covered |
| protocol | test_naming.py, test_sys_messages.py | `cd zchat-protocol && uv run pytest tests/ -v` | 7/9 (2 fail: scoped_name bug) | ⚠️ 2 bugs |

## 操作 E2E 覆盖

所有 E2E 测试已正常执行（0 env error, 0 env skip）。

| 用户流程 | E2E 测试 | 证据类型 | 结果 | 覆盖状态 |
|---------|---------|---------|------|---------|
| WeeChat 连接到 IRC | test_weechat_connects | IrcProbe WHOIS | passed | ✅ covered |
| 创建 agent 并加入 IRC | test_agent_joins_irc | IrcProbe WHOIS | passed | ✅ covered |
| Agent 向频道发消息 (MCP reply) | test_agent_send_to_channel | IrcProbe wait_for_message | **failed** (30s timeout) | ⚠️ MCP 超时 |
| @mention 触发 agent 回复 | test_mention_triggers_reply | IrcProbe wait_for_message | **failed** (30s timeout) | ⚠️ MCP 超时 |
| 创建第二个 agent | test_second_agent | IrcProbe WHOIS + message | **failed** (30s timeout) | ⚠️ MCP 超时 |
| Agent 间通信 (@mention) | test_agent_to_agent | IrcProbe wait_for_message | **failed** (30s timeout) | ⚠️ MCP 超时 |
| 用户间对话 (alice ↔ bob) | test_alice_bob_conversation | IrcProbe dual probe | passed | ✅ covered |
| 停止 agent | test_agent_stop | IrcProbe wait_for_nick_gone | passed | ✅ covered |
| 全局 shutdown | test_shutdown | IrcProbe wait_for_nick_gone | passed | ✅ covered |
| Zellij tab 创建/关闭 | test_tab_create_exists_close | zellij tab_exists | passed | ✅ covered |
| Zellij pane 发送/读取 | test_send_and_read | zellij dump_screen | passed | ✅ covered |
| 创建项目 | (无) | - | - | ❌ not covered |
| 列出/删除/切换项目 | (无) | - | - | ❌ not covered |
| IRC daemon 启停 | (无) | - | - | ❌ not covered |
| OIDC 登录 | (无) | - | - | ❌ not covered |
| 本地模式登录 | (无) | - | - | ❌ not covered |
| 环境诊断 (doctor) | (无) | - | - | ❌ not covered |
| 模板管理 | (无) | - | - | ❌ not covered |
| 配置管理 | (无) | - | - | ❌ not covered |
| 版本更新 | (无) | - | - | ❌ not covered |
| Agent 重启 | (无) | - | - | ❌ not covered |
| Agent focus/hide | (无) | - | - | ❌ not covered |
| Agent 发送文本 (send) | (无，E2E 中 send 仅作为 setup 步骤) | - | - | ❌ not covered |

## Soft-dependency 受限覆盖

Step 4 已确保所有 hard dependency 的测试正常执行。以下仅记录 soft dependency 的影响：

| 测试 | 所需 soft dependency | 说明 |
|------|---------------------|------|
| tests/pre_release/ | asciinema | pre-release 录制功能，不影响 E2E |
| (无其他) | docker | 当前无测试依赖 docker |

## E2E 缺口清单

13 个用户流程缺少操作 E2E，按优先级排序：

1. **创建项目** — `zchat project create local`
2. **IRC daemon 启停** — `zchat irc daemon start/stop`
3. **Agent MCP 消息** — agent 通过 MCP reply tool 发消息（当前 E2E fail 因超时）
4. **@mention 回复** — @agent 触发自动回复（当前 E2E fail 因超时）
5. **OIDC 登录** — `zchat auth login`
6. **本地登录** — `zchat auth login --method local`
7. **环境诊断** — `zchat doctor`
8. **模板管理** — `zchat template list/show/set/create`
9. **配置管理** — `zchat config get/set/list`
10. **项目列表/删除/切换** — `zchat project list/remove/use`
11. **版本更新** — `zchat update/upgrade`
12. **Agent 重启** — `zchat agent restart`
13. **Agent focus/hide** — `zchat agent focus/hide`

## 已知代码 Bug

1. **test_unreachable_server_raises** (unit): WSL2 网络环境下 192.0.2.1 连接被快速拒绝而非超时
2. **test_agent_send_to_channel** (e2e): Claude Code MCP reply 在 30s 内未完成
3. **test_mention_triggers_reply** (e2e): @mention 后 agent 在 30s 内未回复
4. **test_second_agent** (e2e): agent1 MCP 消息 30s 超时
5. **test_agent_to_agent** (e2e): agent 间 MCP 通信 30s 超时
6. **test_scoped_name_no_double_prefix** (protocol): `scoped_name("alice-helper", "alice")` 返回 `"alice-alice-helper"` 而非 `"alice-helper"`
7. **test_scoped_name_different_prefix** (protocol): `scoped_name("bob-helper", "alice")` 返回 `"alice-bob-helper"` 而非 `"bob-helper"`
