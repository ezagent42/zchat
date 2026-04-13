# 第七章：WeeChat 插件——用户界面层

> 预计阅读：15 分钟

## 概述

`weechat-zchat-plugin/zchat.py` 是一个 WeeChat Python 脚本，为用户提供：

1. `/agent` 命令——在 WeeChat 内管理 agent
2. 系统消息渲染——把 `__zchat_sys:` 消息转成可读文本
3. Agent 状态栏——显示在线/离线状态
4. Presence 跟踪——监听 JOIN/PART/QUIT 事件

> 代码位置：`weechat-zchat-plugin/zchat.py`（284 行）

## 协议独立实现

插件**没有直接依赖 zchat-protocol 包**，而是内联了核心常量：

```python
# zchat.py:29-32
AGENT_SEPARATOR = "-"
ZCHAT_SYS_PREFIX = "__zchat_sys:"
```

这是因为 WeeChat 脚本运行在 WeeChat 的嵌入式 Python 环境中，不能 pip install 外部包。

> 引用：`weechat-zchat-plugin/zchat.py:29-32`

## Agent 状态追踪

```python
# zchat.py:34-37
agent_nicks = {}  # nick → {"status": "online"/"offline", "channels": [...]}
```

全局字典，记录所有已知 agent 的在线状态。

### 判断是否是 Agent

```python
# zchat.py:42-44
def is_agent_nick(nick):
    return AGENT_SEPARATOR in nick
```

包含 `-` 的昵称被认为是 agent（如 `alice-agent0`）。普通用户昵称（如 `alice`）不含 `-`。

> 引用：`weechat-zchat-plugin/zchat.py:42-44`

## /agent 命令

### 命令注册

```python
# zchat.py:249-260（main 函数中）
weechat.hook_command(
    "agent",
    "Manage zchat agents",
    "create|stop|list|restart|send <name> [args]",
    "...",
    "create || stop || list || restart || send",
    "agent_command_cb",
    ""
)
```

### 命令分发

```python
# zchat.py:90-112
def agent_command_cb(data, buffer, args):
    parts = args.split(None, 1)
    subcmd = parts[0] if parts else ""
    rest = parts[1] if len(parts) > 1 else ""
    
    if subcmd == "create":
        _agent_create(buffer, rest)
    elif subcmd == "stop":
        _agent_stop(buffer, rest)
    elif subcmd == "list":
        _agent_list(buffer)
    elif subcmd == "restart":
        _agent_restart(buffer, rest)
    elif subcmd == "send":
        _agent_send(buffer, rest)
```

> 引用：`weechat-zchat-plugin/zchat.py:90-112`

### CLI 调用

所有子命令都通过 subprocess 调用 zchat CLI：

```python
# zchat.py:115-134
def _run_zchat(buffer, args, success_msg=None):
    cmd = ["zchat", "agent"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    
    if result.returncode == 0:
        if success_msg:
            weechat.prnt(buffer, f"[zchat] {success_msg}")
        if result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                weechat.prnt(buffer, f"[zchat] {line}")
    else:
        weechat.prnt(buffer, f"[zchat] Error: {result.stderr.strip()}")
```

**设计选择**：WeeChat 插件不直接操作 tmux 或管理 agent，而是调用 zchat CLI。
这保持了单一职责——CLI 是唯一的管理入口。

> 引用：`weechat-zchat-plugin/zchat.py:115-134`

### 各子命令

```python
# zchat.py:137-170
def _agent_create(buffer, args):
    # 解析 name 和可选 --workspace 参数
    _run_zchat(buffer, ["create", name, ...])

def _agent_stop(buffer, args):
    _run_zchat(buffer, ["stop", name])

def _agent_list(buffer):
    _run_zchat(buffer, ["list"])

def _agent_restart(buffer, args):
    _run_zchat(buffer, ["restart", name])

def _agent_send(buffer, args):
    # 解析 name 和 message
    _run_zchat(buffer, ["send", name, message])
```

> 引用：`weechat-zchat-plugin/zchat.py:137-170`

## 系统消息渲染

WeeChat 的 IRC PRIVMSG modifier 拦截所有消息，检查 `__zchat_sys:` 前缀：

```python
# zchat.py:175-190
def privmsg_modifier_cb(data, modifier, modifier_data, string):
    # 解析 IRC PRIVMSG 格式
    match = re.match(r"^:(\S+?)!\S+ PRIVMSG (\S+) :(.+)$", string)
    if not match:
        return string
    
    nick, target, body = match.groups()
    
    # 检查系统消息前缀
    sys_msg = decode_sys_message(body)
    if sys_msg is None:
        return string  # 普通消息，原样返回
    
    # 替换为可读格式
    formatted = format_sys_message(sys_msg)
    return string.replace(body, formatted)
```

> 引用：`weechat-zchat-plugin/zchat.py:175-190`

### 格式化规则

```python
# zchat.py:64-85
def format_sys_message(msg):
    nick = msg.get("nick", "?")
    msg_type = msg.get("type", "")
    
    type_labels = {
        "sys.stop_request": "stop",
        "sys.stop_confirmed": "stopped",
        "sys.join_request": "join",
        "sys.join_confirmed": "joined",
        "sys.status_request": "status?",
        "sys.status_response": "status",
    }
    
    label = type_labels.get(msg_type, msg_type)
    
    # status_response 特殊处理：显示频道列表
    if msg_type == "sys.status_response":
        channels = ", ".join(msg.get("body", {}).get("channels", []))
        return f"[zchat] {nick}: {label} — channels: {channels}"
    
    return f"[zchat] {nick}: {label}"
```

效果：

| IRC 原始消息 | 渲染后 |
|-------------|--------|
| `__zchat_sys:{"type":"sys.stop_request",...}` | `[zchat] alice: stop` |
| `__zchat_sys:{"type":"sys.status_response","body":{"channels":["#general"]}}` | `[zchat] agent0: status — channels: #general` |

> 引用：`weechat-zchat-plugin/zchat.py:64-85`

## Presence 跟踪

### JOIN 事件

```python
# zchat.py:195-203
def join_signal_cb(data, signal, signal_data):
    match = re.match(r"^:(\S+?)!", signal_data)
    if match:
        nick = match.group(1)
        if is_agent_nick(nick):
            agent_nicks[nick] = {"status": "online", "channels": []}
            _update_bar_item()
    return weechat.WEECHAT_RC_OK
```

### PART / QUIT 事件

```python
# zchat.py:206-225
def part_signal_cb(data, signal, signal_data):
    # 类似逻辑，设置 status = "offline"

def quit_signal_cb(data, signal, signal_data):
    # 类似逻辑，设置 status = "offline"
```

> 引用：`weechat-zchat-plugin/zchat.py:195-225`

## 状态栏

```python
# zchat.py:230-239
def bar_item_cb(data, item, window):
    parts = []
    for nick, info in sorted(agent_nicks.items()):
        if info["status"] == "online":
            color = weechat.color("green")
        else:
            color = weechat.color("red")
        reset = weechat.color("reset")
        parts.append(f"{color}{nick}{reset}")
    return " ".join(parts)
```

在 WeeChat 状态栏显示所有 agent，在线绿色，离线红色。

> 引用：`weechat-zchat-plugin/zchat.py:230-239`

## Hook 注册汇总

```python
# zchat.py:249-280（main 函数）
def main():
    weechat.register(SCRIPT_NAME, ...)
    
    # 命令
    weechat.hook_command("agent", ...)
    
    # 消息拦截
    weechat.hook_modifier("irc_in_privmsg", "privmsg_modifier_cb", "")
    
    # Presence 事件
    weechat.hook_signal("*,irc_in_join", "join_signal_cb", "")
    weechat.hook_signal("*,irc_in_part", "part_signal_cb", "")
    weechat.hook_signal("*,irc_in_quit", "quit_signal_cb", "")
    
    # 状态栏
    weechat.bar_item_new("zchat_agents", "bar_item_cb", "")
```

> 引用：`weechat-zchat-plugin/zchat.py:249-280`

## 测试

```python
# weechat-zchat-plugin/tests/test_weechat_plugin.py
# 测试协议一致性：separator、sys_prefix、scoped_name
# 测试命令参数解析
```

> 引用：`weechat-zchat-plugin/tests/test_weechat_plugin.py`

## 下一步

进入 [第八章：消息全链路 + 运维 + 扩展](./08-end-to-end.md)。
