#!/usr/bin/env python3
"""
weechat-channel-server: Claude Code Channel MCP Server
Bridges Zenoh P2P messaging <-> Claude Code via MCP stdio protocol.
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

import anyio
import zenoh
import mcp.server.stdio
from mcp.server.lowlevel import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage, JSONRPCNotification, Tool, TextContent

from message import (
    MessageDedup, detect_mention, clean_mention,
    make_private_pair, chunk_message,
)

AGENT_NAME = os.environ.get("AGENT_NAME", "agent0")

# ============================================================
# MCP Notification Injection
# ============================================================

async def inject_message(write_stream, msg: dict, context: str):
    """Send a channel notification to Claude Code via the MCP write stream."""
    ts = msg.get("ts", 0)
    iso_ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else datetime.now(tz=timezone.utc).isoformat()
    notification = JSONRPCNotification(
        jsonrpc="2.0",
        method="notifications/claude/channel",
        params={
            "content": msg.get("body", ""),
            "meta": {
                "chat_id": context,
                "message_id": msg.get("id", ""),
                "user": msg.get("nick", "unknown"),
                "ts": iso_ts,
            },
        },
    )
    await write_stream.send(SessionMessage(message=JSONRPCMessage(notification)))


async def poll_zenoh_queue(queue: asyncio.Queue, write_stream):
    """Consume Zenoh messages from the queue and inject into Claude Code."""
    while True:
        msg, context = await queue.get()
        try:
            await inject_message(write_stream, msg, context)
        except Exception as e:
            print(f"[channel-server] inject error: {e}", file=sys.stderr)

# ============================================================
# Zenoh Setup
# ============================================================

def setup_zenoh(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """Initialize Zenoh session and subscribe to messages."""
    ZENOH_DEFAULT_ENDPOINT = "tcp/127.0.0.1:7447"
    zenoh_config = zenoh.Config()
    zenoh_config.insert_json5("mode", '"client"')
    connect = os.environ.get("ZENOH_CONNECT")
    if connect:
        zenoh_config.insert_json5("connect/endpoints", json.dumps(connect.split(",")))
    else:
        zenoh_config.insert_json5("connect/endpoints", f'["{ZENOH_DEFAULT_ENDPOINT}"]')
    zenoh_session = zenoh.open(zenoh_config)
    zenoh_session.liveliness().declare_token(f"wc/presence/{AGENT_NAME}")
    dedup = MessageDedup()
    joined_channels: dict[str, object] = {}

    def on_private(sample):
        try:
            key = str(sample.key_expr)
            parts = key.split("/")
            if len(parts) < 3:
                return
            pair = parts[2]
            if AGENT_NAME not in pair.split("_"):
                return
            msg = json.loads(sample.payload.to_string())
            if msg.get("nick") == AGENT_NAME:
                return
            msg_id = msg.get("id", "")
            if msg_id and dedup.is_duplicate(msg_id):
                return
            sender = msg.get("nick", "unknown")
            print(f"[channel-server] [private:{sender}] {sender}: {msg.get('body', '')}", file=sys.stderr)
            loop.call_soon_threadsafe(queue.put_nowait, (msg, sender))
        except Exception as e:
            print(f"[channel-server] private error: {e}", file=sys.stderr)

    def on_channel(sample):
        try:
            msg = json.loads(sample.payload.to_string())
            if msg.get("nick") == AGENT_NAME:
                return
            body = msg.get("body", "")
            if not detect_mention(body, AGENT_NAME):
                return
            msg_id = msg.get("id", "")
            if msg_id and dedup.is_duplicate(msg_id):
                return
            msg["body"] = clean_mention(body, AGENT_NAME)
            channel = str(sample.key_expr).split("/")[2]
            print(f"[channel-server] [#{channel}] {msg.get('nick', '?')}: {body}", file=sys.stderr)
            if channel not in joined_channels:
                token = zenoh_session.liveliness().declare_token(f"wc/channels/{channel}/presence/{AGENT_NAME}")
                joined_channels[channel] = token
            loop.call_soon_threadsafe(queue.put_nowait, (msg, f"#{channel}"))
        except Exception as e:
            print(f"[channel-server] channel error: {e}", file=sys.stderr)

    zenoh_session.declare_subscriber("wc/private/*/messages", on_private)
    zenoh_session.declare_subscriber("wc/channels/*/messages", on_channel)
    return zenoh_session, joined_channels

# ============================================================
# MCP Server + Tools
# ============================================================

def create_server():
    server = Server("weechat-channel")
    return server

def register_tools(server: Server, state: dict):
    """Register MCP tools eagerly. Zenoh session is resolved lazily from state
    dict on first tool call, so tools are available before Zenoh connects."""

    def _get_zenoh():
        session = state.get("zenoh_session")
        if session is None:
            raise RuntimeError("Zenoh session not initialized yet")
        return session

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return [
            Tool(
                name="reply",
                description="Reply to a WeeChat user or channel. chat_id is a username for private (e.g. 'alice') or #channel name (e.g. '#general').",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "string", "description": "Target: username for private or #channel"},
                        "text": {"type": "string", "description": "Message content"},
                    },
                    "required": ["chat_id", "text"],
                },
            ),
            Tool(
                name="join_channel",
                description="Join a WeeChat channel to receive @mentions.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "channel_name": {"type": "string", "description": "Channel name without # prefix"},
                    },
                    "required": ["channel_name"],
                },
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
        zenoh_session = _get_zenoh()
        if name == "reply":
            return await _handle_reply(zenoh_session, arguments)
        elif name == "join_channel":
            return await _handle_join_channel(zenoh_session, arguments)
        raise ValueError(f"Unknown tool: {name}")

async def _handle_reply(zenoh_session, arguments: dict) -> list[TextContent]:
    chat_id = arguments["chat_id"]
    text = arguments["text"]
    chunks = chunk_message(text)
    for chunk in chunks:
        msg = json.dumps({
            "id": os.urandom(8).hex(),
            "nick": AGENT_NAME,
            "type": "msg",
            "body": chunk,
            "ts": time.time(),
        })
        if chat_id.startswith("#"):
            channel = chat_id.lstrip("#")
            zenoh_session.put(f"wc/channels/{channel}/messages", msg)
        else:
            pair = make_private_pair(AGENT_NAME, chat_id)
            zenoh_session.put(f"wc/private/{pair}/messages", msg)
    return [TextContent(type="text", text=f"Sent to {chat_id}")]

async def _handle_join_channel(zenoh_session, arguments: dict) -> list[TextContent]:
    channel = arguments["channel_name"]
    zenoh_session.liveliness().declare_token(f"wc/channels/{channel}/presence/{AGENT_NAME}")
    return [TextContent(type="text", text=f"Joined #{channel}")]

# ============================================================
# Main
# ============================================================

async def main():
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    server = create_server()
    # Shared state dict — tools resolve zenoh_session lazily from here
    state: dict = {}
    register_tools(server, state)
    init_opts = InitializationOptions(
        server_name=f"weechat-channel-{AGENT_NAME}",
        server_version="0.1.0",
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={"claude/channel": {}},
        ),
    )
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await anyio.sleep(2)
        zenoh_session, joined_channels = setup_zenoh(queue, loop)
        state["zenoh_session"] = zenoh_session
        print(f"[channel-server] {AGENT_NAME} ready on Zenoh", file=sys.stderr)
        try:
            async with anyio.create_task_group() as tg:
                tg.start_soon(server.run, read_stream, write_stream, init_opts)
                tg.start_soon(poll_zenoh_queue, queue, write_stream)
        finally:
            zenoh_session.close()

if __name__ == "__main__":
    asyncio.run(main())
