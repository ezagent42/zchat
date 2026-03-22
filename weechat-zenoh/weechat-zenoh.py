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
from helpers import target_to_buffer_label, parse_input

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
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
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

    sidecar_proc = subprocess.Popen(
        [sys.executable, "-u", _sidecar_path()],
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
    pair = "_".join(sorted([my_nick, target_nick]))
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
    pair = "_".join(sorted([my_nick, target_nick]))
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
        pair = "_".join(sorted([my_nick, nick]))
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
    weechat.hook_signal_send("zenoh_message_sent",
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
        weechat.hook_signal_send("zenoh_message_received",
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
        weechat.hook_signal_send("zenoh_presence_changed",
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

def zenoh_cmd_cb(data, buffer, args):
    argv = args.split()
    cmd = argv[0] if argv else "help"

    if cmd == "join" and len(argv) >= 2:
        join(argv[1])

    elif cmd == "leave":
        if len(argv) >= 2:
            leave(argv[1])
        else:
            target = weechat.buffer_get_string(buffer, "localvar_target")
            buf_type = weechat.buffer_get_string(buffer, "localvar_type")
            if target:
                leave(f"{'#' if buf_type == 'channel' else '@'}{target}")

    elif cmd == "nick" and len(argv) >= 2:
        global my_nick
        old = my_nick
        my_nick = argv[1]
        weechat.config_set_plugin("nick", my_nick)
        weechat.prnt("", f"[zenoh] Nick changed: {old} → {my_nick}")
        _sidecar_send({"cmd": "set_nick", "nick": my_nick})
        if privates:
            weechat.prnt("",
                f"[zenoh] Warning: {len(privates)} open private(s) still "
                f"use pair keys with old nick '{old}'. "
                f"Close and re-open them to update.")

    elif cmd == "list":
        weechat.prnt(buffer, "[zenoh] Channels:")
        for r in sorted(channels):
            weechat.prnt(buffer, f"  #{r}")
        weechat.prnt(buffer, "[zenoh] Privates:")
        for d in sorted(privates):
            weechat.prnt(buffer, f"  {d}")

    elif cmd == "send" and len(argv) >= 3:
        target = argv[1]
        body = " ".join(argv[2:])
        send_message(target, body)

    elif cmd == "status":
        global pending_status_buffer
        pending_status_buffer = buffer
        _sidecar_send({"cmd": "status"})

    elif cmd == "reconnect":
        weechat.prnt("", "[zenoh] Reconnecting...")
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
            nicks = pair.split("_")
            other = [n for n in nicks if n != my_nick]
            if other:
                rejoin_targets.append(f"@{other[0]}")
        # Queue for autojoin on ready event
        global pending_autojoin
        pending_autojoin = ",".join(rejoin_targets)

    else:
        weechat.prnt(buffer,
            "[zenoh] Usage: /zenoh <join|leave|nick|list|send|status|reconnect>")

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
        "join <#channel|@nick> || leave [target] || nick <n> || "
        "list || send <target> <msg> || status || reconnect",
        "    join: Join channel or open private\n"
        "   leave: Leave channel or close private\n"
        "    nick: Change nickname\n"
        "    list: List joined channels and privates\n"
        "    send: Send message programmatically\n"
        "  status: Show connection status\n"
        "reconnect: Restart sidecar and rejoin",
        "join || leave || nick || list || send || status || reconnect",
        "zenoh_cmd_cb", "")

    zc_init()
