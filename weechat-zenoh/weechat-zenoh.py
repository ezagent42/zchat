#!/usr/bin/env python3
# weechat-zenoh.py

"""
WeeChat Zenoh P2P 聊天插件
提供 Zenoh 消息总线上的 channel/private 基础设施
"""

import weechat
import json
import time
import uuid
import os
from collections import deque
from helpers import target_to_buffer_label, parse_input

SCRIPT_NAME = "weechat-zenoh"
SCRIPT_AUTHOR = "Allen <ezagent42>"
SCRIPT_VERSION = "0.1.0"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "P2P chat over Zenoh for WeeChat"

# --- 全局状态 ---
zenoh_session = None
msg_queue = deque()
presence_queue = deque()
subscribers = {}          # key → zenoh.Subscriber
publishers = {}           # key → zenoh.Publisher
liveliness_tokens = {}    # key → zenoh.LivelinessToken
buffers = {}              # buffer_key → weechat buffer ptr
my_nick = ""
channels = set()          # 已加入的 channel
privates = set()          # 已开启的 private


# ============================================================
# 初始化 / 反初始化
# ============================================================

def zc_init():
    global zenoh_session, my_nick
    import zenoh

    my_nick = weechat.config_get_plugin("nick")
    if not my_nick:
        my_nick = os.environ.get("USER", "user_%s" % uuid.uuid4().hex[:6])
        weechat.config_set_plugin("nick", my_nick)

    # Zenoh client mode, connect to local zenohd
    from helpers import build_zenoh_config
    connect = weechat.config_get_plugin("connect")
    config = build_zenoh_config(connect if connect else None)

    try:
        zenoh_session = zenoh.open(config)
    except Exception as e:
        weechat.prnt("", f"[zenoh] Failed to open session: {e}")
        return

    # 全局在线状态
    liveliness_tokens["_global"] = \
        zenoh_session.liveliness().declare_token(f"wc/presence/{my_nick}")

    # 队列轮询
    weechat.hook_timer(50, 0, 0, "poll_queues_cb", "")

    # 自动加入
    autojoin = weechat.config_get_plugin("autojoin")
    if autojoin:
        for target in autojoin.split(","):
            target = target.strip()
            if target:
                join(target)

    weechat.prnt("", f"[zenoh] Session opened, nick={my_nick}")


def zc_deinit():
    for token in liveliness_tokens.values():
        token.undeclare()
    for sub in subscribers.values():
        sub.undeclare()
    for pub in publishers.values():
        pub.undeclare()
    if zenoh_session:
        zenoh_session.close()
    return weechat.WEECHAT_RC_OK


# ============================================================
# Channel / Private 管理
# ============================================================

def join(target):
    """加入 #channel 或开启 @nick private"""
    if target.startswith("#"):
        join_channel(target.lstrip("#"))
    elif target.startswith("@"):
        join_private(target.lstrip("@"))
    else:
        join_channel(target)


def join_channel(channel_id):
    import zenoh

    if channel_id in channels:
        weechat.prnt("", f"[zenoh] Already in #{channel_id}")
        return

    # Buffer
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

    # Zenoh pub/sub
    msg_key = f"wc/channels/{channel_id}/messages"
    publishers[f"channel:{channel_id}"] = zenoh_session.declare_publisher(msg_key)
    subscribers[f"channel:{channel_id}"] = zenoh_session.declare_subscriber(
        msg_key,
        lambda sample, _cid=channel_id: _on_channel_msg(sample, _cid),

    )

    # Liveliness
    token_key = f"wc/channels/{channel_id}/presence/{my_nick}"
    liveliness_tokens[f"channel:{channel_id}"] = \
        zenoh_session.liveliness().declare_token(token_key)

    # 监听该 channel 的 presence 变化
    zenoh_session.liveliness().declare_subscriber(
        f"wc/channels/{channel_id}/presence/*",
        lambda sample, _cid=channel_id: _on_channel_presence(sample, _cid),

    )

    # 查询当前在线的成员
    try:
        replies = zenoh_session.liveliness().get(
            f"wc/channels/{channel_id}/presence/*")
        for reply in replies:
            nick = str(reply.ok.key_expr).rsplit("/", 1)[-1]
            _add_nick(channel_id, nick)
    except Exception:
        pass

    channels.add(channel_id)

    # 广播 join
    _publish_event(f"channel:{channel_id}", "join", "")
    weechat.prnt(buf, f"-->\t{my_nick} joined #{channel_id}")


def join_private(target_nick):
    # Private key: 两个 nick 字母序排列
    pair = "_".join(sorted([my_nick, target_nick]))
    private_key = f"private:{pair}"

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
    buffers[private_key] = buf

    msg_key = f"wc/private/{pair}/messages"
    publishers[private_key] = zenoh_session.declare_publisher(msg_key)
    subscribers[private_key] = zenoh_session.declare_subscriber(
        msg_key,
        lambda sample, _pk=private_key: _on_private_msg(sample, _pk),

    )

    privates.add(pair)


def leave(target):
    """离开 channel 或关闭 private"""
    if target.startswith("#"):
        leave_channel(target.lstrip("#"))
    elif target.startswith("@"):
        leave_private(target.lstrip("@"))


def leave_channel(channel_id):
    key = f"channel:{channel_id}"
    if channel_id not in channels:
        return
    _publish_event(key, "leave", "")
    _cleanup_key(key)
    channels.discard(channel_id)


def leave_private(target_nick):
    pair = "_".join(sorted([my_nick, target_nick]))
    key = f"private:{pair}"
    _cleanup_key(key)
    privates.discard(pair)


def _cleanup_key(key):
    if key in subscribers:
        subscribers.pop(key).undeclare()
    if key in publishers:
        publishers.pop(key).undeclare()
    if key in liveliness_tokens:
        liveliness_tokens.pop(key).undeclare()
    if key in buffers:
        weechat.buffer_close(buffers.pop(key))


# ============================================================
# 消息发送
# ============================================================

def _publish_event(pub_key, msg_type, body):
    pub = publishers.get(pub_key)
    if not pub:
        return
    event = json.dumps({
        "id": uuid.uuid4().hex,
        "nick": my_nick,
        "type": msg_type,
        "body": body,
        "ts": time.time()
    })
    pub.put(event)


def send_message(target, body):
    """公共 API: 发送消息到指定 target"""
    if target.startswith("#"):
        channel_id = target.lstrip("#")
        key = f"channel:{channel_id}"
        _publish_event(key, "msg", body)
        buf = buffers.get(key)
        if buf:
            weechat.prnt(buf, f"{my_nick}\t{body}")
    elif target.startswith("@"):
        nick = target.lstrip("@")
        pair = "_".join(sorted([my_nick, nick]))
        key = f"private:{pair}"
        if pair not in privates:
            join_private(nick)
        _publish_event(key, "msg", body)
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

    _publish_event(pub_key, msg_type, body)
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
# 消息接收 (Zenoh callback → deque → hook_timer)
# ============================================================

def _on_channel_msg(sample, channel_id):
    try:
        msg = json.loads(sample.payload.to_string())
        if msg.get("nick") != my_nick:
            msg["_target"] = f"channel:{channel_id}"
            msg_queue.append(msg)
    except Exception:
        pass


def _on_private_msg(sample, private_key):
    try:
        msg = json.loads(sample.payload.to_string())
        if msg.get("nick") != my_nick:
            msg["_target"] = private_key
            msg_queue.append(msg)
    except Exception:
        pass


def _on_channel_presence(sample, channel_id):
    nick = str(sample.key_expr).rsplit("/", 1)[-1]
    kind = str(sample.kind)
    presence_queue.append({
        "channel_id": channel_id,
        "nick": nick,
        "online": "PUT" in kind
    })


def poll_queues_cb(data, remaining_calls):
    # 消息
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

        # Signal 供其他脚本消费
        buffer_label = target_to_buffer_label(target, my_nick)
        weechat.hook_signal_send("zenoh_message_received",
            weechat.WEECHAT_HOOK_SIGNAL_STRING,
            json.dumps({"buffer": buffer_label, "nick": nick,
                        "body": body, "type": msg_type}))

    # Presence
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
# Nicklist helpers
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
# /zenoh 命令
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

        # Broadcast nick change to all joined channels
        nick_body = json.dumps({"old": old, "new": my_nick})
        for cid in channels:
            _publish_event(f"channel:{cid}", "nick", nick_body)

        # Update global liveliness token
        if "_global" in liveliness_tokens:
            liveliness_tokens["_global"].undeclare()
        liveliness_tokens["_global"] = \
            zenoh_session.liveliness().declare_token(f"wc/presence/{my_nick}")

        # Update per-channel liveliness tokens
        for cid in channels:
            tok_key = f"channel:{cid}"
            if tok_key in liveliness_tokens:
                liveliness_tokens[tok_key].undeclare()
            liveliness_tokens[tok_key] = \
                zenoh_session.liveliness().declare_token(
                    f"wc/channels/{cid}/presence/{my_nick}")

        # Warn about open privates (pair keys contain old nick)
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
        try:
            info = zenoh_session.info
            zid = str(info.zid())
            routers = list(info.routers_zid())
            peers = list(info.peers_zid())
            weechat.prnt(buffer,
                f"[zenoh] zid={zid[:8]}... nick={my_nick}\n"
                f"  mode=client  channels={len(channels)} privates={len(privates)}\n"
                f"  routers={len(routers)} peers={len(peers)}\n"
                f"  session={'open' if zenoh_session else 'closed'}")
        except Exception as e:
            weechat.prnt(buffer,
                f"[zenoh] nick={my_nick} channels={len(channels)} "
                f"privates={len(privates)} session={'open' if zenoh_session else 'closed'}\n"
                f"  (info unavailable: {e})")

    else:
        weechat.prnt(buffer,
            "[zenoh] Usage: /zenoh <join|leave|nick|list|send|status>")

    return weechat.WEECHAT_RC_OK


# ============================================================
# 插件注册
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
        "list || send <target> <msg> || status",
        "  join: Join channel or open private\n"
        " leave: Leave channel or close private\n"
        "  nick: Change nickname\n"
        "  list: List joined channels and privates\n"
        "  send: Send message programmatically\n"
        "status: Show connection status",
        "join || leave || nick || list || send || status",
        "zenoh_cmd_cb", "")

    zc_init()
