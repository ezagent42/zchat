#!/usr/bin/env python3
# weechat-zenoh.py

"""
WeeChat Zenoh P2P 聊天插件 (sidecar architecture)
Zenoh 操作委托给 zenoh_sidecar.py 子进程，通过 JSON Lines 通信
"""

import weechat
import json
import os
import subprocess
import sys
from collections import deque
import shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))
from wc_protocol.topics import target_to_buffer_label, parse_input, make_private_pair, extract_other_nick
from wc_protocol.signals import SIGNAL_MESSAGE_SENT, SIGNAL_MESSAGE_RECEIVED, SIGNAL_PRESENCE_CHANGED
from wc_registry import CommandRegistry
from wc_registry.types import CommandParam, CommandResult, ParsedArgs

SCRIPT_NAME = "weechat-zenoh"
SCRIPT_AUTHOR = "Allen <ezagent42>"
SCRIPT_VERSION = "0.2.0"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "P2P chat over Zenoh for WeeChat (sidecar)"

# --- Global state ---
sidecar_proc = None
sidecar_fd_hook = None
read_buffer = ""
sidecar_connected = False
pending_autojoin = ""     # targets to join on ready event
pending_status_buffer = "" # buffer ptr to print status response to
msg_queue = deque()
presence_queue = deque()
buffers = {}              # buffer_key → weechat buffer ptr
my_nick = ""
channels = set()
privates = set()


# ============================================================
# Sidecar IPC
# ============================================================

def _sidecar_path():
    """Resolve zenoh_sidecar.py relative to this plugin."""
    plugin_dir = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(plugin_dir, "zenoh_sidecar.py")


def _start_sidecar():
    """Launch sidecar subprocess."""
    global sidecar_proc, sidecar_fd_hook, read_buffer, sidecar_connected
    read_buffer = ""
    sidecar_connected = False

    # stderr → log file
    weechat_dir = weechat.info_get("weechat_dir", "")
    log_dir = os.path.join(weechat_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = open(os.path.join(log_dir, "zenoh_sidecar.log"), "a")

    # sys.executable inside WeeChat points to the WeeChat binary, not python3.
    python_bin = shutil.which("python3") or "python3"
    sidecar_proc = subprocess.Popen(
        [python_bin, "-u", _sidecar_path()],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=log_file)
    log_file.close()  # Popen dupes the fd; close parent's copy

    # Monitor stdout with hook_fd
    fd = sidecar_proc.stdout.fileno()
    sidecar_fd_hook = weechat.hook_fd(fd, 1, 0, 0, "_on_sidecar_fd", "")


def _stop_sidecar():
    """Terminate sidecar subprocess."""
    global sidecar_proc, sidecar_fd_hook, sidecar_connected
    if sidecar_fd_hook:
        weechat.unhook(sidecar_fd_hook)
        sidecar_fd_hook = None
    if sidecar_proc:
        try:
            sidecar_proc.stdin.close()
        except Exception:
            pass
        sidecar_proc.terminate()
        try:
            sidecar_proc.wait(timeout=3)
        except Exception:
            sidecar_proc.kill()
        sidecar_proc = None
    sidecar_connected = False


def _sidecar_raw_publish(topic: str, payload: dict):
    """Publish raw JSON to a Zenoh topic via sidecar (no msg envelope)."""
    _sidecar_send({"cmd": "raw_publish", "topic": topic, "payload": payload})


def _on_raw_publish_signal(data, signal, signal_data):
    """Handle raw_publish requests from other plugins (e.g. weechat-agent).
    signal_data is JSON: {"topic": "wc/...", "payload": {...}}
    """
    try:
        req = json.loads(signal_data)
        _sidecar_raw_publish(req["topic"], req["payload"])
    except (json.JSONDecodeError, KeyError):
        pass
    return weechat.WEECHAT_RC_OK


def _sidecar_send(cmd: dict):
    """Send JSON command to sidecar stdin."""
    if not sidecar_proc or sidecar_proc.poll() is not None:
        weechat.prnt("", "[zenoh] Sidecar not running. Use /zenoh reconnect")
        return
    try:
        sidecar_proc.stdin.write((json.dumps(cmd) + "\n").encode())
        sidecar_proc.stdin.flush()
    except (BrokenPipeError, OSError) as e:
        weechat.prnt("", f"[zenoh] Sidecar write error: {e}")
        _handle_sidecar_crash()


def _on_sidecar_fd(data, fd):
    """hook_fd callback — read available data, parse JSON lines."""
    global read_buffer, sidecar_connected
    try:
        chunk = os.read(int(fd), 65536)
    except OSError:
        _handle_sidecar_crash()
        return weechat.WEECHAT_RC_OK

    if not chunk:
        _handle_sidecar_crash()
        return weechat.WEECHAT_RC_OK

    read_buffer += chunk.decode("utf-8", errors="replace")
    while "\n" in read_buffer:
        line, read_buffer = read_buffer.split("\n", 1)
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        _handle_event(event)

    return weechat.WEECHAT_RC_OK


def _handle_event(event: dict):
    """Process a single event from sidecar."""
    global sidecar_connected, my_nick
    etype = event.get("event")

    if etype == "ready":
        sidecar_connected = True
        # Always sync nick to sidecar: -r flag or hook_config may have
        # changed my_nick after init sent the wrong one to sidecar.
        # set_nick is idempotent so this is safe even when nick matches.
        _sidecar_send({"cmd": "set_nick", "nick": my_nick})
        weechat.prnt("",
            f"[zenoh] Session opened, nick={my_nick}, "
            f"zid={event.get('zid', '?')[:8]}...")
        # Process pending autojoin
        global pending_autojoin
        if pending_autojoin:
            for target in pending_autojoin.split(","):
                target = target.strip()
                if target:
                    join(target)
            pending_autojoin = ""

    elif etype == "message":
        msg = event.get("msg", {})
        target = event.get("target", "")
        msg["_target"] = target
        msg_queue.append(msg)

    elif etype == "presence":
        presence_queue.append(event)

    elif etype == "status_response":
        global pending_status_buffer
        buf = pending_status_buffer
        pending_status_buffer = ""
        if buf:
            weechat.prnt(buf,
                f"[zenoh] zid={event['zid'][:8]}... nick={my_nick}\n"
                f"  mode=client  channels={event.get('channels', 0)} "
                f"privates={event.get('privates', 0)}\n"
                f"  routers={len(event.get('routers', []))} "
                f"peers={len(event.get('peers', []))}\n"
                f"  sidecar=running")

    elif etype == "error":
        weechat.prnt("", f"[zenoh] Sidecar error: {event.get('detail')}")


def _handle_sidecar_crash():
    """Called when sidecar stdout reaches EOF."""
    global sidecar_connected
    sidecar_connected = False
    weechat.prnt("",
        "[zenoh] Sidecar process crashed. Use /zenoh reconnect")
    for buf in buffers.values():
        weechat.prnt(buf,
            "[zenoh] Connection lost. Use /zenoh reconnect")


def _on_nick_config_changed(data, option, value):
    """hook_config callback — nick changed externally (e.g. via -r flag)."""
    global my_nick
    if value and value != my_nick:
        old = my_nick
        my_nick = value
        if sidecar_connected:
            _sidecar_send({"cmd": "set_nick", "nick": my_nick})
            weechat.prnt("", f"[zenoh] Nick changed: {old} → {my_nick}")
    return weechat.WEECHAT_RC_OK


# ============================================================
# Init / Deinit
# ============================================================

def zc_init():
    global my_nick
    my_nick = weechat.config_get_plugin("nick")
    if not my_nick:
        import uuid
        my_nick = os.environ.get("USER", "user_%s" % uuid.uuid4().hex[:6])
        weechat.config_set_plugin("nick", my_nick)

    _start_sidecar()

    connect = weechat.config_get_plugin("connect")
    cmd = {"cmd": "init", "nick": my_nick}
    if connect:
        cmd["connect"] = connect
    _sidecar_send(cmd)

    # React to nick changes (e.g. from -r flag after plugin init)
    weechat.hook_config("plugins.var.python.weechat-zenoh.nick",
                        "_on_nick_config_changed", "")

    # Timer for queue processing
    weechat.hook_timer(50, 0, 0, "poll_queues_cb", "")
    weechat.hook_signal("zenoh_raw_publish", "_on_raw_publish_signal", "")

    # Autojoin — deferred until ready event arrives
    global pending_autojoin
    autojoin = weechat.config_get_plugin("autojoin")
    if autojoin:
        pending_autojoin = autojoin


def zc_deinit():
    _stop_sidecar()
    return weechat.WEECHAT_RC_OK


# ============================================================
# Channel / Private management
# ============================================================

def join(target):
    if target.startswith("#"):
        join_channel(target.lstrip("#"))
    elif target.startswith("@"):
        join_private(target.lstrip("@"))
    else:
        join_channel(target)


def join_channel(channel_id):
    if channel_id in channels:
        weechat.prnt("", f"[zenoh] Already in #{channel_id}")
        return

    # Create buffer locally
    buf = weechat.buffer_new(
        f"zenoh.#{channel_id}", "buffer_input_cb", "",
        "buffer_close_cb", "")
    weechat.buffer_set(buf, "title", f"Zenoh: #{channel_id}")
    weechat.buffer_set(buf, "short_name", f"#{channel_id}")
    weechat.buffer_set(buf, "nicklist", "1")
    weechat.buffer_set(buf, "localvar_set_type", "channel")
    weechat.buffer_set(buf, "localvar_set_target", channel_id)
    weechat.nicklist_add_nick(buf, "", my_nick, "default", "", "", 1)
    buffers[f"channel:{channel_id}"] = buf
    channels.add(channel_id)

    # Tell sidecar
    _sidecar_send({"cmd": "join_channel", "channel_id": channel_id})
    weechat.prnt(buf, f"-->\t{my_nick} joined #{channel_id}")


def join_private(target_nick):
    pair = make_private_pair(my_nick, target_nick)
    if pair in privates:
        return

    buf = weechat.buffer_new(
        f"zenoh.@{target_nick}", "buffer_input_cb", "",
        "buffer_close_cb", "")
    weechat.buffer_set(buf, "title", f"Private with {target_nick}")
    weechat.buffer_set(buf, "short_name", f"@{target_nick}")
    weechat.buffer_set(buf, "nicklist", "1")
    weechat.buffer_set(buf, "localvar_set_type", "private")
    weechat.buffer_set(buf, "localvar_set_target", target_nick)
    weechat.buffer_set(buf, "localvar_set_private_pair", pair)
    weechat.nicklist_add_nick(buf, "", target_nick, "cyan", "", "", 1)
    weechat.nicklist_add_nick(buf, "", my_nick, "default", "", "", 1)
    buffers[f"private:{pair}"] = buf
    privates.add(pair)

    _sidecar_send({"cmd": "join_private", "target_nick": target_nick})


def leave(target):
    if target.startswith("#"):
        leave_channel(target.lstrip("#"))
    elif target.startswith("@"):
        leave_private(target.lstrip("@"))


def leave_channel(channel_id):
    if channel_id not in channels:
        return
    key = f"channel:{channel_id}"
    _sidecar_send({"cmd": "leave_channel", "channel_id": channel_id})
    if key in buffers:
        weechat.buffer_close(buffers.pop(key))
    channels.discard(channel_id)


def leave_private(target_nick):
    pair = make_private_pair(my_nick, target_nick)
    key = f"private:{pair}"
    _sidecar_send({"cmd": "leave_private", "target_nick": target_nick})
    if key in buffers:
        weechat.buffer_close(buffers.pop(key))
    privates.discard(pair)


# ============================================================
# Message sending
# ============================================================

def send_message(target, body):
    if target.startswith("#"):
        channel_id = target.lstrip("#")
        key = f"channel:{channel_id}"
        _sidecar_send({"cmd": "send", "pub_key": key,
                        "type": "msg", "body": body})
        buf = buffers.get(key)
        if buf:
            weechat.prnt(buf, f"{my_nick}\t{body}")
    elif target.startswith("@"):
        nick = target.lstrip("@")
        pair = make_private_pair(my_nick, nick)
        key = f"private:{pair}"
        if pair not in privates:
            join_private(nick)
        _sidecar_send({"cmd": "send", "pub_key": key,
                        "type": "msg", "body": body})
        buf = buffers.get(key)
        if buf:
            weechat.prnt(buf, f"{my_nick}\t{body}")


def buffer_input_cb(data, buffer, input_data):
    buf_type = weechat.buffer_get_string(buffer, "localvar_type")
    target = weechat.buffer_get_string(buffer, "localvar_target")
    msg_type, body = parse_input(input_data)

    if buf_type == "channel":
        pub_key = f"channel:{target}"
        buffer_label = f"channel:#{target}"
    elif buf_type == "private":
        pair = weechat.buffer_get_string(buffer, "localvar_private_pair")
        pub_key = f"private:{pair}"
        buffer_label = f"private:@{target}"
    else:
        return weechat.WEECHAT_RC_OK

    _sidecar_send({"cmd": "send", "pub_key": pub_key,
                    "type": msg_type, "body": body})
    if msg_type == "action":
        weechat.prnt(buffer, f" *\t{my_nick} {body}")
    else:
        weechat.prnt(buffer, f"{my_nick}\t{body}")
    weechat.hook_signal_send(SIGNAL_MESSAGE_SENT,
        weechat.WEECHAT_HOOK_SIGNAL_STRING,
        json.dumps({"buffer": buffer_label, "nick": my_nick,
                    "body": body, "type": msg_type}))
    return weechat.WEECHAT_RC_OK


def buffer_close_cb(data, buffer):
    buf_type = weechat.buffer_get_string(buffer, "localvar_type")
    target = weechat.buffer_get_string(buffer, "localvar_target")
    if buf_type == "channel":
        leave_channel(target)
    elif buf_type == "private":
        leave_private(target)
    return weechat.WEECHAT_RC_OK


# ============================================================
# Queue polling (unchanged logic)
# ============================================================

def poll_queues_cb(data, remaining_calls):
    for _ in range(200):
        try:
            msg = msg_queue.popleft()
        except IndexError:
            break
        target = msg.get("_target", "")
        buf = buffers.get(target)
        if not buf:
            # Auto-open private buffer when receiving a private message
            if target.startswith("private:"):
                pair = target.split(":", 1)[1]
                other_nick = extract_other_nick(pair, my_nick)
                if other_nick != pair:
                    join_private(other_nick)
                    buf = buffers.get(target)
            if not buf:
                continue
        nick = msg.get("nick", "???")
        body = msg.get("body", "")
        msg_type = msg.get("type", "msg")

        if msg_type == "msg":
            weechat.prnt(buf, f"{nick}\t{body}")
        elif msg_type == "action":
            weechat.prnt(buf, f" *\t{nick} {body}")
        elif msg_type == "join":
            weechat.prnt(buf, f"-->\t{nick} joined")
            channel_id = target.replace("channel:", "")
            _add_nick(channel_id, nick)
        elif msg_type == "leave":
            weechat.prnt(buf, f"<--\t{nick} left")
            channel_id = target.replace("channel:", "")
            _remove_nick(channel_id, nick)
        elif msg_type == "nick":
            try:
                nick_info = json.loads(body)
                old_nick = nick_info.get("old", "")
                new_nick = nick_info.get("new", "")
                if old_nick and new_nick and target.startswith("channel:"):
                    channel_id = target.replace("channel:", "")
                    _remove_nick(channel_id, old_nick)
                    _add_nick(channel_id, new_nick)
                    weechat.prnt(buf,
                        f"--\t{old_nick} is now known as {new_nick}")
            except (json.JSONDecodeError, KeyError):
                pass

        buffer_label = target_to_buffer_label(target, my_nick)
        weechat.hook_signal_send(SIGNAL_MESSAGE_RECEIVED,
            weechat.WEECHAT_HOOK_SIGNAL_STRING,
            json.dumps({"buffer": buffer_label, "nick": nick,
                        "body": body, "type": msg_type}))

    for _ in range(100):
        try:
            ev = presence_queue.popleft()
        except IndexError:
            break
        channel_id = ev["channel_id"]
        nick = ev["nick"]
        if ev["online"]:
            _add_nick(channel_id, nick)
        else:
            _remove_nick(channel_id, nick)
            buf = buffers.get(f"channel:{channel_id}")
            if buf:
                weechat.prnt(buf, f"<--\t{nick} went offline")
        weechat.hook_signal_send(SIGNAL_PRESENCE_CHANGED,
            weechat.WEECHAT_HOOK_SIGNAL_STRING,
            json.dumps(ev))

    return weechat.WEECHAT_RC_OK


# ============================================================
# Nicklist helpers (unchanged)
# ============================================================

def _add_nick(channel_id, nick):
    buf = buffers.get(f"channel:{channel_id}")
    if buf and not weechat.nicklist_search_nick(buf, "", nick):
        weechat.nicklist_add_nick(buf, "", nick, "cyan", "", "", 1)

def _remove_nick(channel_id, nick):
    buf = buffers.get(f"channel:{channel_id}")
    if buf:
        ptr = weechat.nicklist_search_nick(buf, "", nick)
        if ptr:
            weechat.nicklist_remove_nick(buf, ptr)


# ============================================================
# /zenoh command
# ============================================================

def _buffer_target(buffer):
    """Get target string from current buffer localvars."""
    buf_type = weechat.buffer_get_string(buffer, "localvar_type")
    target = weechat.buffer_get_string(buffer, "localvar_target")
    if not target:
        return None
    if buf_type == "channel":
        return f"#{target}"
    elif buf_type == "private":
        return f"@{target}"
    return None


zenoh_registry = CommandRegistry(prefix="zenoh")


@zenoh_registry.command(
    name="join", args="<target>",
    description="Join channel (#name) or open private (@nick)",
    params=[CommandParam("target", required=True, help="#channel or @nick")],
)
def cmd_zenoh_join(buffer, args: ParsedArgs) -> CommandResult:
    target = args.get("target")
    join(target)
    return CommandResult.ok(f"Joining {target}")


@zenoh_registry.command(
    name="leave", args="[target]",
    description="Leave channel or close private",
    params=[CommandParam("target", required=False, help="#channel or @nick (default: current buffer)")],
)
def cmd_zenoh_leave(buffer, args: ParsedArgs) -> CommandResult:
    target = args.get("target")
    if not target:
        target = _buffer_target(buffer)
        if not target:
            return CommandResult.error("No target specified and current buffer is not a channel/private")
    leave(target)
    return CommandResult.ok(f"Left {target}")


@zenoh_registry.command(
    name="nick", args="<newname>",
    description="Change nickname",
    params=[CommandParam("newname", required=True, help="New nickname")],
)
def cmd_zenoh_nick(buffer, args: ParsedArgs) -> CommandResult:
    global my_nick
    new_nick = args.get("newname")
    old_nick = my_nick
    my_nick = new_nick
    weechat.config_set_plugin("nick", my_nick)
    _sidecar_send({"cmd": "set_nick", "nick": my_nick})
    msg = f"Nick changed: {old_nick} → {my_nick}"
    if privates:
        msg += (f"\nWarning: {len(privates)} open private(s) still "
                f"use pair keys with old nick '{old_nick}'. "
                f"Close and re-open them to update.")
    return CommandResult.ok(msg)


@zenoh_registry.command(
    name="list", args="",
    description="List joined channels and privates",
    params=[],
)
def cmd_zenoh_list(buffer, args: ParsedArgs) -> CommandResult:
    lines = []
    if channels:
        lines.append("Channels:")
        for ch in sorted(channels):
            lines.append(f"  #{ch}")
    if privates:
        lines.append("Privates:")
        for pr in sorted(privates):
            lines.append(f"  {pr}")
    if not lines:
        return CommandResult.ok("Not in any channels or privates")
    return CommandResult.ok("\n".join(lines))


@zenoh_registry.command(
    name="send", args="<target> <msg>",
    description="Send message programmatically",
    params=[
        CommandParam("target", required=True, help="#channel or @nick"),
        CommandParam("msg", required=True, help="Message text"),
    ],
)
def cmd_zenoh_send(buffer, args: ParsedArgs) -> CommandResult:
    target = args.get("target")
    # msg is everything after target in the raw string
    raw_tokens = args.raw.split(None, 2)  # ["send", "target", "rest..."]
    msg = raw_tokens[2] if len(raw_tokens) > 2 else args.get("msg", "")
    send_message(target, msg)
    return CommandResult.ok(f"Sent to {target}")


@zenoh_registry.command(
    name="status", args="",
    description="Show connection status",
    params=[],
)
def cmd_zenoh_status(buffer, args: ParsedArgs) -> CommandResult:
    global pending_status_buffer
    pending_status_buffer = buffer
    _sidecar_send({"cmd": "status"})
    return CommandResult.ok("Requesting status...")


@zenoh_registry.command(
    name="reconnect", args="",
    description="Restart sidecar and rejoin",
    params=[],
)
def cmd_zenoh_reconnect(buffer, args: ParsedArgs) -> CommandResult:
    _stop_sidecar()
    _start_sidecar()
    connect = weechat.config_get_plugin("connect")
    cmd_init = {"cmd": "init", "nick": my_nick}
    if connect:
        cmd_init["connect"] = connect
    _sidecar_send(cmd_init)
    # Build rejoin targets from local state
    saved_channels = set(channels)
    saved_privates = set(privates)
    channels.clear()
    privates.clear()
    rejoin_targets = [f"#{cid}" for cid in saved_channels]
    for pair in saved_privates:
        other_nick = extract_other_nick(pair, my_nick)
        if other_nick != pair:
            rejoin_targets.append(f"@{other_nick}")
    global pending_autojoin
    pending_autojoin = ",".join(rejoin_targets)
    return CommandResult.ok("Reconnecting...")


def zenoh_cmd_cb(data, buffer, args):
    """WeeChat hook callback — delegates to registry."""
    result = zenoh_registry.dispatch(buffer, args)
    prefix = "[zenoh]"
    if result.success:
        weechat.prnt(buffer, f"{prefix} {result.message}")
    else:
        weechat.prnt(buffer, f"{prefix} Error: {result.message}")
    return weechat.WEECHAT_RC_OK


# ============================================================
# Plugin registration
# ============================================================

if weechat.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION,
                    SCRIPT_LICENSE, SCRIPT_DESC, "zc_deinit", ""):
    for key, val in {
        "nick": "",
        "autojoin": "#general",
        "connect": "",
    }.items():
        if not weechat.config_is_set_plugin(key):
            weechat.config_set_plugin(key, val)

    weechat.hook_command("zenoh",
        "Zenoh P2P chat",
        zenoh_registry.weechat_help_args(),
        "",
        zenoh_registry.weechat_completion(),
        "zenoh_cmd_cb", "")

    zc_init()
