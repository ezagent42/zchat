# zchat

多 Agent 协作系统：IRC ↔ Claude Code (MCP)。

## 术语

遵循 IRC / WeeChat 命名惯例：
- **channel** — IRC 频道（如 `#general`）
- **private** / **DM** — IRC PRIVMSG 一对一消息
- **nick** — IRC 昵称

## 架构

四个组件，通过 IRC 协议连接：
- `zchat-channel-server/` — MCP server 桥接 IRC ↔ Claude Code（git submodule → `ezagent42/claude-zchat-channel`）
- `zchat/cli/` — CLI 工具，管理 agent 生命周期（create/stop/list/restart）
- `zchat-protocol/` — 协议规范（git submodule → `ezagent42/zchat-protocol`）
- `weechat-zchat-plugin/` — WeeChat Python script（git submodule → `ezagent42/weechat-zchat-plugin`）
- IRC server — 任意 IRC server（本地 ergo、公司内网、Libera.Chat 等）

```
┌──────────────┐  ┌──────────────┐
│ alice        │  │ bob          │   ← 任意 IRC 客户端
│ (WeeChat     │  │ (irssi)      │
│  +zchat.py)  │  │              │
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

zchat project create local            # 创建项目
zchat irc daemon start                # 启动 ergo IRC server
zchat irc start                       # 启动 WeeChat
zchat agent create agent0             # 创建 agent
zchat agent send agent0 "..."         # 向 agent 发送文本
zchat agent list                      # 列出所有 agent
zchat agent stop helper               # 停止 agent
zchat agent restart helper            # 重启 agent
zchat shutdown                        # 停止所有 agent

uv run pytest tests/unit/ -v                                              # CLI unit 测试
cd zchat-protocol && uv run pytest tests/ -v                              # Protocol 测试
cd zchat-channel-server && uv run pytest tests/ -v                        # Channel server 测试
uv run pytest tests/e2e/ -v -m e2e                                        # E2E 测试（需要 ergo + tmux）
```

### 配置

项目配置存储在 `~/.zchat/projects/<name>/config.toml`：
```toml
[irc]
server = "127.0.0.1"
port = 6667
tls = false
password = ""

[agents]
default_channels = ["#general"]
username = ""  # 空则从 $USER 读取
env_file = ""  # 代理/API 密钥环境文件路径（可选）
claude_args = ["--permission-mode", "bypassPermissions", "--dangerously-load-development-channels", "server:zchat-channel"]
mcp_server_cmd = ["zchat-channel"]  # 开发时可用 ["uv", "run", "--project", "<path>", "zchat-channel"]
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
- 系统消息（stop/join/status）：IRC PRIVMSG + `__zchat_sys:` 前缀 + JSON payload
- Presence：IRC 原生 JOIN/PART/QUIT

### WeeChat 插件

`weechat-zchat-plugin/zchat.py` 提供：
- `/agent create|stop|list|restart|send` — 在 WeeChat 内管理 agent
- 系统消息渲染 — `__zchat_sys:` 消息转换为可读格式
- Agent 状态栏 — 显示在线/离线状态
- 启动时自动加载（通过 irc_manager）

### 添加 MCP Tool

1. 在 `server.py` 的 `register_tools()` 中添加 `@server.list_tools()` entry 和 `@server.call_tool()` handler
2. 在模块顶层实现 `_handle_<toolname>()` 函数
3. 在 `zchat-channel-server/tests/test_channel_server.py` 添加测试

### 关键约束

- Channel MCP 需要 `--dangerously-load-development-channels` flag
- `{username}-agent0` 是 primary agent — 由 `zchat agent create agent0` 创建
- Agent 的 IRC nick 必须符合 RFC 2812（无 `:` 等特殊字符）
- channel-server 运行在 IRC reactor 线程中，通过 asyncio.Queue 桥接到 MCP
- tmux session 名为 `zchat-{project}`（如 `zchat-local`），避免多项目冲突

### Git Submodules

三个组件是独立仓库，通过 git submodule 引入：
- `git clone --recurse-submodules` 获取完整代码
- `git submodule update --init` 初始化子模块
- Protocol import：`from zchat_protocol.naming import scoped_name`（注意下划线）
- 每个子模块有独立的 `pyproject.toml`、venv 和测试
