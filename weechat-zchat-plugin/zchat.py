"""zchat — WeeChat Python script for multi-agent collaboration.

Provides:
- /agent command (create/stop/list/restart/send via zchat CLI)
- @mention highlighting for agent nicks
- Agent presence tracking (JOIN/PART/QUIT)
- System message rendering (__zchat_sys: → human-readable)
- Agent status bar item

Protocol implemented independently — no imports from zchat package.
"""

import json
import subprocess
import re

try:
    import weechat
except ImportError:
    # Allow importing for testing without weechat
    weechat = None

SCRIPT_NAME = "zchat"
SCRIPT_AUTHOR = "ezagent42"
SCRIPT_VERSION = "0.1.0"
SCRIPT_LICENSE = "Apache-2.0"
SCRIPT_DESC = "Multi-agent collaboration over IRC"

# --- Protocol constants (independent implementation) ---

AGENT_SEPARATOR = "-"
ZCHAT_SYS_PREFIX = "__zchat_sys:"

# --- Agent state ---

# nick → {"status": "online"/"offline", "channels": [...]}
agent_nicks = {}


# --- Protocol helpers ---

def is_agent_nick(nick):
    """Check if a nick looks like an agent (contains separator)."""
    return AGENT_SEPARATOR in nick


def scoped_name(name, username):
    """Add username prefix if not already scoped."""
    if AGENT_SEPARATOR in name:
        return name
    return f"{username}{AGENT_SEPARATOR}{name}"


def decode_sys_message(text):
    """Decode a __zchat_sys: message. Returns dict or None."""
    if not text.startswith(ZCHAT_SYS_PREFIX):
        return None
    try:
        return json.loads(text[len(ZCHAT_SYS_PREFIX):])
    except (json.JSONDecodeError, ValueError):
        return None


def format_sys_message(msg):
    """Format a system message for human display."""
    msg_type = msg.get("type", "unknown")
    nick = msg.get("nick", "?")
    body = msg.get("body", {})

    type_labels = {
        "sys.stop_request": "stop",
        "sys.join_request": "join",
        "sys.status_request": "status query",
        "sys.status_response": "status",
    }
    label = type_labels.get(msg_type, msg_type.replace("sys.", ""))

    if msg_type == "sys.status_response":
        channels = body.get("channels", [])
        return f"[zchat] {nick}: {label} — channels: {', '.join(channels)}"

    detail = ""
    if body:
        detail = f" — {json.dumps(body)}" if len(body) > 0 else ""
    return f"[zchat] {nick}: {label}{detail}"


# --- /agent command ---

def agent_command_cb(data, buffer, args):
    """Handle /agent command."""
    if not args:
        weechat.prnt(buffer, "[zchat] Usage: /agent <create|stop|list|restart|send> [args]")
        return weechat.WEECHAT_RC_OK

    parts = args.split(None, 1)
    subcmd = parts[0]
    rest = parts[1] if len(parts) > 1 else ""

    if subcmd == "create":
        return _agent_create(buffer, rest)
    elif subcmd == "stop":
        return _agent_stop(buffer, rest)
    elif subcmd == "list":
        return _agent_list(buffer)
    elif subcmd == "restart":
        return _agent_restart(buffer, rest)
    elif subcmd == "send":
        return _agent_send(buffer, rest)
    else:
        weechat.prnt(buffer, f"[zchat] Unknown subcommand: {subcmd}")
        return weechat.WEECHAT_RC_OK


def _run_zchat(buffer, args, success_msg=None):
    """Run zchat CLI command and print output to buffer."""
    cmd = ["zchat"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            output = result.stdout.strip()
            if output:
                for line in output.splitlines():
                    weechat.prnt(buffer, f"[zchat] {line}")
            elif success_msg:
                weechat.prnt(buffer, f"[zchat] {success_msg}")
        else:
            err = result.stderr.strip() or result.stdout.strip()
            weechat.prnt(buffer, f"[zchat] Error: {err}")
    except FileNotFoundError:
        weechat.prnt(buffer, "[zchat] Error: 'zchat' command not found. Is it installed?")
    except subprocess.TimeoutExpired:
        weechat.prnt(buffer, "[zchat] Error: command timed out")
    return weechat.WEECHAT_RC_OK


def _agent_create(buffer, args):
    if not args:
        weechat.prnt(buffer, "[zchat] Usage: /agent create <name> [--workspace <path>]")
        return weechat.WEECHAT_RC_OK
    parts = args.split()
    cmd_args = ["agent", "create"] + parts
    return _run_zchat(buffer, cmd_args, f"Agent '{parts[0]}' created")


def _agent_stop(buffer, args):
    if not args:
        weechat.prnt(buffer, "[zchat] Usage: /agent stop <name>")
        return weechat.WEECHAT_RC_OK
    return _run_zchat(buffer, ["agent", "stop", args.strip()])


def _agent_list(buffer):
    return _run_zchat(buffer, ["agent", "list"])


def _agent_restart(buffer, args):
    if not args:
        weechat.prnt(buffer, "[zchat] Usage: /agent restart <name>")
        return weechat.WEECHAT_RC_OK
    return _run_zchat(buffer, ["agent", "restart", args.strip()])


def _agent_send(buffer, args):
    parts = args.split(None, 1)
    if len(parts) < 2:
        weechat.prnt(buffer, "[zchat] Usage: /agent send <name> <message>")
        return weechat.WEECHAT_RC_OK
    name, message = parts
    return _run_zchat(buffer, ["agent", "send", name, message])


# --- System message modifier ---

def privmsg_modifier_cb(data, modifier, modifier_data, string):
    """Intercept PRIVMSG to render system messages as human-readable text."""
    # Parse IRC PRIVMSG: :nick!user@host PRIVMSG #channel :message
    match = re.match(r"^(:(\S+)\s+)?PRIVMSG\s+(\S+)\s+:(.*)$", string)
    if not match:
        return string

    text = match.group(4)
    sys_msg = decode_sys_message(text)
    if sys_msg is None:
        return string

    formatted = format_sys_message(sys_msg)
    prefix = match.group(1) or ""
    channel = match.group(3)
    return f"{prefix}PRIVMSG {channel} :{formatted}"


# --- Presence tracking ---

def join_signal_cb(data, signal, signal_data):
    """Track agent JOINs."""
    match = re.match(r"^:(\S+?)!", signal_data)
    if match:
        nick = match.group(1)
        if is_agent_nick(nick):
            agent_nicks[nick] = {"status": "online"}
            _update_bar_item()
    return weechat.WEECHAT_RC_OK


def part_signal_cb(data, signal, signal_data):
    """Track agent PARTs."""
    match = re.match(r"^:(\S+?)!", signal_data)
    if match:
        nick = match.group(1)
        if nick in agent_nicks:
            agent_nicks[nick]["status"] = "offline"
            _update_bar_item()
    return weechat.WEECHAT_RC_OK


def quit_signal_cb(data, signal, signal_data):
    """Track agent QUITs."""
    match = re.match(r"^:(\S+?)!", signal_data)
    if match:
        nick = match.group(1)
        if nick in agent_nicks:
            agent_nicks[nick]["status"] = "offline"
            _update_bar_item()
    return weechat.WEECHAT_RC_OK


# --- Bar item ---

def bar_item_cb(data, item, window):
    """Render agent status bar item."""
    if not agent_nicks:
        return ""
    parts = []
    for nick, info in sorted(agent_nicks.items()):
        status = info.get("status", "?")
        color = "green" if status == "online" else "red"
        parts.append(f"{weechat.color(color)}{nick}{weechat.color('reset')}")
    return " ".join(parts)


def _update_bar_item():
    """Trigger bar item refresh."""
    weechat.bar_item_update("zchat_agents")


# --- Script entry point ---

def main():
    weechat.register(
        SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE,
        SCRIPT_DESC, "", ""
    )

    # /agent command
    weechat.hook_command(
        "agent",
        "Manage zchat agents",
        "create <name> [--workspace <path>] || stop <name> || list || restart <name> || send <name> <message>",
        "  create: Create and launch a new agent\n"
        "    stop: Stop a running agent\n"
        "    list: List all agents with status\n"
        " restart: Restart an agent\n"
        "    send: Send a text message to an agent",
        "create || stop || list || restart || send",
        "agent_command_cb", ""
    )

    # System message rendering
    weechat.hook_modifier("irc_in_privmsg", "privmsg_modifier_cb", "")

    # Presence tracking (JOIN/PART/QUIT for all servers)
    weechat.hook_signal("*,irc_in_join", "join_signal_cb", "")
    weechat.hook_signal("*,irc_in_part", "part_signal_cb", "")
    weechat.hook_signal("*,irc_in_quit", "quit_signal_cb", "")

    # Agent status bar item
    weechat.bar_item_new("zchat_agents", "bar_item_cb", "")

    weechat.prnt("", f"[zchat] v{SCRIPT_VERSION} loaded. Use /agent for help.")


if __name__ == "__main__" and weechat is not None:
    main()
