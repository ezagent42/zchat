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

SCRIPT_NAME = "weechat-agent"
SCRIPT_AUTHOR = "Allen <ezagent42>"
SCRIPT_VERSION = "0.2.0"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Claude Code agent lifecycle management for WeeChat"

# --- 全局状态 ---
agents = {}                # name → { workspace, pane_id, status }
CHANNEL_PLUGIN_DIR = ""    # weechat-channel-server plugin 路径
TMUX_SESSION = ""          # tmux session 名称
USERNAME = ""              # 当前用户名（用于 agent 名称作用域）
PRIMARY_AGENT = ""         # 主 agent 全名（如 alice:agent0）


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
        agent0_pane = _find_claude_pane()
        agents[PRIMARY_AGENT] = {
            "workspace": weechat.config_get_plugin("agent0_workspace"),
            "status": "running",
            "pane_id": agent0_pane,
        }
        weechat.command("", f"/zenoh join @{PRIMARY_AGENT}")

    # 监听消息 signal，检测 Agent 的结构化命令输出
    weechat.hook_signal("zenoh_message_received",
                        "on_message_signal_cb", "")

    # 监听 presence signal，更新 Agent 状态
    weechat.hook_signal("zenoh_presence_changed",
                        "on_presence_signal_cb", "")


# ============================================================
# Agent Workspace 管理
# ============================================================

def _create_agent_workspace(name):
    """Create a temporary workspace with .mcp.json for the agent."""
    safe = name.replace(":", "-")
    workspace = os.path.join(tempfile.gettempdir(), f"wc-agent-{safe}")
    os.makedirs(workspace, exist_ok=True)

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
    with open(os.path.join(workspace, ".mcp.json"), "w") as f:
        json.dump(config, f)
    return workspace


def _cleanup_agent_workspace(name):
    """Remove the agent's temporary workspace directory."""
    import shutil
    safe = name.replace(":", "-")
    workspace = os.path.join(tempfile.gettempdir(), f"wc-agent-{safe}")
    shutil.rmtree(workspace, ignore_errors=True)


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

    # Create isolated workspace with .mcp.json for this agent
    agent_workspace = _create_agent_workspace(name)
    cmd = (
        f"cd '{agent_workspace}' && "
        f"AGENT_NAME='{name}' "
        f"claude "
        f"--permission-mode bypassPermissions "
        f"--dangerously-load-development-channels server:weechat-channel"
    )
    # Split vertically from the last agent pane (right column)
    target = _last_agent_pane() or TMUX_SESSION
    result = subprocess.run(
        ["tmux", "split-window", "-v", "-P", "-F", "#{pane_id}",
         "-t", target, cmd],
        capture_output=True, text=True
    )
    pane_id = result.stdout.strip()

    agents[name] = {
        "workspace": agent_workspace,
        "status": "starting",
        "pane_id": pane_id,
    }

    # Auto-confirm the --dangerously-load-development-channels prompt
    weechat.hook_timer(3000, 0, 1, "_auto_confirm_cb", pane_id)

    # 创建 private buffer
    weechat.command("", f"/zenoh join @{name}")

    weechat.prnt("",
        f"[agent] Created {name}\n"
        f"  workspace: {agent_workspace}\n"
        f"  pane: {pane_id}\n"
        f"  tmux: Ctrl+b then arrow keys to navigate")


def _auto_confirm_cb(data, remaining_calls):
    """Auto-confirm the development channels warning prompt."""
    pane_id = data
    subprocess.run(
        ["tmux", "send-keys", "-t", pane_id, "Enter"],
        capture_output=True
    )
    return weechat.WEECHAT_RC_OK


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
    """监听 presence 变化，更新 Agent 状态并通知用户"""
    try:
        ev = json.loads(signal_data)
        nick = ev.get("nick", "")
        online = ev.get("online", False)
        if nick in agents:
            if online:
                agents[nick]["status"] = "running"
            else:
                agents[nick]["status"] = "offline"
                # Clean up workspace when agent goes offline
                _cleanup_agent_workspace(nick)
                weechat.prnt("",
                    f"[agent] {nick} is now offline")
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

    elif cmd == "list":
        if not agents:
            weechat.prnt(buffer, "[agent] No agents")
        else:
            for name, info in agents.items():
                pane_id = info.get('pane_id', '?')
                weechat.prnt(buffer,
                    f"  {name}\t{info['status']}\t{pane_id}\t{info['workspace']}")

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
            "  /agent create <n> [--workspace <path>]  — launch new agent\n"
            "  /agent list                             — list agents and panes\n"
            "  /agent join <agent> <#channel>          — ask agent to join channel\n"
            "\n"
            "To stop an agent: switch to its tmux pane and type /exit")

    return weechat.WEECHAT_RC_OK


def restart_timer_cb(data, remaining_calls):
    info = json.loads(data)
    create_agent(info["name"], info["workspace"])
    return weechat.WEECHAT_RC_OK


def agent_deinit():
    for name in list(agents.keys()):
        _cleanup_agent_workspace(name)
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
        "create <n> [--workspace <path>] || list || join <agent> <#channel>",
        "  create: Launch new Claude Code instance\n"
        "    list: List agents, status, and pane IDs\n"
        "    join: Ask agent to join a channel\n"
        "\n"
        "  To stop: go to agent's tmux pane, type /exit",
        "create || list || join",
        "agent_cmd_cb", "")

    agent_init()
