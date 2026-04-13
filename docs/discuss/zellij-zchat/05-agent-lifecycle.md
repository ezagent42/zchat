# 第五章：Agent 生命周期管理

> 预计阅读：25 分钟
>
> 基于 [旧版第五章](../introduce/05-agent-lifecycle.md) 更新，核心流程不变，tmux → Zellij 适配。

## 概述

AgentManager 管理 agent 从创建到销毁的完整生命周期。核心状态机不变：

```
create → spawn Zellij tab → auto-confirm → wait for ready → running → stop → cleanup
```

> 代码位置：`zchat/cli/agent_manager.py`

## 状态机

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
         │offline│  Zellij tab 已关闭
         └───────┘
```

状态存储在 `state.json`：

```python
self._agents[scoped] = {
    "type": agent_type,
    "workspace": workspace,
    "tab_name": tab_name,       # 旧版是 window_name
    "status": "starting",
    "created_at": time.time(),
    "channels": channels,
}
```

## 创建流程

### Step 1：名称作用域化

```python
scoped = self.scoped(name)  # "agent0" → "yaosh-agent0"

if scoped in self._agents and self._check_alive(scoped) == "running":
    raise ValueError(f"{scoped} already running")
```

### Step 2：创建工作空间 & 环境变量

工作空间创建和环境变量构建与旧版相同——参见 [旧版第五章 Step 2-3](../introduce/05-agent-lifecycle.md)。

环境变量写入 `{workspace}/.zchat-env`：

```bash
AGENT_NAME=yaosh-agent0
IRC_SERVER=127.0.0.1
IRC_PORT=6667
IRC_CHANNELS=general
IRC_TLS=false
IRC_AUTH_TOKEN=...
```

### Step 3：创建 Zellij tab（替代 tmux window）

```python
# agent_manager.py — _spawn_tab()（旧版是 _spawn_tmux）
def _spawn_tab(self, name, workspace, agent_type, channels):
    context = self._build_env_context(name, workspace, channels)
    env = render_env(agent_type, context)
    
    # 叠加项目级 env_file
    if self._env_file and os.path.isfile(self._env_file):
        env.update(parse_env(self._env_file))
    
    # 写 .zchat-env 到工作空间
    env_path = os.path.join(workspace, ".zchat-env")
    with open(env_path, "w") as f:
        for k, v in env.items():
            f.write(f"export {k}={shlex.quote(v)}\n")
    
    # 获取启动脚本
    start_script = get_start_script(agent_type)
    cmd = f"cd '{workspace}' && bash '{start_script}'"
    
    # ✨ 新：创建 Zellij tab（旧版是 tmux window）
    zellij.new_tab(self._session_name, name, command=cmd)
    
    # 启动自动确认线程
    self._auto_confirm_startup(name)
    
    return name  # tab_name
```

**关键区别**：`tmux_session.new_window()` → `zellij.new_tab()`。

每个 agent 是独立的 Zellij tab（不是 pane），好处：
- 互不干扰
- 可通过 tab 栏直接点击切换
- 停止时关闭 tab 即可

### Step 4：自动确认启动提示

Claude Code 启动时有确认提示，需要自动按 Enter：

```python
def _auto_confirm_startup(self, tab_name, timeout=60):
    def _poll():
        pane_id = zellij.get_pane_id(self._session_name, tab_name)
        deadline = time.time() + timeout
        while time.time() < deadline:
            # ✨ 新：通过 Zellij pane 事件流读取内容
            # 旧版用 tmux capture-pane
            content = _read_pane_content(self._session_name, pane_id)
            
            for pattern in ["I trust this folder", "Enter to confirm", ...]:
                if pattern in content:
                    zellij.send_command(self._session_name, pane_id, "")
                    return
            
            time.sleep(1)
    
    t = threading.Thread(target=_poll, daemon=True)
    t.start()
```

### Step 5：等待就绪

```python
def _wait_for_ready(self, name, timeout=60):
    ready_file = os.path.join(self._project_dir, "agents", f"{name}.ready")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.isfile(ready_file):
            return True
        time.sleep(0.5)
    return False
```

`.ready` 文件由 Claude Code 的 **SessionStart hook** 自动创建。这个机制完全不变。

## 停止流程

```python
def stop(self, name, force=False):
    scoped = self.scoped(name)
    
    # 1. 执行 pre_stop hook（模板定义）
    template_meta = load_template(agent_type)
    pre_stop = template_meta.get("hooks", {}).get("pre_stop", "")
    if pre_stop:
        pane_id = zellij.get_pane_id(self._session_name, scoped)
        zellij.send_command(self._session_name, pane_id, pre_stop)
        
        # 等待 tab 自行关闭（最多 10 秒）
        for _ in range(20):
            if not zellij.tab_exists(self._session_name, scoped):
                break
            time.sleep(0.5)
    
    # 2. 强制关闭 tab
    if zellij.tab_exists(self._session_name, scoped):
        zellij.close_tab(self._session_name, scoped)
    
    # 3. 清理：只删 .ready 标记，保留工作目录
    ready_file = os.path.join(self._project_dir, "agents", f"{scoped}.ready")
    if os.path.isfile(ready_file):
        os.remove(ready_file)
    
    # 4. 更新状态
    self._agents[scoped]["status"] = "offline"
    self._save_state()
```

## 存活检测

```python
def _check_alive(self, name):
    info = self._agents.get(name, {})
    tab_name = info.get("tab_name")  # 旧版是 window_name
    if tab_name and zellij.tab_exists(self._session_name, tab_name):
        return "running"
    return "offline"
```

## Zellij tab 布局

```
Zellij Session: zchat-local
┌──────────────────────────────────────────────────────┐
│ [chat] │ [ctl] │ [yaosh-agent0] │ [yaosh-helper]    │  ← tab 栏
├──────────────────────────────────────────────────────┤
│                                                      │
│          当前选中 tab 的 pane 内容                      │
│                                                      │
└──────────────────────────────────────────────────────┘
```

切换方式：
- `Alt+1/2/3` — 按编号切换
- `zchat agent focus agent0` — CLI 命令切换
- `zchat agent hide` — 切回 chat tab
- 点击 tab 栏

## 其他操作

### 发送消息、重启、模板系统

这些功能的逻辑与旧版完全相同，只是底层的 tmux 调用替换为 zellij 调用。参见 [旧版第五章](../introduce/05-agent-lifecycle.md) 的"发送消息"、"重启"、"模板系统"章节。

## 测试

```bash
uv run pytest tests/unit/test_agent_manager.py -v
```

## 下一步

- IRC 与认证管理：参见 [旧版第六章](../introduce/06-irc-auth.md)（小幅更新：tmux → Zellij）
- WeeChat 插件：参见 [旧版第七章](../introduce/07-weechat-plugin.md)（无变化）
- 通信全链路：进入 [第八章](./08-communication.md)
