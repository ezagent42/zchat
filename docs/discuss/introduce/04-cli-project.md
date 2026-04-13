# 第四章：zchat CLI——项目与配置管理

> 预计阅读：25 分钟

## 概述

zchat CLI 是用户交互的入口，基于 Typer 框架构建。本章覆盖：

- CLI 架构与命令层级
- 项目创建与配置
- 状态持久化
- tmux session 管理

> 代码位置：`zchat/cli/`
> 入口：`pyproject.toml:25` → `zchat = "zchat.cli.app:app"`

## CLI 命令层级

```
zchat
├─ project
│   ├─ create <name>        # 创建项目
│   ├─ list                 # 列出所有项目
│   ├─ use <name>           # 设为默认项目
│   ├─ show [name]          # 显示项目配置
│   └─ remove <name>        # 删除项目
├─ auth
│   ├─ login                # OIDC 或本地认证
│   ├─ status               # 查看认证状态
│   ├─ refresh              # 刷新 token
│   └─ logout               # 登出
├─ irc
│   ├─ start                # 启动 WeeChat
│   ├─ stop                 # 停止 WeeChat
│   ├─ status               # 查看 IRC 状态
│   └─ daemon
│       ├─ start            # 启动本地 ergo
│       └─ stop             # 停止 ergo
├─ agent
│   ├─ create <name>        # 创建 agent
│   ├─ stop <name>          # 停止 agent
│   ├─ list                 # 列出 agent
│   ├─ status <name>        # 查看 agent 详情
│   ├─ send <name> <text>   # 发送消息
│   ├─ restart <name>       # 重启 agent
│   ├─ focus <name>         # 切到 agent 窗口
│   └─ hide [name|all]      # 切回 WeeChat
├─ template
│   ├─ list / show / set / create
├─ setup
│   └─ weechat              # 安装 WeeChat 插件
├─ doctor                   # 环境检查
├─ shutdown                 # 全部停止
└─ self-update              # 自我更新
```

> 引用：`zchat/cli/app.py:22-36`（命令组定义）

## 项目概念

zchat 中"项目"是一组配置的集合，存储在 `~/.zchat/projects/<name>/` 下。

### 目录结构

```
~/.zchat/
├─ default                          # 默认项目名
├─ auth.json                        # OIDC 认证信息
├─ projects/
│   └─ local/                       # 项目 "local"
│       ├─ config.toml              # 项目配置
│       ├─ tmuxp.yaml               # tmux session 定义
│       ├─ bootstrap.sh             # session 初始化脚本
│       ├─ state.json               # 运行时状态
│       ├─ claude.local.env         # 代理配置（可选）
│       ├─ .weechat/                # WeeChat 配置缓存
│       ├─ ergo/                    # ergo 数据目录
│       │   ├─ ergo.yaml            # 生成的 ergo 配置
│       │   └─ ergo.log             # ergo 日志
│       └─ agents/                  # agent 工作空间
│           ├─ alice-agent0/        # agent0 的工作目录
│           ├─ alice-agent0.ready   # 就绪标记文件
│           └─ alice-helper/        # helper 的工作目录
└─ templates/                       # 用户自定义模板
```

### ZCHAT_DIR

```python
# zchat/cli/project.py:9
ZCHAT_DIR = os.environ.get("ZCHAT_HOME", os.path.expanduser("~/.zchat"))
```

可通过 `ZCHAT_HOME` 环境变量覆盖，测试时常用。

> 引用：`zchat/cli/project.py:9`

## 项目创建

```python
# zchat/cli/project.py:22-80
def create_project_config(name, server, port, tls, password, nick, channels, ...):
```

创建项目时生成三个文件：

### 1. config.toml

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
env_file = ""
mcp_server_cmd = ["zchat-channel"]

[tmux]
session = "zchat-e1df88e1-local"
```

> 引用：`zchat/cli/project.py:31-45`

### 2. tmuxp.yaml

```yaml
session_name: zchat-e1df88e1-local
start_directory: /home/yaosh/.zchat/projects/local
windows:
  - window_name: weechat
    panes:
      - blank
    focus: true
```

tmuxp 是声明式的 tmux session 管理工具。`start_directory` 决定了 session 中新建 pane 的默认工作目录。

> 引用：`zchat/cli/project.py:49-60`

### 3. bootstrap.sh

```bash
#!/bin/bash
set -euo pipefail
mkdir -p agents
# 清理残留的 .ready 标记
for f in agents/*.ready; do
    [ -e "$f" ] && rm "$f"
done
```

每次 tmux session 启动时执行，确保环境干净。

> 引用：`zchat/cli/project.py:62-74`

## tmux Session 命名

```python
# zchat/cli/project.py:16-19
def _generate_tmux_session_name(project_name: str) -> str:
    import uuid
    short = uuid.uuid4().hex[:8]
    return f"zchat-{short}-{project_name}"
```

格式：`zchat-<8位UUID>-<项目名>`，如 `zchat-e1df88e1-local`。

UUID 确保多个项目的 session 不冲突。

> 引用：`zchat/cli/project.py:16-19`

## 项目解析顺序

当用户运行 `zchat agent list`（没有指定项目）时，如何确定项目？

```python
# zchat/cli/project.py:103-113
def resolve_project(explicit=None):
    # 1. 命令行 --project 参数
    if explicit:
        return explicit
    
    # 2. 当前目录或父目录中的 .zchat 文件
    path = os.getcwd()
    while path != os.path.dirname(path):
        marker = os.path.join(path, ".zchat")
        if os.path.isfile(marker):
            return open(marker).read().strip()
        path = os.path.dirname(path)
    
    # 3. 全局默认项目
    return get_default_project()
```

优先级：**显式指定 > .zchat 文件 > 默认项目**

> 引用：`zchat/cli/project.py:103-113`

## 状态持久化

运行时状态存储在 `state.json` 中：

```json
{
  "agents": {
    "alice-agent0": {
      "type": "claude",
      "workspace": "/home/yaosh/.zchat/projects/local/agents/alice-agent0",
      "window_name": "alice-agent0",
      "status": "running",
      "created_at": 1712000000.0,
      "channels": ["#general"]
    }
  },
  "irc": {
    "daemon_pid": 12345,
    "weechat_window": "weechat"
  }
}
```

- `agents` 键由 AgentManager 管理
- `irc` 键由 IrcManager 管理
- 两者共享同一个 state.json，写入时合并而非覆盖

> 引用：`zchat/cli/agent_manager.py:319-339`、`zchat/cli/irc_manager.py:331-342`

## 配置修改

```python
# zchat/cli/project.py:145-169
def set_config_value(name, key, value):
    # 支持点号路径：irc.port → config["irc"]["port"]
    # 自动类型转换：true → True, "6667" → 6667
```

命令行：`zchat set irc.port 6668`

> 引用：`zchat/cli/project.py:145-169`

## 上下文注入

CLI 主回调函数在每个子命令之前运行，注入项目上下文：

```python
# zchat/cli/app.py:108-126
@app.callback(invoke_without_command=True)
def main(ctx, project, version):
    # 解析项目
    proj = resolve_project(project)
    # 加载配置
    cfg = load_project_config(proj)
    # 存入上下文
    ctx.obj = {"project": proj, "config": cfg}
```

子命令通过 `ctx.obj` 访问项目配置。

> 引用：`zchat/cli/app.py:108-126`

## 工厂函数

每个子系统都通过工厂函数创建管理器：

```python
# zchat/cli/app.py:71-97
def _get_irc_manager(ctx):
    cfg = _get_config(ctx)
    return IrcManager(config=cfg, state_file=state_path, tmux_session=session_name)

def _get_agent_manager(ctx):
    cfg = _get_config(ctx)
    return AgentManager(
        irc_server=cfg["irc"]["server"],
        irc_port=cfg["irc"]["port"],
        username=get_username(),
        default_channels=cfg["agents"]["default_channels"],
        tmux_session=session_name,
        state_file=state_path,
        project_dir=project_dir,
    )
```

> 引用：`zchat/cli/app.py:71-97`

## tmux 辅助模块

```python
# zchat/cli/tmux.py
_server: libtmux.Server | None = None

def server() -> libtmux.Server:
    """缓存的 libtmux Server 单例"""
    global _server
    if _server is None:
        _server = libtmux.Server()
    return _server

def get_or_create_session(name) -> Session:
    """获取已有 session 或创建新的（detached）"""
    
def find_window(session, window_name) -> Window | None:
    """按名称查找 window"""
    
def window_alive(session, window_name) -> bool:
    """检查 window 是否存在"""
```

所有 tmux 操作都通过这个模块间接调用 libtmux。

> 引用：`zchat/cli/tmux.py:1-61`

## 测试

```bash
uv run pytest tests/unit/test_project.py -v
```

覆盖：项目创建/删除/列出、配置加载/修改、解析顺序。

> 引用：`tests/unit/test_project.py`

## 下一步

理解了项目管理后，进入 [第五章：Agent 生命周期管理](./05-agent-lifecycle.md)。
