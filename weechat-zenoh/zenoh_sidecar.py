#!/usr/bin/env python3
"""
Zenoh sidecar process for weechat-zenoh plugin.
Runs as standalone process to avoid PyO3 subinterpreter issues.
Communicates via stdin (JSON commands) / stdout (JSON events).
"""

import json
import sys
import uuid
import time
import threading
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))
from wc_protocol.topics import (
    make_private_pair, channel_topic, private_topic,
    presence_topic, channel_presence_topic, channel_presence_glob,
)
from wc_protocol.config import build_zenoh_config_dict

# Support --mock flag for testing
_use_mock = "--mock" in sys.argv

if _use_mock:
    from conftest import MockZenohSession
else:
    import zenoh


# --- Global state ---
session = None
my_nick = ""
publishers = {}          # key → zenoh.Publisher
subscribers = {}         # key → zenoh.Subscriber
liveliness_subs = {}     # key → zenoh liveliness Subscriber
liveliness_tokens = {}   # key → zenoh.LivelinessToken
channels = set()
privates = set()
_stdout_lock = threading.Lock()


def emit(event: dict):
    """Write JSON event to stdout. Thread-safe via lock.
    Called from both main thread and Zenoh callback threads."""
    with _stdout_lock:
        sys.stdout.write(json.dumps(event) + "\n")
        sys.stdout.flush()


def build_config(connect: str | None = None):
    """Build Zenoh client config from wc_protocol dict."""
    cfg = build_zenoh_config_dict(connect)
    config = zenoh.Config()
    config.insert_json5("mode", f'"{cfg["mode"]}"')
    config.insert_json5("connect/endpoints", json.dumps(cfg["connect/endpoints"]))
    return config


def handle_init(params: dict):
    global session, my_nick
    my_nick = params["nick"]
    connect = params.get("connect")

    if _use_mock:
        session = MockZenohSession()
        zid = "mock-zid-" + uuid.uuid4().hex[:8]
    else:
        config = build_config(connect)
        session = zenoh.open(config)
        zid = str(session.info.zid())

    # Global liveliness
    liveliness_tokens["_global"] = \
        session.liveliness().declare_token(presence_topic(my_nick))

    emit({"event": "ready", "zid": zid})


def _on_channel_msg(sample, channel_id):
    """Zenoh callback — runs in Zenoh thread."""
    try:
        msg = json.loads(sample.payload.to_string())
        if msg.get("nick") != my_nick:
            msg["_target"] = f"channel:{channel_id}"
            emit({"event": "message", "target": f"channel:{channel_id}",
                  "msg": msg})
    except Exception:
        pass


def _on_channel_presence(sample, channel_id):
    """Zenoh callback — runs in Zenoh thread."""
    nick = str(sample.key_expr).rsplit("/", 1)[-1]
    kind = str(sample.kind)
    emit({"event": "presence", "channel_id": channel_id,
          "nick": nick, "online": "PUT" in kind})


def handle_join_channel(params: dict):
    channel_id = params["channel_id"]
    if channel_id in channels:
        return

    key = f"channel:{channel_id}"
    msg_key = channel_topic(channel_id)

    publishers[key] = session.declare_publisher(msg_key)
    subscribers[key] = session.declare_subscriber(
        msg_key,
        lambda sample, _cid=channel_id: _on_channel_msg(sample, _cid))

    # Liveliness
    token_key = channel_presence_topic(channel_id, my_nick)
    liveliness_tokens[key] = \
        session.liveliness().declare_token(token_key)

    liveliness_subs[key] = session.liveliness().declare_subscriber(
        channel_presence_glob(channel_id),
        lambda sample, _cid=channel_id: _on_channel_presence(sample, _cid))

    # Query current members
    try:
        replies = session.liveliness().get(
            channel_presence_glob(channel_id))
        for reply in replies:
            nick = str(reply.ok.key_expr).rsplit("/", 1)[-1]
            emit({"event": "presence", "channel_id": channel_id,
                  "nick": nick, "online": True})
    except Exception:
        pass

    channels.add(channel_id)

    # Publish join event
    _publish_event(key, "join", "")


def handle_leave_channel(params: dict):
    channel_id = params["channel_id"]
    if channel_id not in channels:
        return
    key = f"channel:{channel_id}"
    _publish_event(key, "leave", "")
    _cleanup_key(key)
    channels.discard(channel_id)


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


def _cleanup_key(key):
    if key in subscribers:
        subscribers.pop(key).undeclare()
    if key in liveliness_subs:
        liveliness_subs.pop(key).undeclare()
    if key in publishers:
        publishers.pop(key).undeclare()
    if key in liveliness_tokens:
        liveliness_tokens.pop(key).undeclare()


def _on_private_msg(sample, private_key):
    """Zenoh callback — runs in Zenoh thread."""
    try:
        msg = json.loads(sample.payload.to_string())
        if msg.get("nick") != my_nick:
            msg["_target"] = private_key
            emit({"event": "message", "target": private_key, "msg": msg})
    except Exception:
        pass


def handle_join_private(params: dict):
    target_nick = params["target_nick"]
    pair = make_private_pair(my_nick, target_nick)
    key = f"private:{pair}"

    if pair in privates:
        return

    msg_key = private_topic(pair)
    publishers[key] = session.declare_publisher(msg_key)
    subscribers[key] = session.declare_subscriber(
        msg_key,
        lambda sample, _pk=key: _on_private_msg(sample, _pk))

    privates.add(pair)


def handle_leave_private(params: dict):
    target_nick = params["target_nick"]
    pair = make_private_pair(my_nick, target_nick)
    key = f"private:{pair}"
    _cleanup_key(key)
    privates.discard(pair)


def handle_send(params: dict):
    _publish_event(params["pub_key"], params["type"], params["body"])


def handle_set_nick(params: dict):
    global my_nick
    old = my_nick
    my_nick = params["nick"]

    # Broadcast nick change to all channels
    nick_body = json.dumps({"old": old, "new": my_nick})
    for cid in channels:
        _publish_event(f"channel:{cid}", "nick", nick_body)

    # Update global liveliness
    if "_global" in liveliness_tokens:
        liveliness_tokens["_global"].undeclare()
    liveliness_tokens["_global"] = \
        session.liveliness().declare_token(presence_topic(my_nick))

    # Update per-channel liveliness
    for cid in channels:
        tok_key = f"channel:{cid}"
        if tok_key in liveliness_tokens:
            liveliness_tokens[tok_key].undeclare()
        liveliness_tokens[tok_key] = \
            session.liveliness().declare_token(
                channel_presence_topic(cid, my_nick))


def handle_status(params: dict):
    if _use_mock:
        zid = "mock-zid"
        routers = []
        peers = []
    else:
        info = session.info
        zid = str(info.zid())
        routers = [str(z) for z in info.routers_zid()]
        peers = [str(z) for z in info.peers_zid()]
    emit({"event": "status_response",
          "zid": zid, "routers": routers, "peers": peers,
          "nick": my_nick,
          "channels": len(channels), "privates": len(privates)})


def handle_command(cmd: dict):
    """Dispatch a single command."""
    name = cmd.get("cmd")
    if name == "init":
        handle_init(cmd)
    elif name == "join_channel":
        handle_join_channel(cmd)
    elif name == "leave_channel":
        handle_leave_channel(cmd)
    elif name == "status":
        handle_status(cmd)
    elif name == "join_private":
        handle_join_private(cmd)
    elif name == "leave_private":
        handle_leave_private(cmd)
    elif name == "send":
        handle_send(cmd)
    elif name == "set_nick":
        handle_set_nick(cmd)
    else:
        emit({"event": "error", "detail": f"Unknown command: {name}"})


def main():
    """Main loop: read stdin line by line, dispatch commands."""
    # Use readline() to avoid buffered iteration blocking
    for line in iter(sys.stdin.readline, ""):
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError as e:
            emit({"event": "error", "detail": f"Invalid JSON: {e}"})
            continue
        handle_command(cmd)

    # stdin EOF — clean up
    cleanup()


def cleanup():
    global session
    for token in liveliness_tokens.values():
        token.undeclare()
    for sub in liveliness_subs.values():
        sub.undeclare()
    for sub in subscribers.values():
        sub.undeclare()
    for pub in publishers.values():
        pub.undeclare()
    if session and not _use_mock:
        session.close()
    session = None


if __name__ == "__main__":
    main()
