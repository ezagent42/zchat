# 第五章：Agent 生命周期管理

> 预计阅读：25 分钟

## 概述

AgentManager 是 zchat 中最复杂的模块，管理 agent 从创建到销毁的完整生命周期：

```
create → spawn tmux window → wait for ready → running → stop → cleanup
```

> 代码位置：`zchat/cli/agent_manager.py`

## Agent 状态机

```
          create()
             │
             ▼
         ┌────────┐
         │starting│  等待 .ready 标记
         └───┬────┘
             │ .ready 文件出现
             ▼
         ┌───────┐
         │running│  正常工作
         └───┬───┘
             │ stop() / restart()
             ▼
         ┌───────┐
         │offline│  tmux window 已关闭
         └───────┘
```

状态存储在 `state.json` 的 `agents` 字典中：

```python
# agent_manager.py:72-80
self._agents[scoped] = {
    "type": agent_type,
    "workspace": workspace,
    "window_name": window_name,
    "status": "starting",
    "created_at": time.time(),
    "channels": channels,
}
```

> 引用：`zchat/cli/agent_manager.py:72-80`

## 创建流程详解

### Step 1：名称作用域化

```python
# agent_manager.py:58-64
def create(self, name, workspace=None, channels=None, agent_type=None):
    scoped = self.scoped(name)  # "agent0" → "alice-agent0"
    
    # 检查是否已在运行
    if scoped in self._agents and self._check_alive(scoped) == "running":
        raise ValueError(f"{scoped} already running")
```

> 引用：`zchat/cli/agent_manager.py:58-64`

### Step 2：创建工作空间

```python
# agent_manager.py:132-139
def _create_workspace(self, name):
    if self._project_dir:
        # 项目模式：~/.zchat/projects/local/agents/alice-agent0/
        ws = os.path.join(self._project_dir, "agents", name)
    else:
        # 遗留模式：/tmp/zchat-alice-agent0/
        ws = f"/tmp/zchat-{name}"
    os.makedirs(ws, exist_ok=True)
    return ws
```

工作空间是 agent 的 Claude Code 工作目录，agent 可以在其中读写文件。

> 引用：`zchat/cli/agent_manager.py:132-139`

### Step 3：构建环境变量

```python
# agent_manager.py:141-163
def _build_env_context(self, name, workspace, channels):
    return {
        "agent_name": name,
        "irc_server": self._irc_server,
        "irc_port": str(self._irc_port),
        "irc_channels": ",".join(channels),
        "irc_tls": str(self._irc_tls).lower(),
        "irc_password": self._irc_password,
        "workspace": workspace,
        "zchat_project_dir": self._project_dir,
        "irc_auth_token": token or "",
        "auth_token_file": auth_file,
    }
```

这些变量会通过模板系统渲染成 `.zchat-env` 文件，供 agent 的 start.sh 读取。

> 引用：`zchat/cli/agent_manager.py:141-163`

### Step 4：启动 tmux window

```python
# agent_manager.py:165-193
def _spawn_tmux(self, name, workspace, agent_type, channels):
    # 1. 渲染模板环境变量
    context = self._build_env_context(name, workspace, channels)
    env = render_env(agent_type, context)
    
    # 2. 叠加项目级 env_file
    if self._env_file and os.path.isfile(self._env_file):
        env.update(parse_env(self._env_file))
    
    # 3. 写 .zchat-env 到工作空间
    env_path = os.path.join(workspace, ".zchat-env")
    with open(env_path, "w") as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")
    
    # 4. 获取启动脚本路径
    start_script = get_start_script(agent_type)
    cmd = f"cd '{workspace}' && bash '{start_script}'"
    
    # 5. 创建 tmux window
    window = self.tmux_session.new_window(
        window_name=name, window_shell=cmd, attach=False
    )
    
    # 6. 启动自动确认线程
    self._auto_confirm_startup(name)
    
    return name  # window_name
```

**每个 agent 是独立的 tmux window**（不是 pane），这样：
- 互不干扰
- 可以独立切换查看
- 停止时直接 kill window

> 引用：`zchat/cli/agent_manager.py:165-193`

### Step 5：自动确认启动提示

Claude Code 启动时会弹出确认提示（"I trust this folder" 等），需要自动按 Enter：

```python
# agent_manager.py:255-285
def _auto_confirm_startup(self, window_name, timeout=60):
    def _poll():
        deadline = time.time() + timeout
        while time.time() < deadline:
            # 读取 pane 内容
            content = pane.capture_pane()
            text = "\n".join(content)
            
            # 检测确认提示
            for pattern in ["I trust this folder", "local development", "Enter to confirm"]:
                if pattern in text:
                    pane.send_keys("", enter=True)  # 按 Enter
                    return
            
            time.sleep(1)
    
    # 在后台守护线程中运行
    t = threading.Thread(target=_poll, daemon=True)
    t.start()
```

> 引用：`zchat/cli/agent_manager.py:255-285`

### Step 6：等待就绪

```python
# agent_manager.py:243-253
def _wait_for_ready(self, name, timeout=60):
    ready_file = os.path.join(self._project_dir, "agents", f"{name}.ready")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.isfile(ready_file):
            return True
        time.sleep(0.5)
    return False
```

`.ready` 文件由 Claude Code 的 **SessionStart hook** 创建——当 Claude Code 完全启动后自动写入。

> 引用：`zchat/cli/agent_manager.py:243-253`
> 引用：[CLAUDE.md](../../../CLAUDE.md) "Agent 就绪检测通过 Claude Code SessionStart hook"

## 停止流程

### Step 1：执行 pre_stop hook

模板可以定义 `pre_stop` 钩子命令：

```python
# agent_manager.py:195-227
def _force_stop(self, name):
    # 加载模板的 pre_stop hook
    template_meta = load_template(agent_type)
    pre_stop = template_meta.get("hooks", {}).get("pre_stop", "")
    
    if pre_stop:
        # 发送 pre_stop 命令到 pane
        pane.send_keys(pre_stop, enter=True)
        
        # 等待 window 自行关闭（最多 10 秒）
        for _ in range(20):
            if not window_alive(self.tmux_session, name):
                return
            time.sleep(0.5)
    
    # 超时后强制 kill
    window = find_window(self.tmux_session, name)
    if window:
        window.kill()
```

> 引用：`zchat/cli/agent_manager.py:195-227`

### Step 2：清理

```python
# agent_manager.py:229-241
def _cleanup_workspace(self, name):
    # 删除 .ready 标记文件
    ready_file = os.path.join(self._project_dir, "agents", f"{name}.ready")
    if os.path.isfile(ready_file):
        os.remove(ready_file)
    
    # 注意：工作空间目录本身不删除（保留工作产物）
```

**关键设计**：停止 agent 时**只删除 .ready 标记**，不删除工作空间。这样 agent 的工作产物（代码、笔记等）会保留。

> 引用：`zchat/cli/agent_manager.py:229-241`

## 重启

```python
# agent_manager.py:103-113
def restart(self, name):
    scoped = self.scoped(name)
    info = self._agents.get(scoped, {})
    channels = info.get("channels", self._default_channels)
    agent_type = info.get("type", self._default_type)
    
    self.stop(name, force=True)
    
    # 提取基础名（去掉用户名前缀）
    base = scoped.split(AGENT_SEPARATOR, 1)[1] if AGENT_SEPARATOR in scoped else scoped
    self.create(base, channels=channels, agent_type=agent_type)
```

重启 = stop + create，保留原来的 channels 和 agent_type 配置。

> 引用：`zchat/cli/agent_manager.py:103-113`

## 存活检测

```python
# agent_manager.py:287-299
def _check_alive(self, name):
    info = self._agents.get(name, {})
    window_name = info.get("window_name")
    if window_name and window_alive(self.tmux_session, window_name):
        return "running"
    return "offline"
```

通过检查 tmux window 是否存在来判断 agent 是否在运行。

> 引用：`zchat/cli/agent_manager.py:287-299`

## 发送消息

```python
# agent_manager.py:301-317
def send(self, name, text):
    scoped = self.scoped(name)
    status = self.get_status(name)
    
    if status["status"] != "running":
        raise ValueError(f"{scoped} is not running")
    
    # 检查是否就绪
    ready_file = os.path.join(self._project_dir, "agents", f"{scoped}.ready")
    if not os.path.isfile(ready_file):
        raise ValueError(f"{scoped} is starting, not ready yet")
    
    # 发送到 tmux pane
    window = find_window(self.tmux_session, status["window_name"])
    window.active_pane.send_keys(text, enter=True)
```

`zchat agent send agent0 "hello"` 相当于在 agent 的 Claude Code 终端里打字。

> 引用：`zchat/cli/agent_manager.py:301-317`

## 模板系统

agent 的启动行为由模板定义：

```
~/.zchat/templates/claude/          # 用户自定义（高优先级）
zchat/cli/templates/claude/          # 内置（低优先级）
├── template.toml                    # 元数据
├── start.sh                         # 启动脚本
├── .env.example                     # 环境变量模板
└── .env                             # 用户覆盖（可选）
```

### template.toml

```toml
[template]
name = "claude"
description = "Claude Code agent"

[hooks]
pre_stop = ""
```

### .env.example（使用占位符）

```bash
AGENT_NAME={{agent_name}}
IRC_SERVER={{irc_server}}
IRC_PORT={{irc_port}}
IRC_CHANNELS={{irc_channels}}
```

`render_env()` 函数用上下文替换 `{{placeholder}}`。

> 引用：`zchat/cli/template_loader.py:54-79`

### start.sh

agent 的实际启动脚本。Claude 模板的 start.sh 会：
1. Source `.zchat-env` 加载环境变量
2. 启动 Claude Code CLI（带 channel-server MCP 插件）
3. Claude Code 的 SessionStart hook 写入 `.ready` 文件

## tmux 窗口模型

```
tmux session: zchat-e1df88e1-local
├─ window 1: weechat          ← WeeChat IRC 客户端
├─ window 2: alice-agent0     ← Agent0 的 Claude Code
├─ window 3: alice-helper     ← Helper 的 Claude Code
└─ (可继续添加更多 agent)
```

切换方式：
- `Ctrl+b 1/2/3` — 按编号切换
- `zchat agent focus agent0` — CLI 命令切换
- `zchat agent hide all` — 切回 WeeChat

> 引用：[CLAUDE.md](../../../CLAUDE.md) "每个 agent / WeeChat 使用独立 tmux window"

## 测试

```bash
uv run pytest tests/unit/test_agent_manager.py -v
```

覆盖：名称作用域化、工作空间创建/清理、环境变量构建、就绪标记检测。

> 引用：`tests/unit/test_agent_manager.py`

## 下一步

进入 [第六章：IRC 与认证管理](./06-irc-auth.md)。
