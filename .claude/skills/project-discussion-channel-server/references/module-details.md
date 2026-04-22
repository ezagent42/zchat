# Module Details · zchat-channel-server

> 从 `zchat-channel-server/.artifacts/bootstrap/module-reports/*.json` 汇总（2026-04-22 V6 finalize 后）。6 个模块每个给：职责、关键接口、依赖、file:line evidence、对应用户流程。

## agent_mcp

**职责**：独立 MCP stdio 代理进程。每个 Claude Code agent 运行一个 `agent_mcp` 实例，为 Claude 暴露 4 个 MCP tools (reply / join_channel / list_peers / run_zchat_cli) + 订阅 IRC pubmsg/privmsg/sys 事件并作为 `JSONRPCNotification` 注入到 Claude Code (`method=notifications/claude/channel`)。只在收到包含 `@AGENT_NAME` 的 pubmsg 或任意 privmsg/sys 时触发注入。进程通过 stdio 与 Claude Code 宿主通信，单独 IRC reactor 线程处理传输。

**关键接口**：
- `entry_point()` — setuptools entry: `zchat-agent-mcp`
- 环境变量：`AGENT_NAME / IRC_SERVER / IRC_PORT / IRC_CHANNELS / IRC_TLS / IRC_AUTH_TOKEN`
- MCP tools：`reply / join_channel / list_peers / run_zchat_cli`

**依赖**：
- `mcp` (Server, stdio, Tool, TextContent, JSONRPCNotification)
- `anyio` (task_group)
- `irc.client` / `irc.connection`
- `zchat_protocol.irc_encoding`（encode_edit / encode_msg / encode_side / parse / make_sys_payload）
- `subprocess` / `shlex`（run_zchat_cli）

**Evidence**：`agent_mcp.py`（单文件，~700 行；根目录）

**对应用户流程**：
- Claude agent reply 回 IRC：`_handle_reply` tool
- Agent 查同 channel peers：`_handle_list_peers(state["members"])`
- Claude 调 zchat CLI 做 audit/agent 管理：`_handle_run_zchat_cli`
- agent 加入新 channel：`_handle_join_channel`

## channel_server

**职责**：V4 核心路由引擎。纯基础设施层：routing.toml 加载 + 热更新 + IRC 长连接 + WebSocket bridge 接入 + Plugin 框架 + WS↔IRC 双向翻译。**不含业务语义**，所有业务扩展通过 plugin 挂载。进程入口 `__main__._main()`，启动顺序：load_routing → PluginRegistry → WSServer → IRCConnection → Router → **`plugin_loader.load_plugins`**（V7，config-driven 自动发现 + register 6 个官方 plugin） → wire callbacks → auto-join channels → routing_watcher。

**关键接口**：
- `channel_server.__main__.main` — 进程入口（setuptools entry: `zchat-channel-server`）
- `channel_server.routing.load(path)` → `RoutingTable`
- `channel_server.routing.RoutingTable / Bot / ChannelRoute`
- `channel_server.router.Router`（emit_event + forward_inbound_ws/irc）
- `channel_server.plugin.BasePlugin / Plugin / PluginRegistry`
- `channel_server.plugin_loader.load_plugins / load_plugins_toml / default_plugin_data_dir`（V7）
- `channel_server.ws_server.WSServer`
- `channel_server.irc_connection.IRCConnection`
- `channel_server.routing_watcher.watch_routing`

**依赖**：
- `zchat_protocol`（irc_encoding, ws_messages）
- `irc >=20`（IRC 协议库）
- `websockets`（WS server）
- `tomllib` / `tomli`（routing.toml 解析）
- `plugins.*`（只在 `__main__` wiring 时 import，非 core 依赖）

**Evidence**：`src/channel_server/`（8 files：__init__.py / __main__.py / router.py / irc_connection.py / ws_server.py / plugin.py / routing.py / routing_watcher.py）

**对应用户流程**：
- bridge → CS WS → IRC PRIVMSG：`router.py::forward_inbound_ws` → `_handle_message` → `_route_to_irc`
- IRC PRIVMSG → CS → bridge：`router.py::forward_inbound_irc`
- `/cmd` 分派：router 查 `registry.get_handler(cmd)` → `plugin.on_command`
- emit_event 三路广播：`router.py::emit_event`（L212-240，WS + plugin registry + IRC sys）
- routing.toml 热更新：`routing_watcher.py` 轮询 mtime

## feishu_bridge

**职责**：V6 飞书 ↔ channel-server 业务桥接层。一个 bot 一个 bridge 进程，从 `routing.toml [bots.<name>]` 派生配置。飞书 WSS 长连接（`CardAwareClient`）接收 `im.message.receive_v1` / `bot.added` / `user.added|deleted` / `chat.disbanded` / `card.action.trigger` 事件；通过 `BridgeAPIClient` WS 连到 channel-server 收发 Bridge API 消息。

- 入站：消息 → `_forward` → `build_message` → WS 发给 CS
- 出站：`_on_bridge_event` → 按 `irc_encoding.parse` 的 kind 路由：
  - `msg / plain` → `send_text`
  - `side` → `reply_in_thread`
  - `edit` → reply-to-placeholder（V6+：飞书 text 消息不可 patch）
  - `sys` → 按 own / supervisor 分发

V6 支持：`supervises`（监管他人 channel → squad 卡片 + thread 镜像）、`lazy_create`（bot_added 时 CLI 懒创建 channel + agent）、CSAT 卡片 recall + resend。

**关键接口**：
- `feishu_bridge.__main__.main` — CLI entry（`--bot <name> --routing <path> --channel-server-url`）
- setuptools entry: `zchat-feishu-bridge`
- `FeishuBridge(config).start()`
- `CardAwareClient`（WSS 封装）/ `BridgeAPIClient`（WS 客户端连 CS）
- `ChannelMapper`（channel_id ↔ chat_id 双向映射）
- `OutboundRouter.route(conversation_id, *, kind, text, cs_msg_id=None)` — kw-only 签名
- `Sender`（REST API 封装：send_text / send_card / update_card / reply_in_thread / recall / get_chat_info）
- `feishu_renderer`（卡片 JSON：build_conv_card / csat_card / thank_you_card）
- `routing_reader`（独立解析 routing.toml，**不** import channel_server）

**依赖**：
- `lark-oapi >=1.4`（飞书 SDK，WSS + im.v1）
- `zchat_protocol`（irc_encoding, ws_messages）
- `websockets`（BridgeAPIClient）
- `tomllib` / `tomli`
- 运行时连接 channel-server（bridge 不 import CS 代码）
- zchat CLI（lazy_create / disband 通过 `subprocess`）

**Evidence**：`src/feishu_bridge/`（13 files）

**对应用户流程**：
- 客户消息入站：`bridge.py::_forward`
- supervise 卡片创建：`bridge.py::_handle_supervised_message`
- Help SLA 卡片更新：`bridge.py::_supervise_help_requested` / `_supervise_help_timeout`
- bot 拉入新群 → lazy_create：`bridge.py::_on_bot_added` → `subprocess run zchat channel create`
- 群解散清理：`bridge.py::_on_chat_disbanded`
- CSAT 卡片点击：`bridge.py::_on_card_action` → emit `csat_score` event

## meta

**职责**：仓库配置元数据。定义 3 个 setuptools entry script（`zchat-channel-server` / `zchat-feishu-bridge` / `zchat-agent-mcp`），wheel 打包 `src/channel_server` + `src/plugins` + `src/feishu_bridge` 三个 package，force-include `agent_mcp.py` + `instructions.md` + `.claude-plugin` + `commands`。pytest.ini 配置 `pythonpath=src` + `asyncio_mode=auto` + markers `e2e` / `prerelease`。`routing.example.toml` 提供 V6 `[bots]` / `[channels]` schema 参考。`.claude-plugin/` + `commands/` 是 Claude Code plugin 元数据（broadcast / dm / join / reply 四个 slash command 文档）。GitHub Actions `publish.yml` 跑打包发布流程。

**关键接口**：
- setuptools entry_points：`zchat-channel-server` / `zchat-feishu-bridge` / `zchat-agent-mcp`
- wheel packages：`channel_server`, `plugins`, `feishu_bridge` + force-include `agent_mcp.py`
- pytest markers：`e2e`, `prerelease`

**依赖**：
- `hatchling`（build backend）
- `uv`（dev 环境管理）
- GitHub Actions（`.github/workflows/publish.yml`）

**Evidence**：`pyproject.toml`, `pytest.ini`, `routing.example.toml`, `.claude-plugin/`, `commands/`, `.github/workflows/publish.yml`

**对应用户流程**：
- 安装：`uv tool install zchat-channel-server` / `uv tool install zchat-feishu-bridge`
- 测试配置：`pytest.ini` 决定路径 + asyncio 模式
- 发布：push tag → GH Actions 自动 wheel + publish

## plugins

**职责**：6 个官方业务 plugin，通过 `BasePlugin` 接口挂入 `PluginRegistry`。全部在 `channel_server.__main__` 初始化时注册。`plugins/` 是 **namespace package**（`extend_path`），支持与根目录 `plugins/` 合并以便部署期第三方 plugin 扩展。业务语义集中在此层：
- `mode` — copilot ↔ takeover 切换
- `resolve` — 结案命令
- `sla` — 双 timer 守护（takeover 超时 + help 超时）
- `audit` — 数据统计持久化
- `activation` — 休眠 + 回访识别
- `csat` — 评分卡片链路

**核心契约**：router 不感知这些 event name，只做分派。plugin 间禁止 import，通过 DI 注入的 `emit_event` 和 `PluginRegistry.get_plugin` 通信（csat 拿 audit 引用为此特例）。

**关键接口**：
- `plugins.mode.plugin.ModePlugin`
- `plugins.sla.plugin.SlaPlugin`
- `plugins.resolve.plugin.ResolvePlugin`
- `plugins.audit.plugin.AuditPlugin`
- `plugins.activation.plugin.ActivationPlugin`
- `plugins.csat.plugin.CsatPlugin`

**依赖**：
- `channel_server.plugin.BasePlugin`
- `zchat_protocol.irc_encoding`（sla 解析 `__side:`）
- `asyncio`（sla timer）

**Evidence**：`src/plugins/`（13 files，6 个 plugin 目录 + `__init__.py` namespace）

**对应用户流程**：完整速览见主库 `docs/guide/007-plugin-guide.md`。关键流程：
- `/hijack` / `/release` → mode plugin emit `mode_changed`
- takeover 3 分钟 → sla emit `sla_breach` + emit `/release` command
- `__side:@operator ...` → sla emit `help_requested` + 180s timer
- `/resolve` → resolve emit `channel_resolved` → csat emit `csat_request`
- 客户点 ⭐ → bridge emit `csat_score` → csat → audit.record_csat

## tests

**职责**：两层测试体系。
- **unit**：22 files, ~180 test case，无外部依赖，普遍用 `AsyncMock` / `MagicMock` stub 飞书 / IRC / WS
- **e2e**：4 files, ~12 test case，标记 `@pytest.mark.e2e`；部分要求飞书真 API 或真 CS 实例

`pytest.ini` 设 `testpaths=tests`, `pythonpath=src`, `asyncio_mode=auto`, markers `e2e` / `prerelease`。`conftest.py` 强制 `sys.path.insert(0, "src")` 以免根目录旧 plugins 污染。

**关键接口**：
- pytest 入口：`uv run pytest tests/unit/ -v` 或 `tests/e2e/ -v -m e2e`
- markers：`e2e`, `prerelease`
- `asyncio_mode=auto`（不用加 `@pytest.mark.asyncio`）

**依赖**：
- `pytest >=9`, `pytest-asyncio >=1.3`, `pytest-timeout`, `pytest-order`
- `unittest.mock` (AsyncMock / MagicMock)
- 被测：`channel_server.*` / `plugins.*` / `feishu_bridge.*` / `agent_mcp`

**Evidence**：`tests/unit/` + `tests/e2e/` + `tests/conftest.py` + `pytest.ini`

**对应用户流程**：
- 本地单元：`bash scripts/test-all.sh` → 179 passed
- 按模块拆测：`scripts/test-<module>.sh`
- E2E：`bash scripts/test-e2e.sh`（需 CS spin-up）
- 全量：`cd zchat-channel-server && uv run pytest tests/ -v` → ~540 passed (V6 finalize 基线，含 e2e)
