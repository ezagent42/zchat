# zchat Quick Start（Zellij 版）

> 从零到 agent 对话的完整操作指南。
>
> 已知问题和绕过方案见 [E2E 测试记录](../e2e-log/2026-04-08-quickstart-test.md)。

## 前置条件

```bash
# 必须安装
claude --version        # Claude Code CLI
uv --version            # Python 包管理
weechat --version       # IRC 客户端
zellij --version        # 终端复用器（替代 tmux）

# 本地开发时需要
ergo --version          # 本地 IRC server（连远程服务器可跳过）
```

安装缺失项：

```bash
brew install ergo zellij         # macOS
# WSL/Linux
brew install ergo                # Homebrew on Linux
# Zellij: https://zellij.dev/documentation/installation
```

---

## 方式一：一键启动

```bash
cd ~/projects/zchat
./start.sh ~/workspace local
```

这会依次执行：同步依赖 → 创建项目 → 启动 ergo → 启动 WeeChat → 创建 agent0 → attach 到 Zellij session。

> `start.sh` 第一个参数是 agent 的工作目录，第二个是项目名（默认 `local`）。

---

## 方式二：逐步手动启动

### Step 1：同步依赖

```bash
cd ~/projects/zchat
uv sync
```

### Step 2：创建项目

```bash
zchat project create local
```

交互式选择：

| 选项 | 本地开发 | 远程协作 |
|------|----------|----------|
| IRC Server | `2) Local (127.0.0.1:6667)` | `1) zchat.inside.h2os.cloud` |
| Default channels | `#general`（默认） | 按需填写 |
| Agent type | `1) claude`（默认） | 同左 |
| HTTP proxy | 留空（直连）或填 `ip:port` | 同左 |

项目配置写入 `~/.zchat/projects/local/config.toml`：

```toml
server = "local"              # 或 "zchat.inside.h2os.cloud"
default_runner = "claude"
default_channels = ["#general"]
username = ""
env_file = ""
mcp_server_cmd = ["zchat-channel"]

[zellij]
session = "zchat-local"
```

### Step 3：启动 ergo IRC server

> 如果 Step 2 选了远程服务器（`zchat.inside.h2os.cloud`），**跳过此步**。

```bash
zchat irc daemon start
```

输出示例：

```
  Downloading ergo languages from https://github.com/ergochat/ergo/...
  ergo languages installed.
ergo running (pid 50988, port 6667).
```

> 首次启动会自动下载 ergo 的 languages 目录（Homebrew 安装不包含）。

### Step 4：启动 WeeChat

```bash
zchat irc start
```

WeeChat 在 Zellij 的 `chat` tab 中启动，自动连接 IRC server 并加入频道。

### Step 5：创建 Agent

```bash
zchat agent create agent0 --workspace ~/workspace
```

这会：
1. 创建 scoped name：`{你的用户名}-agent0`
2. 在 Zellij 中开一个新 tab 运行 Claude Code + channel-server MCP
3. 后台自动确认 Claude Code 的启动提示
4. 等待 `.ready` 标记文件出现

### Step 6：进入 Zellij

```bash
zellij attach zchat-local
```

或者 `start.sh` 会自动 attach。

---

## Zellij 基本操作

| 操作 | 快捷键 |
|------|--------|
| 切换 tab | `Alt+1/2/3...` 或点击 tab 栏 |
| 锁定模式（输入不被 Zellij 截获） | `Ctrl+g` |
| 新建 pane | `Alt+n` |
| 关闭 pane | `Ctrl+q` |
| detach（后台运行） | `Ctrl+o` 然后 `d` |
| 重新 attach | `zellij attach zchat-local` |

Zellij tab 布局：

```
┌─ zchat-local ──────────────────────────────────────┐
│ [chat]  [ctl]  [yaosh-agent0]  [yaosh-helper] ...  │  ← tab 栏
├────────────────────────────────────────────────────┤
│                                                    │
│          当前 tab 的内容                              │
│                                                    │
└────────────────────────────────────────────────────┘
```

- **chat** — WeeChat IRC 客户端
- **ctl** — CLI 命令窗口
- **yaosh-agent0** — Agent 的 Claude Code 终端

---

## 与 Agent 交互

### 在 WeeChat 中 @mention

```
@yaosh-agent0 帮我看看 main.py 的结构
```

Agent 会在频道中回复。

### 私聊 Agent

```
/msg yaosh-agent0 帮我 debug 这个函数
```

### CLI 发送消息

```bash
zchat agent send agent0 "帮我跑一下测试"
```

### 查看 Agent 状态

```bash
zchat agent list
zchat agent status agent0
```

---

## 管理 Agent

```bash
# 创建更多 agent
zchat agent create helper --workspace ~/workspace

# 切换到 agent 的 tab
zchat agent focus agent0

# 切回 WeeChat
zchat agent hide

# 重启 agent
zchat agent restart agent0

# 停止 agent（保留工作目录）
zchat agent stop agent0
```

---

## 停止

```bash
# 停止所有（agent + WeeChat + ergo）
zchat shutdown

# 或一键停止
./stop.sh local
```

---

## 开发模式 vs 全局安装

| 场景 | 命令 | 说明 |
|------|------|------|
| 用本地源码 | `uv run python -m zchat.cli <command>` | 开发/调试时用 |
| 用全局安装 | `zchat <command>` | 日常使用 |
| 用 start.sh | `./start.sh ~/workspace` | 内部调用 `uv run` |

> 注意：全局 `zchat` 和本地源码可能版本不同，开发时建议统一用 `uv run`。

---

## 远程协作模式

如果连接远程 IRC server（如 `zchat.inside.h2os.cloud`）：

1. 项目创建时选远程服务器
2. 需要先登录认证：`zchat auth login`
3. 不需要启动本地 ergo
4. 多人共享同一个 IRC server，在同一个频道协作

```bash
zchat project create collab
# 选 1) zchat.inside.h2os.cloud
zchat auth login
zchat irc start
zchat agent create agent0 --workspace ~/workspace
```

---

## 常见问题

### ergo 启动失败：languages 目录缺失

Homebrew 安装的 ergo 不包含 languages 目录。最新版 zchat 会自动从 GitHub release 下载。如果仍然失败：

```bash
rm -rf ~/.zchat/projects/local/ergo
zchat irc daemon start    # 重新生成配置并下载
```

### 端口被占用

```bash
lsof -i :6667             # 查看谁在用
zchat irc daemon stop     # 停止已有 ergo
```

### Agent 一直 starting

检查 Claude Code 是否正常启动：

```bash
zchat agent focus agent0  # 切到 agent tab 查看
```

可能需要手动确认 Claude Code 的启动提示。

### 旧配置格式错误

```bash
rm -rf ~/.zchat/projects/local
zchat project create local
```
