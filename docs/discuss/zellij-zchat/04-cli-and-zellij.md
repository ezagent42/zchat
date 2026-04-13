# 第四章：CLI + Zellij 会话管理

> 预计阅读：25 分钟
>
> 本章完全重写，替代 [旧版第四章](../introduce/04-cli-project.md)（tmux 版）。

## 概述

zchat CLI 的核心职责不变——管理项目、agent、IRC 的生命周期。变化在于底层从 tmux 切换到 Zellij。

## CLI 命令层级

```
zchat [--project <name>] [--version]
├─ project: create / list / show / remove / use
├─ irc:
│   ├─ daemon: start / stop
│   └─ start / stop / status
├─ agent: create / stop / list / status / send / restart / focus / hide
├─ auth: login / status / refresh / logout
├─ setup: weechat
├─ template: list / show / set / create
├─ config: (全局配置)
├─ doctor                    # 环境检查
├─ shutdown                  # 全部停止
└─ update / upgrade          # 更新
```

> 代码位置：`zchat/cli/app.py`

## 项目目录结构

```
~/.zchat/
├─ default                          # 默认项目名
├─ auth.json                        # OIDC 认证信息
├─ config.json                      # 全局配置（IRC server 引用等）
├─ projects/
│   └─ local/
│       ├─ config.toml              # 项目配置（新格式）
│       ├─ layout.kdl               # Zellij 布局定义
│       ├─ state.json               # 运行时状态
│       ├─ claude.local.env         # 代理配置（可选）
│       ├─ .weechat/                # WeeChat 配置缓存
│       ├─ ergo/                    # ergo 数据目录
│       │   ├─ ergo.yaml
│       │   ├─ ergo.log
│       │   └─ languages/           # 自动下载
│       └─ agents/
│           ├─ yaosh-agent0/        # agent 工作目录
│           ├─ yaosh-agent0.ready   # 就绪标记
│           └─ yaosh-helper/
└─ templates/                       # 用户自定义模板
```

### 与旧版对比

| 旧版 | 新版 | 说明 |
|------|------|------|
| `tmuxp.yaml` | `layout.kdl` | Zellij KDL 格式布局 |
| `bootstrap.sh` | _(移除)_ | 清理逻辑内置到 CLI |
| `config.toml [irc]/[tmux]/[agents]` | `config.toml` 扁平结构 | 简化配置层级 |

## paths.py — 集中路径管理

所有路径解析集中在一个模块，支持环境变量覆盖：

```python
# zchat/cli/paths.py — 优先级：环境变量 > 配置 > 默认值

zchat_home()                    # $ZCHAT_HOME 或 ~/.zchat
projects_dir()                  # {zchat_home}/projects
project_dir(name)               # {projects_dir}/{name}
project_config(name)            # {project_dir}/config.toml
project_state(name)             # {project_dir}/state.json

agent_workspace(project, name)  # {project_dir}/agents/{scoped_name}
agent_ready_marker(project, n)  # {project_dir}/agents/{scoped_name}.ready

ergo_data_dir(project)          # {project_dir}/ergo
weechat_home(project)           # {project_dir}/.weechat
zellij_layout_dir(project)      # {project_dir}/
```

**设计目的**：测试时通过 `ZCHAT_HOME` 环境变量隔离，避免污染真实配置。

> 代码位置：`zchat/cli/paths.py`

## Zellij 会话管理

### zellij.py 封装层

所有 Zellij 操作通过 CLI 命令调用，不依赖任何 Python 绑定：

```python
# zchat/cli/zellij.py

def ensure_session(name: str):
    """创建或验证 Zellij session"""
    # 处理 EXITED 状态的 session（需要先 delete 再 create）
    
def new_tab(session: str, name: str, command: str = "", cwd: str = ""):
    """在 session 中创建新 tab"""
    # zellij --session {session} action new-tab --name {name}
    # 如果有 command，发送到新 tab 的 pane
    
def close_tab(session: str, name: str):
    """关闭指定 tab"""
    
def tab_exists(session: str, name: str) -> bool:
    """检查 tab 是否存在"""
    # 通过 zellij --session {session} action query-tab-names
    
def get_pane_id(session: str, tab_name: str) -> str | None:
    """获取 tab 内 pane 的 ID（用于 send_command）"""
    
def send_command(session: str, pane_id: str, text: str):
    """向 pane 发送文本 + Enter"""
    # zellij --session {session} action write-chars --pane-id {pane_id} "{text}\n"
    
def list_tabs(session: str) -> list[str]:
    """列出 session 的所有 tab 名"""
    
def go_to_tab(session: str, tab_name: str):
    """切换到指定 tab"""
    
def kill_session(session: str):
    """终止 session"""
```

### 与 tmux 的对应关系

| tmux 概念 | Zellij 概念 | 变化 |
|-----------|-------------|------|
| session | session | 命名简化，去掉 UUID |
| window | tab | 功能等价 |
| pane | pane | 功能等价 |
| `libtmux` Python 库 | CLI 命令 `zellij action` | 无 Python 绑定 |
| `tmuxp.yaml` | `layout.kdl` | 声明式布局 |
| `capture-pane` | `subscribe-pane-events` | 用于自动确认启动提示 |

### layout.py — KDL 布局生成

Zellij 使用 KDL 格式定义布局：

```python
# zchat/cli/layout.py
def generate_layout(config: dict, state: dict) -> str:
    """生成 Zellij KDL 布局字符串"""
    # 包含：
    # - default_tab_template（tab-bar + status-bar 插件）
    # - chat tab（WeeChat，focused）
    # - ctl tab（CLI 命令窗口）
    # - 从 state.json 恢复的 agent tabs
```

生成的 KDL 示例（简化）：

```kdl
layout {
    default_tab_template {
        pane size=1 borderless=true {
            plugin location="tab-bar"
        }
        children
        pane size=2 borderless=true {
            plugin location="status-bar"
        }
    }
    
    tab name="chat" focus=true {
        pane
    }
    
    tab name="ctl" {
        pane
    }
}
```

## 项目配置解析

### config.toml 加载

```python
# zchat/cli/project.py
def load_project_config(name: str) -> dict:
    """加载并验证项目配置"""
    # 1. 读取 config.toml
    # 2. 检测旧格式（有 [irc] section）→ 触发迁移
    # 3. 解析 server 引用（"local" → 127.0.0.1:6667）
```

### 全局 IRC Server 配置

`~/.zchat/config.json` 存储全局 IRC server 定义：

```json
{
  "servers": {
    "local": {"host": "127.0.0.1", "port": 6667, "tls": false},
    "zchat.inside.h2os.cloud": {"host": "zchat.inside.h2os.cloud", "port": 6697, "tls": true}
  }
}
```

`config.toml` 中的 `server = "local"` 是引用名，由 `_get_irc_config()` 解析为实际连接参数。

### 项目解析优先级

```
1. 命令行 --project 参数
2. 当前目录的 .zchat 文件
3. ~/.zchat/default 全局默认
```

> 代码位置：`zchat/cli/project.py:resolve_project()`

## 状态持久化

`state.json` 记录运行时状态：

```json
{
  "agents": {
    "yaosh-agent0": {
      "type": "claude",
      "workspace": "/home/yaosh/workspace",
      "tab_name": "yaosh-agent0",
      "status": "running",
      "created_at": 1712000000.0,
      "channels": ["#general"]
    }
  },
  "irc": {
    "daemon_pid": 50988,
    "weechat_tab": "weechat",
    "weechat_pane_id": "0"
  }
}
```

与旧版对比：
- `window_name` → `tab_name`
- `weechat_window` → `weechat_tab`
- 新增 `weechat_pane_id`（用于 send_command）

## 工厂函数

CLI 回调注入上下文，子命令通过工厂函数获取管理器：

```python
# zchat/cli/app.py
def _get_irc_manager(ctx) -> IrcManager:
    return IrcManager(
        config=cfg,
        state_file=state_path,
        zellij_session=session_name,  # 旧版是 tmux_session
    )

def _get_agent_manager(ctx) -> AgentManager:
    return AgentManager(
        irc_server=...,
        irc_port=...,
        username=get_username(),
        default_channels=...,
        zellij_session=session_name,  # 旧版是 tmux_session
        state_file=state_path,
        project_dir=project_dir,
    )
```

## 迁移支持

如果用户有旧配置，`migrate.py` 自动处理：

```python
# zchat/cli/migrate.py
def migrate_config_if_needed(project_dir):
    # 检测 [tmux] section → 旧格式
    # 备份为 config.toml.bak
    # 转换：
    #   [irc].server → server
    #   [agents].default_type → default_runner
    #   [tmux].session → [zellij].session
    #   zchat-{uuid}-{name} → zchat-{name}
    
def migrate_state_if_needed(project_dir):
    # window_name → tab_name
    # weechat_window → weechat_tab
    # 移除 legacy pane_id
```

## 测试

```bash
uv run pytest tests/unit/test_project.py tests/unit/test_paths.py tests/unit/test_layout.py -v
```

## 下一步

进入 [第五章：Agent 生命周期管理](./05-agent-lifecycle.md)。
