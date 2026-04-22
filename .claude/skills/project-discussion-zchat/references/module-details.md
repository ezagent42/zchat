# Module Details · zchat (main repo)

> 从 `.artifacts/bootstrap/module-reports/*.json` 汇总生成。每个模块给：职责、关键接口、依赖、file:line evidence、对应用户流程。

## agent_manager

**职责**：AgentManager — create/stop/restart/list/send Claude Code agents；每个 agent 绑定一个 zellij tab + workspace dir；通过 state.json + `.ready` marker 跟踪生命周期。

**关键接口**：
- `AgentManager` (class) — 主门面
- `DEFAULT_STATE_FILE` — state 持久化路径

**依赖**：
- `zellij`（tab 操作）
- `irc_manager.check_irc_connectivity`（启动前 probe）
- `runner`（resolve_runner / render_env / _parse_env_file / _resolve_template_dir / _load_template_toml）
- `auth`（get_credentials, _global_auth_dir）
- `zchat_protocol.naming`（scoped_name, AGENT_SEPARATOR）

**Evidence**：`zchat/cli/agent_manager.py:56` / `:88` / `:209` / `:248` / `:310`

**对应用户流程**：
- 创建 agent：`zchat agent create <name>`
- 停止 agent：`zchat agent stop <name>`
- 重启 agent：`zchat agent restart <name>`

## app

**职责**：Typer CLI 根入口——声明所有 sub-apps (project/irc/agent/auth/template/config/channel/bot/audit/setup) 并把命令连接到对应 manager 类。

**关键接口**：
- `app`、`project_app`、`irc_app`、`irc_daemon_app`、`agent_app`、`setup_app`、`template_app`、`auth_app`、`config_app`、`channel_app`、`bot_app`
- 全部 `cmd_*` 函数（Typer commands）

**依赖**：project / agent_manager / irc_manager / zellij / layout / auth / routing / template_loader / config_cmd / defaults / doctor / update / audit_cmd / paths / typer。

**Evidence**：`zchat/cli/app.py`（~1800 行）

**对应用户流程**：全部 CLI 入口 (`zchat <command>`)。

## auth

**职责**：OIDC device-code 流程做用户身份 + IRC SASL；凭证存 `~/.zchat/auth.json`。`ergo_auth_script.py` 是独立子进程，通过 stdin/stdout JSON 和 ergo 的 auth-script 功能通信。

**关键接口**：
- auth.py: `get_username`、`save_token`、`load_cached_token`、`device_code_flow`、`refresh_token_if_needed`、`get_credentials`、`discover_oidc_endpoints`、`_global_auth_dir`、`_sanitize_irc_nick`、`_extract_username`
- ergo_auth_script.py: `validate_credentials`（作为子进程调用）

**依赖**：
- `httpx`（OIDC HTTP 调用）
- `paths.zchat_home`
- `segno`（可选，QR 二维码渲染）

**Evidence**：`zchat/cli/auth.py`、`zchat/cli/ergo_auth_script.py`

**对应用户流程**：
- 登录：`zchat auth login`
- 查 token：`zchat auth status`
- ergo 验 nick/pwd：由 ergo daemon fork 出子进程

## doctor_update

**职责**：3 个命令合并——环境诊断 (`doctor`)、自升级 (`update`)、audit.json 只读 CLI (`audit_cmd`)。`audit_cmd` 是 admin-agent 面向的只读接口，读 CS 产出的 audit artifact。

**关键接口**：
- doctor.py: `run_doctor`、`setup_weechat`
- update.py: `load_update_state`、`save_update_state`、`should_check_today`、`check_for_updates`、`run_upgrade`、`UPDATE_STATE_FILE`
- audit_cmd.py: `audit_app`（Typer sub-app）

**依赖**：
- `subprocess`、`urllib.request`
- `paths.update_state`
- `project`（list_projects, load_project_config, resolve_project）
- `typer`

**Evidence**：`zchat/cli/doctor.py`、`update.py`、`audit_cmd.py`

**对应用户流程**：
- `zchat doctor` — 诊断环境依赖
- `zchat update check/run` — 自升级
- `zchat audit status/report --json` — admin agent 读运营数据

## irc_manager

**职责**：IrcManager — 管理本地 ergo IRC daemon（per-project data dir） + WeeChat zellij tab；构造 WeeChat 自动连接命令；有凭证时注入 OIDC auth-script。

**关键接口**：
- `IrcManager` (class)
- `check_irc_connectivity`（独立函数，startup probe）

**依赖**：
- `zellij`（tab 操作）
- `auth`（get_credentials, get_username, discover_oidc_endpoints, load_cached_token, _global_auth_dir）
- 外部二进制：`ergo`、`weechat`

**Evidence**：`zchat/cli/irc_manager.py`

**对应用户流程**：
- `zchat irc daemon start/stop/status`
- `zchat irc start`（起 WeeChat tab）
- WSL2 proxy 重写：`_rewrite_proxy_for_wsl2`

## project

**职责**：project/config/paths/defaults 汇合层——CRUD 在 `~/.zchat/projects/<name>/config.toml`；所有路径中心解析；全局 `config.toml` 带 `[servers.*]` + `[update]`；legacy tmux→zellij migrator。

**关键接口**：
- project.py: `project_dir`、`project_state`、`project_config`、`projects_dir`、`create_project_config`、`list_projects`、`get_default_project`、`set_default_project`、`resolve_project`、`load_project_config`、`remove_project`、`state_file_path`、`set_config_value`、`normalize_channel_name`
- paths.py: `zchat_home`、`plugins_dir`、`templates_dir`、`global_config_path`、`auth_file`、`update_state`、`default_project_file`、`zellij_layout_dir`、`agent_workspace`、`agent_ready_marker`、`legacy_agent_state`、`ergo_data_dir`、`weechat_home`

**依赖**：
- `tomllib`、`tomli_w`
- `routing.init_routing`（create_project_config 调用）

**Evidence**：`zchat/cli/project.py`、`paths.py`、`defaults.py`、`config_cmd.py`、`migrate.py`

**对应用户流程**：
- `zchat project create/use/list/remove <name>`
- `zchat config set/get`
- tmux→zellij 迁移由 migrate.py 在首次启动自动跑

## routing

**职责**：读写 `routing.toml` —— V6 动态运行时配置，包含 `[bots.*]` 和 `[channels.*]`。由 CLI (bot/channel/agent) 写，由 channel-server 和 bridge 消费。

**关键接口**：
- `routing_path`、`load_routing`、`save_routing`、`init_routing`
- `add_bot`、`list_bots`、`remove_bot`、`bot_exists`
- `add_channel`、`list_channels`、`channel_exists`、`remove_channel`

**依赖**：
- `tomllib`、`tomli_w`

**Evidence**：`zchat/cli/routing.py`

**对应用户流程**：
- `zchat bot add/list/remove`
- `zchat channel create/list/remove`
- 路由热加载由 CS 的 routing_watcher 监控 mtime

## runner

**职责**：template/runner 解析 + `.env` 渲染——找 template dir（用户 > builtin）→ 加载 template.toml → 用 `{{placeholders}}` 渲染 `.env.example` → 覆盖用户 `.env`。`runner.py` 是 V6 API；`template_loader.py` 是 legacy/更简单的 API，仍被 CLI import。

**关键接口**：
- runner.py: `RunnerNotFoundError`、`resolve_runner`、`render_env`、`list_runners`、`_parse_env_file`、`_resolve_template_dir`、`_load_template_toml`
- template_loader.py: `TemplateNotFoundError`、`resolve_template_dir`、`load_template`、`render_env`、`get_start_script`、`list_templates`

**依赖**：
- `dotenv.dotenv_values`
- `tomllib`
- `paths.templates_dir`

**Evidence**：`zchat/cli/runner.py`、`zchat/cli/template_loader.py`

**对应用户流程**：由 agent_manager 在启动 agent 时内部调用，用户不直接触发。

## templates

**职责**：内置 agent 模板——5 个 template（`claude/`、`fast-agent/`、`deep-agent/`、`admin-agent/`、`squad-agent/`）。每个 template dir 含：
- `template.toml` — name/description/hooks.pre_stop
- `start.sh` — bash 启动脚本
- `.env.example` — placeholder env template
- `soul.md` — 人格 + 指令
- 可选 `skills/*/SKILL.md`

**数据不是代码**——由 runner.py / template_loader.py 加载。

**关键接口**：
- 模板被 `zchat template list/show/set/create` 消费
- 每个模板暴露 env vars: `AGENT_NAME`、`IRC_SERVER`、`IRC_PORT`、`IRC_CHANNELS`、`IRC_TLS`、`IRC_PASSWORD`、`WORKSPACE`、`ZCHAT_PROJECT_DIR`、`IRC_AUTH_TOKEN`、`CHANNEL_PKG_DIR`、`MCP_SERVER_CMD`

**依赖**：
- runner / template_loader（解析 + 渲染）
- agent_manager（env context + spawn）
- 外部：`bash`、`jq`、`claude`

**Evidence**：`zchat/cli/templates/`（33 个文件跨 5 个模板）

**对应用户流程**：
- `zchat template list` — 列所有可用
- `zchat template show <name>` — 查看 soul + skills
- 新模板：`zchat template create <name>` 从 `claude/` 复制

## tests

**职责**：三层测试套件——unit（纯逻辑，29 文件）、e2e（pytest 驱动，通过 `uv run python -m zchat.cli` 调用，需 ergo + zellij，`@pytest.mark.e2e`）、pre_release（CLI walkthrough 脚本，asciinema 录制 + 每步 pytest 文件，产 `reports/*.json` + `reports/*.md`）。

**关键接口**：
- pytest 测试发现：`tests/unit/`、`tests/e2e/`、`tests/pre_release/`
- Fixture/helper 在 `tests/shared/`

**依赖**：
- `pytest`、`pytest-asyncio`、`pytest-order`
- `zchat.cli.*`（subject under test）
- `ergo`、`zellij`、`weechat`（e2e only）
- `asciinema`、`agg`（pre_release only）

**Evidence**：`tests/` 64 个文件

**对应用户流程**：
- `uv run pytest tests/unit/ -v` — 单测（304 passed baseline）
- `uv run pytest tests/e2e/ -v -m e2e` — E2E（31 collected，需服务）
- `./tests/pre_release/walkthrough.sh` — 验收录制

## zellij

**职责**：`zellij action` subprocess 的薄包装 + KDL layout 生成器。由 AgentManager / IrcManager / app.py 用来管理 tabs、panes、sessions、layouts。

**关键接口**：
- zellij.py: `ensure_session`、`session_exists`、`new_tab`、`close_tab`、`list_tabs`、`list_panes`、`send_command`、`send_keys`、`dump_screen`、`subscribe_pane`、`tab_exists`、`get_pane_id`、`go_to_tab`、`switch_session`、`kill_session`
- layout.py: `generate_layout`、`write_layout`

**依赖**：
- `subprocess`
- `paths`（for plugins_dir）
- 外部 `zellij` 二进制

**Evidence**：`zchat/cli/zellij.py`、`layout.py`

**对应用户流程**：
- agent tab：`zellij.new_tab`（由 agent_manager 间接触发）
- weechat tab：`zellij.new_tab("chat", command=weechat_cmd)`
- 完整 `zchat up` layout：由 `generate_layout` 写 `layout.kdl`

## 附：Submodules

### zchat-channel-server

独立 repo，含：
- `src/channel_server/` — 消息总线（router + irc_connection + ws_server + plugin 框架）
- `src/plugins/` — 6 个官方 plugin（mode/sla/resolve/audit/activation/csat）
- `src/feishu_bridge/` — 飞书 WSS 入站 + REST 出站 + supervisor 卡片+thread
- `agent_mcp.py` — MCP stdio server 给 Claude Code agent 用

测试：`cd zchat-channel-server && uv run pytest tests/ -v` → 540 passed（V6 finalize 基线）

有独立 Skill 1：`.claude/skills/project-discussion-channel-server/`

### zchat-protocol

独立 repo，零外部依赖：
- `irc_encoding.py` — `__msg:<uuid>:<text>` / `__side:` / `__edit:` / `__zchat_sys:<json>` 前缀编解码
- `ws_messages.py` — bridge↔CS WebSocket schema：build_message / build_event / build_register / parse
- `naming.py` — scoped_name + AGENT_SEPARATOR（兼容 IRC RFC 2812）

测试：`cd zchat-protocol && uv run pytest tests/ -v`
