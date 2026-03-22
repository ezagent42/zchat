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
from collections import deque

# Support --mock flag for testing
_use_mock = "--mock" in sys.argv

if _use_mock:
    from conftest import MockZenohSession
else:
    import zenoh

ZENOH_DEFAULT_ENDPOINT = "tcp/127.0.0.1:7447"

# --- Global state ---
session = None
my_nick = ""
publishers = {}          # key → zenoh.Publisher
subscribers = {}         # key → zenoh.Subscriber
liveliness_subs = {}     # key → zenoh liveliness Subscriber
liveliness_tokens = {}   # key → zenoh.LivelinessToken
channels = set()
privates = set()
event_queue = deque()    # events to write to stdout


def emit(event: dict):
    """Write JSON event to stdout (thread-safe via deque)."""
    event_queue.append(event)


def flush_events():
    """Write all queued events to stdout. Call from main thread."""
    while True:
        try:
            event = event_queue.popleft()
        except IndexError:
            break
        sys.stdout.write(json.dumps(event) + "\n")
        sys.stdout.flush()


def build_config(connect: str | None = None):
    """Build Zenoh client config."""
    config = zenoh.Config()
    config.insert_json5("mode", '"client"')
    endpoints = connect.split(",") if connect else [ZENOH_DEFAULT_ENDPOINT]
    config.insert_json5("connect/endpoints", json.dumps(endpoints))
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
        session.liveliness().declare_token(f"wc/presence/{my_nick}")

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
    msg_key = f"wc/channels/{channel_id}/messages"

    publishers[key] = session.declare_publisher(msg_key)
    subscribers[key] = session.declare_subscriber(
        msg_key,
        lambda sample, _cid=channel_id: _on_channel_msg(sample, _cid))

    # Liveliness
    token_key = f"wc/channels/{channel_id}/presence/{my_nick}"
    liveliness_tokens[key] = \
        session.liveliness().declare_token(token_key)

    liveliness_subs[key] = session.liveliness().declare_subscriber(
        f"wc/channels/{channel_id}/presence/*",
        lambda sample, _cid=channel_id: _on_channel_presence(sample, _cid))

    # Query current members
    try:
        replies = session.liveliness().get(
            f"wc/channels/{channel_id}/presence/*")
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
            flush_events()
            continue
        handle_command(cmd)
        flush_events()

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
