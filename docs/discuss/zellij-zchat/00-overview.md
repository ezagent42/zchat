# 第零章：全局概览与架构变化

> 预计阅读：15 分钟

## zchat 是什么

zchat 是一个**多 Agent 协作系统**，让多个 Claude Code 实例（agent）和人类通过 IRC 协议实时聊天、协作完成软件工程任务。

> 核心概念不变——详见 [旧版第零章](../introduce/00-overview.md)。

## 架构总览（Zellij 版）

```
┌──────────────────────────────────────────────────────────────┐
│ Zellij Session: zchat-local                                  │
│                                                              │
│ ┌─────────┐  ┌─────────┐  ┌──────────────┐  ┌───────────┐  │
│ │  chat   │  │   ctl   │  │ yaosh-agent0 │  │yaosh-help │  │
│ │(WeeChat)│  │ (shell) │  │ (Claude Code │  │(Claude    │  │
│ │         │  │         │  │  + MCP)      │  │ Code+MCP) │  │
│ └────┬────┘  └─────────┘  └──────┬───────┘  └─────┬─────┘  │
│      │                           │                 │         │
└──────┼───────────────────────────┼─────────────────┼─────────┘
       │ IRC                       │ IRC             │ IRC
       ▼                           ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│ IRC Server (ergo)                                           │
│ 本地 127.0.0.1:6667 或远程 zchat.inside.h2os.cloud:6697     │
└─────────────────────────────────────────────────────────────┘
```

与旧版架构的关键区别：

| 维度 | 旧版（tmux） | 新版（Zellij） |
|------|-------------|---------------|
| 终端复用 | tmux + tmuxp（YAML 声明） | Zellij + KDL layout |
| 隔离单元 | tmux window | Zellij tab |
| Session 命名 | `zchat-{uuid}-{project}` | `zchat-{project}` |
| 启动方式 | tmuxp load → tmux attach | Zellij layout → zellij attach |
| 状态文件 | `window_name`, `weechat_window` | `tab_name`, `weechat_tab` |

**不变的部分**：

- IRC 作为通信协议——所有组件通过 IRC PRIVMSG 通信
- channel-server 作为 MCP ↔ IRC 桥接——双线程 + asyncio.Queue
- zchat-protocol 定义的命名规范和系统消息
- WeeChat 插件的 `/agent` 命令和消息渲染
- Agent ready 检测机制（SessionStart hook → `.ready` 文件）

## 五个核心组件

| 组件 | 职责 | 代码位置 | 变化 |
|------|------|----------|------|
| **zchat CLI** | 项目/agent/IRC 生命周期管理 | `zchat/cli/` | Zellij 适配 |
| **zchat-channel-server** | MCP server，桥接 IRC ↔ Claude Code | `zchat-channel-server/` | 无变化 |
| **zchat-protocol** | 命名规范 + 系统消息协议 | `zchat-protocol/` | 无变化 |
| **weechat-zchat-plugin** | WeeChat 插件 | `weechat-zchat-plugin/` | 无变化 |
| **ergo** | IRC server | 第三方 | 无变化 |

## 新增模块

### paths.py — 集中路径管理

所有路径解析集中到一个模块，替代之前散落在各处的 `os.path.join()`：

```python
# zchat/cli/paths.py
zchat_home()           # $ZCHAT_HOME 或 ~/.zchat
project_dir(name)      # ~/.zchat/projects/{name}
agent_workspace(...)   # ~/.zchat/projects/{name}/agents/{scoped}/
ergo_data_dir(...)     # ~/.zchat/projects/{name}/ergo/
weechat_home(...)      # ~/.zchat/projects/{name}/.weechat/
zellij_layout_dir(...) # ~/.zchat/projects/{name}/
```

### zellij.py — Zellij 操作封装

通过 `zellij` CLI 命令操作 session 和 tab：

```python
# zchat/cli/zellij.py
ensure_session(name)              # 创建/验证 session
new_tab(session, name, command)   # 创建 tab 并运行命令
close_tab(session, name)          # 关闭 tab
tab_exists(session, name)         # 检查 tab 是否存在
send_command(session, pane, text) # 向 pane 发送文本
get_pane_id(session, tab_name)    # 获取 tab 的 pane ID
```

### layout.py — KDL 布局生成

生成 Zellij 的 KDL 布局文件：

```python
# zchat/cli/layout.py
generate_layout(config, state)  # 生成 KDL 字符串
write_layout(project_dir, ...)  # 写入 layout.kdl
```

生成的 layout 包含 tab-bar、status-bar 插件和初始 tab 定义。

### migrate.py — 配置迁移

自动将旧格式配置迁移到新格式：

```python
# zchat/cli/migrate.py
migrate_config_if_needed(project_dir)  # [irc]/[tmux] → 扁平结构
migrate_state_if_needed(project_dir)   # window_name → tab_name
```

## 配置格式变化

### 旧格式（tmux 版）

```toml
[irc]
server = "127.0.0.1"
port = 6667
tls = false
password = ""

[agents]
default_type = "claude"
default_channels = ["#general"]
username = ""

[tmux]
session = "zchat-e1df88e1-local"
```

### 新格式（Zellij 版）

```toml
server = "local"
default_runner = "claude"
default_channels = ["#general"]
username = ""
env_file = ""
mcp_server_cmd = ["zchat-channel"]

[zellij]
session = "zchat-local"
```

变化要点：
- `[irc]` section 消失，`server` 提升为顶层键，值从 IP 变为引用名（`"local"` → 由全局配置解析为 `127.0.0.1:6667`）
- `[agents]` section 消失，键提升为顶层
- `[tmux]` → `[zellij]`，session 名去掉 UUID
- 新增 `mcp_server_cmd` — MCP server 启动命令

## 依赖变化

```diff
- libtmux>=0.55,<0.56
- tmuxp>=1.30.0
- pyyaml>=6.0
+ python-dotenv>=1.0.0
```

Zellij 通过 CLI 命令调用（`subprocess`），不需要 Python 绑定库。

## 学习路线

| 章 | 主题 | 重点 |
|----|------|------|
| 1-2 | IRC + Protocol | **无变化**，直接看旧版 |
| 3 | channel-server 通信 | **重点**——深入双线程模型和消息流 |
| 4 | CLI + Zellij | **重写**——新的 session/tab 管理 |
| 5 | Agent 生命周期 | **更新**——Zellij tab 替代 tmux window |
| 6-7 | IRC 认证 + WeeChat | 小幅更新，主体不变 |
| 8 | 通信全链路 | **重点**——端到端消息追踪 |

## 下一步

- 如果你是新用户：先看 [Quick Start](./quick-start.md)
- 如果你了解旧版：直接跳到 [第三章：通信详解](./03-channel-server.md) 和 [第四章：CLI + Zellij](./04-cli-and-zellij.md)
- IRC / Protocol 基础：参见旧版 [第一章](../introduce/01-irc-fundamentals.md) 和 [第二章](../introduce/02-protocol.md)
