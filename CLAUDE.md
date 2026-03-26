# WeeChat-Claude

多 Agent 协作系统：IRC ↔ Claude Code (MCP)。

## 术语

遵循 IRC / WeeChat 命名惯例：
- **channel** — IRC 频道（如 `#general`）
- **private** / **DM** — IRC PRIVMSG 一对一消息
- **nick** — IRC 昵称

## 架构

三个组件，通过 IRC 协议连接：
- `weechat-channel-server/` — MCP server 桥接 IRC ↔ Claude Code（每个 agent 一个实例）
- `wc-agent/` — 独立 CLI 工具，管理 agent 生命周期（create/stop/list/restart）
- IRC server — 任意 IRC server（本地 ergo、公司内网、Libera.Chat 等）

**零 WeeChat 自定义代码。** 用户使用 WeeChat 原生 IRC 功能聊天，任何 IRC 客户端都可以。

```
┌──────────────┐  ┌──────────────┐
│ alice        │  │ bob          │   ← 任意 IRC 客户端
│ (WeeChat)    │  │ (irssi)      │
└──────┬───────┘  └──────┬───────┘
       │ IRC             │ IRC
       ▼                 ▼
┌─────────────────────────────┐
│ IRC Server (ergo / 公开)     │
└──┬─────────────┬────────────┘
   │ IRC         │ IRC
   ▼             ▼
┌────────┐    ┌────────┐
│agent0  │    │agent1  │
│(channel│    │(channel│
│-server)│    │-server)│
└──┬─────┘    └──┬─────┘
   │MCP          │MCP
   ▼             ▼
 claude        claude
```

## Agent 命名

- 分隔符：`-`（IRC RFC 2812 禁止 `:` 在 nick 中）
- 格式：`{username}-{agent_name}`，如 `alice-agent0`、`alice-helper`
- `scoped_name("helper", "alice")` → `"alice-helper"`

## 开发

### 常用命令

```bash
./start.sh ~/workspace                # 启动（ergo + agent0 + WeeChat）
./stop.sh                             # 停止 tmux session

wc-agent project create local         # 创建项目
wc-agent irc daemon start             # 启动 ergo IRC server
wc-agent irc start                    # 启动 WeeChat
wc-agent agent create agent0          # 创建 agent
wc-agent agent send agent0 "..."      # 向 agent 发送文本
wc-agent agent list                   # 列出所有 agent
wc-agent agent stop helper            # 停止 agent
wc-agent agent restart helper         # 重启 agent
wc-agent shutdown                     # 停止所有 agent

cd weechat-channel-server && uv run python -m pytest ../tests/unit/ -v   # Unit 测试
bash tests/e2e/e2e-test.sh           # E2E 测试（需要 ergo）
```

### 配置

项目配置存储在 `~/.wc-agent/projects/<name>/config.toml`：
```toml
[irc]
server = "127.0.0.1"
port = 6667
tls = false
password = ""

[agents]
default_channels = ["#general"]
username = ""  # 空则从 $USER 读取
```

### 依赖

- `irc` ≥20.0 — IRC 客户端库（channel-server）
- `mcp[cli]` ≥1.2.0 — MCP server 框架
- `uv` — Python 依赖管理
- `tmux` — Session/pane 管理
- `ergo` — 本地 IRC server（可选，也可用公开 IRC server）

### 消息协议

- 用户聊天：标准 IRC PRIVMSG
- @mention agent：`@alice-agent0 question` → channel-server 检测并转发给 Claude
- 系统消息（stop/join/status）：IRC PRIVMSG + `__wc_sys:` 前缀 + JSON payload
- Presence：IRC 原生 JOIN/PART/QUIT

### 添加 MCP Tool

1. 在 `server.py` 的 `register_tools()` 中添加 `@server.list_tools()` entry 和 `@server.call_tool()` handler
2. 在模块顶层实现 `_handle_<toolname>()` 函数
3. 在 `tests/unit/test_channel_server_irc.py` 添加测试

### 关键约束

- Channel MCP 需要 `--dangerously-load-development-channels` flag
- `{username}-agent0` 是 primary agent — 由 `wc-agent agent create agent0` 创建
- Agent 的 IRC nick 必须符合 RFC 2812（无 `:` 等特殊字符）
- channel-server 运行在 IRC reactor 线程中，通过 asyncio.Queue 桥接到 MCP
