# 第八章：消息全链路 + 运维 + 扩展

> 预计阅读：30 分钟

## 概述

前七章分别讲解了每个组件。本章将它们串联起来：
1. 完整的消息流（端到端）
2. 系统启动/关闭流程
3. 部署与发布
4. 扩展点与未来方向

## 消息全链路

### 场景 1：频道 @mention

用户在 WeeChat 的 `#general` 频道输入 `@alice-agent0 帮我看看 main.py`

```
┌─ 用户端 ─────────────────────────────────────────────────────┐
│ WeeChat 输入：@alice-agent0 帮我看看 main.py                  │
│   ↓                                                          │
│ IRC PRIVMSG #general :@alice-agent0 帮我看看 main.py          │
└──────────────────────────────────┬────────────────────────────┘
                                   │
┌─ ergo IRC Server ────────────────┼────────────────────────────┐
│ 路由 PRIVMSG 到 #general 的所有成员                            │
│   ↓ (广播给所有频道成员)                                        │
└──────────────────────────────────┬────────────────────────────┘
                                   │
┌─ channel-server (alice-agent0) ──┼────────────────────────────┐
│ IRC 线程：on_pubmsg() 触发                                     │
│   ↓                                                          │
│ detect_mention("@alice-agent0 帮我看看 main.py", "alice-agent0")│
│   → True                                                     │
│   ↓                                                          │
│ clean_mention() → "帮我看看 main.py"                           │
│   ↓                                                          │
│ msg = {"id":"a1b2","nick":"alice","body":"帮我看看 main.py"}   │
│   ↓                                                          │
│ loop.call_soon_threadsafe(queue.put_nowait, (msg, "#general"))│
│   ↓                                                          │
│ [跨线程] asyncio Queue                                        │
│   ↓                                                          │
│ poll_irc_queue() → inject_message()                           │
│   ↓                                                          │
│ MCP JSONRPCNotification:                                      │
│   method: "notifications/claude/channel"                      │
│   params.content: "帮我看看 main.py"                           │
│   params.meta.chat_id: "#general"                             │
│   params.meta.user: "alice"                                   │
└──────────────────────────────────┬────────────────────────────┘
                                   │ MCP stdio
┌─ Claude Code ────────────────────┼────────────────────────────┐
│ 收到通知，格式化为：                                            │
│ <channel chat_id="#general" user="alice">                      │
│   帮我看看 main.py                                             │
│ </channel>                                                    │
│   ↓                                                          │
│ Claude 处理请求，读取 main.py                                   │
│   ↓                                                          │
│ 调用 MCP tool: reply(chat_id="#general", text="main.py 的内容…")│
└──────────────────────────────────┬────────────────────────────┘
                                   │ MCP tool call
┌─ channel-server ─────────────────┼────────────────────────────┐
│ _handle_reply():                                              │
│   chunks = chunk_message(text, 4000)                          │
│   for chunk in chunks:                                        │
│       connection.privmsg("#general", chunk)                   │
└──────────────────────────────────┬────────────────────────────┘
                                   │ IRC
┌─ ergo → WeeChat ─────────────────┼────────────────────────────┐
│ 用户看到 alice-agent0 在 #general 的回复                        │
└───────────────────────────────────────────────────────────────┘
```

> 引用：
> - `zchat-channel-server/server.py:112-131`（on_pubmsg）
> - `zchat-channel-server/server.py:43-60`（inject_message）
> - `zchat-channel-server/server.py:270-278`（_handle_reply）

### 场景 2：私聊

用户发送 `/msg alice-agent0 帮我 debug`

```
用户 → PRIVMSG alice-agent0 :帮我 debug
  → ergo 路由到 alice-agent0 的 channel-server
  → on_privmsg()
  → decode_sys_from_irc() → None（不是系统消息）
  → queue → inject_message(context="alice")
  → Claude 处理
  → reply(chat_id="alice", text="好的...")
  → PRIVMSG alice :好的...
  → 用户在私聊窗口看到回复
```

> 引用：`zchat-channel-server/server.py:133-154`

### 场景 3：系统消息（停止 agent）

CLI 执行 `zchat agent stop agent0`

```
CLI (AgentManager._force_stop):
  → 加载 template pre_stop hook
  → 发送 pre_stop 到 tmux pane
  → 等待 window 关闭（最多 10 秒）
  → 超时则 window.kill()
  → 删除 agents/alice-agent0.ready
  → 更新 state.json: status="offline"
```

> 引用：`zchat/cli/agent_manager.py:195-241`

## 系统启动流程

### 快速启动（start.sh）

```bash
# start.sh 的完整流程
uv sync                              # 同步依赖
zchat project create local            # 创建项目（如果不存在）
zchat irc daemon start                # 启动 ergo
zchat irc start                       # 启动 WeeChat
zchat agent create agent0             # 创建主 agent
tmux attach                           # 进入 tmux session
```

> 引用：`start.sh:26-44`

### 逐步启动

```
1. zchat project create local
   → 生成 config.toml + tmuxp.yaml + bootstrap.sh
   → 创建 tmux session: zchat-<uuid>-local

2. zchat irc daemon start
   → 检查端口 6667
   → 生成 ergo 配置（从 defaultconfig 修补）
   → 启动 ergo 子进程
   → 保存 PID 到 state.json

3. zchat irc start
   → tmuxp load 创建 session（如需要）
   → 在 weechat window 中启动 WeeChat
   → 自动连接到 ergo 并加入频道

4. zchat agent create agent0
   → scoped_name("agent0", "alice") → "alice-agent0"
   → 创建工作空间 agents/alice-agent0/
   → 渲染 .zchat-env 环境变量
   → 创建 tmux window "alice-agent0"
   → 运行 start.sh → 启动 Claude Code + channel-server MCP
   → 后台线程自动确认启动提示
   → 等待 SessionStart hook 写入 agents/alice-agent0.ready
   → 状态 → "running"
```

## 系统关闭流程

```python
# zchat/cli/app.py:719-745
def cmd_shutdown(ctx):
    # 1. 停止所有 agent
    for agent in mgr.list_agents():
        if agent["status"] == "running":
            mgr.stop(agent_name, force=True)
    
    # 2. 停止 WeeChat
    irc_mgr.stop_weechat()
    
    # 3. 停止 ergo
    irc_mgr.daemon_stop()
    
    # 4. 杀掉 tmux session
    session.kill()
```

> 引用：`zchat/cli/app.py:719-745`

## claude.sh 启动器

`claude.sh` 是独立于 zchat 的 Claude Code 启动器，提供四种模式：

| 模式 | 用途 |
|------|------|
| Interactive | 标准 Claude Code 会话 |
| Interactive + Worktree | 在隔离的 git 分支中工作 |
| Remote Control | 从手机/浏览器继续（QR 码） |
| Resume | 恢复已有对话 |

关键特性：
- 所有模式都在 tmux 中运行（SSH 断线保护）
- 自动检测 iTerm2 并启用 `tmux -CC` 原生集成
- 管理 session 复用和创建
- 加载 `claude.local.env`（代理、API 密钥）和 `.mcp.env`（MCP server 密钥）

> 引用：`claude.sh:1-452`

## 部署与发布

### 发布流程

```
1. 打 tag：git tag v0.3.1.dev58
2. Push tag → CI 自动发布到 PyPI
3. 更新 homebrew-zchat formula（版本号 + sha256）
4. 用户：brew upgrade zchat 或 zchat self-update
```

> 引用：[docs/releasing.md](../../releasing.md)

### Homebrew 打包

```ruby
# homebrew-zchat/Formula/zchat.rb
class Zchat < Formula
  desc "Multi-agent collaboration over IRC"
  # 创建 Python venv，安装 zchat + 子模块
  # 生成 zchat 和 zchat-channel 两个可执行文件
end
```

> 引用：`homebrew-zchat/Formula/zchat.rb`

### 生产环境 ergo

`ergo-inside/` 包含生产环境配置：
- Caddy L4 代理提供 TLS（`:6697` → `:6667`）
- OIDC 认证（SASL + auth-script）
- `deploy.sh` 部署到服务器

> 引用：`ergo-inside/deploy.sh`

## 测试体系

三层测试策略：

| 层 | 命令 | 范围 | 依赖 |
|----|------|------|------|
| Unit | `uv run pytest tests/unit/ -v` | 纯逻辑 | 无外部依赖 |
| E2E | `uv run pytest tests/e2e/ -v -m e2e` | CLI 集成 | ergo + tmux |
| Pre-release | `./tests/pre_release/walkthrough.sh` | 完整流程 | 全部组件 |

Pre-release 测试使用 asciinema 录制，产出 `.cast` 文件和 `.gif` 动图。

> 引用：[CLAUDE.md](../../../CLAUDE.md) "测试体系"

## 插件市场

```json
// ezagent42-marketplace/.claude-plugin/marketplace.json
{
  "plugins": [
    {"name": "zchat", "description": "IRC channel for Claude Code"},
    {"name": "feishu", "description": "Feishu (Lark) channel for Claude Code"}
  ]
}
```

channel-server 通过 Claude Code 的插件系统安装：
```bash
claude plugin install zchat-channel
```

> 引用：`ezagent42-marketplace/.claude-plugin/marketplace.json`

## 扩展点

### 1. 自定义 Agent 模板

创建新模板：
```bash
zchat template create my-agent
```

编辑 `~/.zchat/templates/my-agent/start.sh` 自定义启动行为。

> 引用：`zchat/cli/template_loader.py:82-88`

### 2. 添加 MCP 工具

在 `server.py` 的 `register_tools()` 中添加新工具：

```python
# 1. 在 @server.list_tools() 中添加 tool 定义
# 2. 在 @server.call_tool() 中添加 handler
# 3. 实现 _handle_<toolname>() 函数
```

> 引用：[CLAUDE.md](../../../CLAUDE.md) "添加 MCP Tool"

### 3. Agent soul.md

在 agent 工作空间中放一个 `soul.md`，定义 agent 的角色和通信风格：

```markdown
# Soul
你是一个专注于代码审查的 agent。
对每个 PR 提供 3 个改进建议。
用中文回复。
```

channel-server 的 instructions.md 会指导 Claude 读取这个文件。

> 引用：`zchat-channel-server/instructions.md`（soul.md 部分）

### 4. 未来方向

根据 constraints.md 的路线图：
- Agent-to-agent DMs（agent 之间直接私聊）
- Feishu/飞书 bridge
- Ed25519 签名（消息认证）
- Web UI

> 引用：[docs/guide/constraints.md](../../guide/constraints.md) "Roadmap"

## 架构总结

```
┌─────────────────────────────────────────────────────────┐
│                    用户交互层                             │
│  WeeChat + zchat.py 插件                                │
│  (/agent 命令、系统消息渲染、状态栏)                       │
├─────────────────────────────────────────────────────────┤
│                    管理层                                 │
│  zchat CLI (Typer)                                      │
│  ├─ ProjectManager (config.toml, tmuxp, bootstrap)      │
│  ├─ AgentManager (create/stop/restart, tmux windows)    │
│  ├─ IrcManager (ergo daemon, WeeChat)                   │
│  └─ Auth (OIDC device code, token cache)                │
├─────────────────────────────────────────────────────────┤
│                    桥接层                                 │
│  zchat-channel-server (MCP Server)                      │
│  ├─ IRC 线程 (irc.client.Reactor)                       │
│  ├─ Async 主线程 (MCP stdio + queue polling)             │
│  └─ MCP 工具 (reply, join_channel)                      │
├─────────────────────────────────────────────────────────┤
│                    协议层                                 │
│  zchat-protocol                                         │
│  ├─ naming (scoped_name, AGENT_SEPARATOR)               │
│  └─ sys_messages (encode/decode, make_sys_message)      │
├─────────────────────────────────────────────────────────┤
│                    基础设施层                              │
│  IRC (ergo server) + tmux + Claude Code CLI             │
└─────────────────────────────────────────────────────────┘
```

## 快速参考

| 我想… | 命令/位置 |
|-------|----------|
| 创建项目 | `zchat project create local` |
| 启动全部 | `./start.sh ~/workspace` |
| 创建 agent | `zchat agent create agent0` |
| 看 agent 终端 | `Ctrl+b 2` 或 `zchat agent focus agent0` |
| 在频道对话 | WeeChat 中 `@yaosh-agent0 你好` |
| 私聊 agent | WeeChat 中 `/msg yaosh-agent0 hello` |
| 查看状态 | `zchat agent list` |
| 停止全部 | `zchat shutdown` |
| 跑测试 | `uv run pytest tests/unit/ -v` |
| 添加 MCP 工具 | 编辑 `zchat-channel-server/server.py` |
| 自定义 agent 行为 | 在工作空间创建 `soul.md` |

## 恭喜

你已经完整掌握了 zchat 的架构、原理和使用方式。回顾一下学习路径：

1. **IRC 基础** → 为什么选 IRC，消息类型
2. **协议层** → 命名规范，系统消息
3. **桥接层** → MCP ↔ IRC 双线程模型
4. **管理层** → 项目配置，agent 生命周期，IRC/认证
5. **UI 层** → WeeChat 插件
6. **全链路** → 端到端消息流，部署，扩展

如果需要深入某个主题，每章都标注了源码位置和行号，可以直接跳转阅读。
