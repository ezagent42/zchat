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

SCRIPT_NAME = "weechat-agent"
SCRIPT_AUTHOR = "Allen <ezagent42>"
SCRIPT_VERSION = "0.1.0"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Claude Code agent lifecycle management for WeeChat"

# --- 全局状态 ---
agents = {}                # name → { workspace, tmux_pane, status }
CHANNEL_PLUGIN_DIR = ""    # weechat-channel-server plugin 路径
TMUX_SESSION = ""          # tmux session 名称
next_pane_id = 1


# ============================================================
# 初始化
# ============================================================

def agent_init():
    global CHANNEL_PLUGIN_DIR, TMUX_SESSION

    CHANNEL_PLUGIN_DIR = weechat.config_get_plugin("channel_plugin_dir")
    TMUX_SESSION = weechat.config_get_plugin("tmux_session") or "weechat-claude"

    # 注册 agent0（由 start.sh 预启动）
    if weechat.config_get_plugin("agent0_workspace"):
        agents["agent0"] = {
            "workspace": weechat.config_get_plugin("agent0_workspace"),
            "status": "running",
        }
        # 为 agent0 创建 private buffer
        weechat.command("", "/zenoh join @agent0")

    # 监听消息 signal，检测 Agent 的结构化命令输出
    weechat.hook_signal("zenoh_message_received",
                        "on_message_signal_cb", "")

    # 监听 presence signal，更新 Agent 状态
    weechat.hook_signal("zenoh_presence_changed",
                        "on_presence_signal_cb", "")


# ============================================================
# Agent 创建
# ============================================================

def create_agent(name, workspace):
    if name in agents:
        weechat.prnt("", f"[agent] {name} already exists")
        return

    if not CHANNEL_PLUGIN_DIR:
        weechat.prnt("",
            "[agent] Error: channel_plugin_dir not set. "
            "Use /set plugins.var.python.weechat-agent.channel_plugin_dir")
        return

    workspace = os.path.abspath(workspace)

    # 1. 在 tmux pane 中启动 Claude Code with channel plugin
    cmd = (
        f"cd '{workspace}' && "
        f"AGENT_NAME='{name}' "
        f"claude "
        f"--dangerously-skip-permissions "
        f"--dangerously-load-development-channels "
        f"plugin:weechat-channel"
    )
    result = subprocess.run(
        ["tmux", "split-window", "-h", "-P", "-F", "#{pane_id}",
         "-t", TMUX_SESSION, cmd],
        capture_output=True, text=True
    )
    pane_id = result.stdout.strip()

    # 2. 注册
    agents[name] = {
        "workspace": workspace,
        "status": "starting",
        "pane_id": pane_id,
    }

    # 3. 通知 weechat-zenoh 创建 private buffer
    weechat.command("", f"/zenoh join @{name}")

    weechat.prnt("", f"[agent] Created {name} in {workspace}")


# ============================================================
# Agent 停止
# ============================================================

def stop_agent(name):
    if name == "agent0":
        weechat.prnt("", "[agent] Cannot stop agent0")
        return
    if name not in agents:
        weechat.prnt("", f"[agent] Unknown agent: {name}")
        return

    # 向 Claude Code 发送退出命令（target specific pane）
    pane_id = agents[name].get("pane_id")
    if pane_id:
        subprocess.run(
            ["tmux", "send-keys", "-t", pane_id, "C-c", ""],
            capture_output=True
        )

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
            agents[nick]["status"] = "running" if online else "offline"
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
        name = argv[1]
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
        agent_name = argv[1]
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
        if name != "agent0":
            stop_agent(name)
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
        "  create: Launch new Claude Code instance\n"
        "    stop: Stop an agent (cannot stop agent0)\n"
        " restart: Restart an agent\n"
        "    list: List all agents and status\n"
        "    join: Ask agent to join a channel",
        "create || stop || restart || list || join",
        "agent_cmd_cb", "")

    agent_init()
