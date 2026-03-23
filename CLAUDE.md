# WeeChat-Claude

多 Agent 协作系统：WeeChat ↔ Zenoh P2P ↔ Claude Code (MCP)。

## 术语

遵循 WeeChat 命名惯例：
- **channel**（不是 "room"）— 群聊 buffer（`localvar_type = "channel"`）
- **private**（不是 "DM"）— 一对一 buffer（`localvar_type = "private"`）
- **buffer** — WeeChat 通用消息容器

## 架构

四个可组合组件，通过 Zenoh topic 约定连接：
- `weechat-zenoh/weechat-zenoh.py` — WeeChat P2P 聊天插件（详见 [docs/dev/weechat-zenoh.md](docs/dev/weechat-zenoh.md)）
- `weechat-channel-server/` — MCP server 桥接 Claude Code ↔ Zenoh（详见 [docs/dev/channel-server.md](docs/dev/channel-server.md)）
- `weechat-agent/weechat-agent.py` — Agent 生命周期管理（详见 [docs/dev/agent.md](docs/dev/agent.md)）
- `zenohd` — 本地 Zenoh 路由（start.sh 自动启动，跨 session 持续运行）

## Zenoh Topics

- `wc/channels/{channel_id}/messages` — channel pub/sub
- `wc/channels/{channel_id}/presence/{nick}` — channel presence (liveliness)
- `wc/private/{sorted_pair}/messages` — private pub/sub（按字母序排列，如 `alice_bob`）
- `wc/presence/{nick}` — 全局在线状态

消息格式：JSON `{id, nick, type, body, ts}`

## 开发

### 常用命令

```bash
./start.sh ~/workspace username    # 完整系统启动（tmux + username:agent0 + weechat）
./stop.sh                          # 停止 tmux session（zenohd 保持运行）
./stop.sh --all                    # 停止 tmux session + zenohd
pytest tests/unit/                 # Unit 测试（mock Zenoh，快）
pytest -m integration tests/       # Integration 测试（真实 Zenoh peer）
```

### 依赖

- `eclipse-zenoh` ≥1.0.0 — P2P 消息
- `mcp[cli]` ≥1.2.0 — MCP server 框架
- `uv` — Python 依赖管理
- `tmux` — Session/pane 管理

### 测试

详见 [docs/dev/testing.md](docs/dev/testing.md)

### 添加 MCP Tool

1. 在 `server.py` 的 `register_tools()` 中添加 `@server.list_tools()` entry 和 `@server.call_tool()` handler
2. 在模块顶层实现 `_handle_<toolname>()` 函数
3. 在 `tests/unit/test_tools.py` 添加测试

详见 [docs/dev/channel-server.md](docs/dev/channel-server.md#添加-mcp-tool)

### 关键约束

- Channel MCP 需要 `--dangerously-load-development-channels` flag
- `{username}:agent0` 是 primary agent — 由 start.sh 创建，不能通过 `/agent stop` 停止
- Agent 名称带用户前缀：`alice:agent0`、`alice:helper`（分隔符：`:`）
- WeeChat callback 不能阻塞 — 使用 deque + timer 实现异步
