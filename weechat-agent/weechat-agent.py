#!/usr/bin/env python3
# weechat-agent.py

"""
Claude Code Agent 生命周期管理
依赖 weechat-zenoh.py（通过 WeeChat 命令交互）
"""

import weechat
import json
import os
import subprocess
import tempfile
import time

SCRIPT_NAME = "weechat-agent"
SCRIPT_AUTHOR = "Allen <ezagent42>"
SCRIPT_VERSION = "0.1.0"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Claude Code agent lifecycle management for WeeChat"

# --- 全局状态 ---
agents = {}                # name → { workspace, tmux_pane, status }
CHANNEL_PLUGIN_DIR = ""    # weechat-channel-server plugin 路径
TMUX_SESSION = ""          # tmux session 名称
USERNAME = ""              # 当前用户名（用于 agent 名称作用域）
PRIMARY_AGENT = ""         # 主 agent 全名（如 alice:agent0）
next_pane_id = 1


def scoped_name(name):
    """给 agent 名称加上用户名前缀（如已有前缀则不重复添加）。"""
    if ":" in name:
        return name
    return f"{USERNAME}:{name}"


# ============================================================
# 初始化
# ============================================================

def agent_init():
    global CHANNEL_PLUGIN_DIR, TMUX_SESSION, USERNAME, PRIMARY_AGENT

    CHANNEL_PLUGIN_DIR = weechat.config_get_plugin("channel_plugin_dir")
    TMUX_SESSION = weechat.config_get_plugin("tmux_session") or "weechat-claude"
    USERNAME = weechat.config_string(
        weechat.config_get("plugins.var.python.weechat-zenoh.nick")
    ) or os.environ.get("USER", "user")

    PRIMARY_AGENT = scoped_name("agent0")

    # 注册 agent0（由 start.sh 预启动）
    if weechat.config_get_plugin("agent0_workspace"):
        # 找到 agent0 的 tmux pane（运行 claude 的 pane）
        agent0_pane = _find_claude_pane()
        agents[PRIMARY_AGENT] = {
            "workspace": weechat.config_get_plugin("agent0_workspace"),
            "status": "running",
            "pane_id": agent0_pane,
        }
        # 为 agent0 创建 private buffer
        weechat.command("", f"/zenoh join @{PRIMARY_AGENT}")

    # 监听消息 signal，检测 Agent 的结构化命令输出
    weechat.hook_signal("zenoh_message_received",
                        "on_message_signal_cb", "")

    # 监听 presence signal，更新 Agent 状态
    weechat.hook_signal("zenoh_presence_changed",
                        "on_presence_signal_cb", "")


# ============================================================
# MCP Config 生成
# ============================================================

def _mcp_config_path(name):
    """返回 agent 对应的临时 MCP config 路径。"""
    safe = name.replace(":", "-")
    return os.path.join(tempfile.gettempdir(), f"wc-mcp-{safe}.json")


def _generate_mcp_config(name):
    """生成 MCP config JSON，返回文件路径。"""
    config = {
        "mcpServers": {
            "weechat-channel": {
                "type": "stdio",
                "command": "uv",
                "args": [
                    "run", "--project", CHANNEL_PLUGIN_DIR,
                    "python3", os.path.join(CHANNEL_PLUGIN_DIR, "server.py"),
                ],
                "env": {
                    "AGENT_NAME": name,
                    "AUTOJOIN_CHANNELS": "general",
                },
            }
        }
    }
    path = _mcp_config_path(name)
    with open(path, "w") as f:
        json.dump(config, f)
    return path


def _cleanup_mcp_config(name):
    """删除 agent 的临时 MCP config。"""
    path = _mcp_config_path(name)
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _find_claude_pane():
    """Find the tmux pane running claude in the current session."""
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-t", TMUX_SESSION,
             "-F", "#{pane_id}:#{pane_current_command}"],
            capture_output=True, text=True)
        for line in result.stdout.strip().split("\n"):
            if ":" in line:
                pane_id, cmd = line.split(":", 1)
                # claude shows as its version number (e.g. 2.1.81) in pane_current_command
                if cmd and cmd not in ("weechat", "zsh", "bash"):
                    return pane_id
    except Exception:
        pass
    return ""


def _last_agent_pane():
    """Return the pane_id of the last registered agent (for split targeting)."""
    for name in reversed(list(agents.keys())):
        pane = agents[name].get("pane_id")
        if pane:
            return pane
    return ""


# ============================================================
# Agent 创建
# ============================================================

def create_agent(name, workspace):
    name = scoped_name(name)
    if name in agents:
        weechat.prnt("", f"[agent] {name} already exists")
        return

    if not CHANNEL_PLUGIN_DIR:
        weechat.prnt("",
            "[agent] Error: channel_plugin_dir not set. "
            "Use /set plugins.var.python.weechat-agent.channel_plugin_dir")
        return

    workspace = os.path.abspath(workspace)

    # 1. 生成 MCP config 并在 tmux pane 中启动 Claude Code
    mcp_config = _generate_mcp_config(name)
    cmd = (
        f"cd '{workspace}' && "
        f"claude "
        f"--permission-mode bypassPermissions "
        f"--mcp-config '{mcp_config}'"
    )
    # Split vertically from the last agent pane (right column),
    # so agents stack below agent0.
    target = _last_agent_pane() or TMUX_SESSION
    result = subprocess.run(
        ["tmux", "split-window", "-v", "-P", "-F", "#{pane_id}",
         "-t", target, cmd],
        capture_output=True, text=True
    )
    pane_id = result.stdout.strip()

    # 2. 注册
    agents[name] = {
        "workspace": workspace,
        "status": "starting",
        "pane_id": pane_id,
        "mcp_config": mcp_config,
    }

    # 3. 通知 weechat-zenoh 创建 private buffer
    weechat.command("", f"/zenoh join @{name}")

    weechat.prnt("", f"[agent] Created {name} in {workspace}")


# ============================================================
# Agent 停止
# ============================================================

def stop_agent(name):
    name = scoped_name(name)
    if name == PRIMARY_AGENT:
        weechat.prnt("", f"[agent] Cannot stop {PRIMARY_AGENT}")
        return
    if name not in agents:
        weechat.prnt("", f"[agent] Unknown agent: {name}")
        return

    pane_id = agents[name].get("pane_id")
    if pane_id:
        # Send /exit to claude's tmux pane (non-blocking).
        # When claude exits, its channel-server closes the Zenoh session,
        # which invalidates liveliness tokens. The presence offline event
        # triggers on_presence_signal_cb → _finalize_stop.
        subprocess.run(
            ["tmux", "send-keys", "-t", pane_id, "/exit", "Enter"],
            capture_output=True
        )
        agents[name]["status"] = "stopping"
        weechat.prnt("", f"[agent] Stopping {name}...")

        # Timeout: if presence event doesn't arrive in 15s, force cleanup
        weechat.hook_timer(15000, 0, 1, "_stop_timeout_cb",
                          json.dumps({"name": name, "pane_id": pane_id}))
    else:
        _finalize_stop(name, "")


def _stop_timeout_cb(data, remaining_calls):
    """Timeout fallback if presence offline event never arrives."""
    info = json.loads(data)
    name = info["name"]
    if name in agents and agents[name].get("status") == "stopping":
        weechat.prnt("", f"[agent] {name} did not exit gracefully, forcing stop")
        _finalize_stop(name, info.get("pane_id", ""))
    return weechat.WEECHAT_RC_OK


def _finalize_stop(name, pane_id):
    """Clean up after agent stop: kill pane, remove config, update status."""
    if pane_id:
        subprocess.run(
            ["tmux", "kill-pane", "-t", pane_id],
            capture_output=True
        )
    _cleanup_mcp_config(name)
    if name in agents:
        agents[name]["status"] = "stopped"
    weechat.prnt("", f"[agent] Stopped {name}")


# ============================================================
# Signal 处理
# ============================================================

def on_message_signal_cb(data, signal, signal_data):
    """监听 zenoh 消息，检测 Agent 的结构化命令"""
    try:
        msg = json.loads(signal_data)
        nick = msg.get("nick", "")
        body = msg.get("body", "")

        # 检测 Agent 输出的结构化命令
        if nick in agents and body.strip().startswith("{"):
            try:
                cmd = json.loads(body.strip())
                if cmd.get("action") == "create_agent":
                    create_agent(
                        cmd["name"],
                        cmd.get("workspace", os.getcwd())
                    )
            except (json.JSONDecodeError, KeyError):
                pass

    except Exception:
        pass
    return weechat.WEECHAT_RC_OK


def on_presence_signal_cb(data, signal, signal_data):
    """监听 presence 变化，更新 Agent 状态"""
    try:
        ev = json.loads(signal_data)
        nick = ev.get("nick", "")
        online = ev.get("online", False)
        if nick in agents:
            if online:
                agents[nick]["status"] = "running"
            elif agents[nick].get("status") == "stopping":
                # Agent went offline after /agent stop — complete the stop
                _finalize_stop(nick, agents[nick].get("pane_id", ""))
            else:
                agents[nick]["status"] = "offline"
    except Exception:
        pass
    return weechat.WEECHAT_RC_OK


# ============================================================
# /agent 命令
# ============================================================

def agent_cmd_cb(data, buffer, args):
    argv = args.split()
    cmd = argv[0] if argv else "help"

    if cmd == "create" and len(argv) >= 2:
        name = argv[1]
        workspace = os.getcwd()
        for i, a in enumerate(argv):
            if a == "--workspace" and i + 1 < len(argv):
                workspace = argv[i + 1]
        create_agent(name, workspace)

    elif cmd == "stop" and len(argv) >= 2:
        stop_agent(argv[1])

    elif cmd == "restart" and len(argv) >= 2:
        name = scoped_name(argv[1])
        if name in agents:
            ws = agents[name]["workspace"]
            stop_agent(name)
            del agents[name]
            weechat.hook_timer(2000, 0, 1, "restart_timer_cb",
                              json.dumps({"name": name, "workspace": ws}))

    elif cmd == "list":
        if not agents:
            weechat.prnt(buffer, "[agent] No agents")
        else:
            for name, info in agents.items():
                weechat.prnt(buffer,
                    f"  {name}\t{info['status']}\t{info['workspace']}")

    elif cmd == "join" and len(argv) >= 3:
        agent_name = scoped_name(argv[1])
        channel = argv[2]
        if agent_name not in agents:
            weechat.prnt(buffer, f"[agent] Unknown agent: {agent_name}")
        else:
            weechat.command("",
                f"/zenoh send @{agent_name} "
                f"Please join channel {channel} and monitor it for messages mentioning you.")
            weechat.prnt(buffer,
                f"[agent] Asked {agent_name} to join {channel}")

    else:
        weechat.prnt(buffer,
            "[agent] Commands:\n"
            "  /agent create <n> [--workspace <path>]\n"
            "  /agent stop <n>\n"
            "  /agent restart <n>\n"
            "  /agent list\n"
            "  /agent join <agent> <#channel>")

    return weechat.WEECHAT_RC_OK


def restart_timer_cb(data, remaining_calls):
    info = json.loads(data)
    create_agent(info["name"], info["workspace"])
    return weechat.WEECHAT_RC_OK


def agent_deinit():
    for name in list(agents.keys()):
        if name != PRIMARY_AGENT:
            stop_agent(name)
        _cleanup_mcp_config(name)
    return weechat.WEECHAT_RC_OK


# ============================================================
# 插件注册
# ============================================================

if weechat.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION,
                    SCRIPT_LICENSE, SCRIPT_DESC, "agent_deinit", ""):
    for key, val in {
        "channel_plugin_dir": "",
        "tmux_session": "weechat-claude",
        "agent0_workspace": "",
    }.items():
        if not weechat.config_is_set_plugin(key):
            weechat.config_set_plugin(key, val)

    weechat.hook_command("agent",
        "Manage Claude Code agents",
        "create <n> [--workspace <path>] || stop <n> || "
        "restart <n> || list || join <agent> <#channel>",
        "  create: Launch new Claude Code instance (name auto-scoped to user)\n"
        "    stop: Stop an agent (cannot stop primary agent)\n"
        " restart: Restart an agent\n"
        "    list: List all agents and status\n"
        "    join: Ask agent to join a channel",
        "create || stop || restart || list || join",
        "agent_cmd_cb", "")

    agent_init()
