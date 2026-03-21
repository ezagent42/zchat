"""Tests for Zenoh background thread -> asyncio.Queue bridge."""
import asyncio
import threading
import pytest
from unittest.mock import AsyncMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "weechat-channel-server"))
from server import inject_message

class TestThreadToAsyncBridge:
    @pytest.mark.asyncio
    async def test_thread_to_queue_bridge(self):
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        def zenoh_callback():
            loop.call_soon_threadsafe(queue.put_nowait, ({"body": "hello"}, "alice"))
        thread = threading.Thread(target=zenoh_callback)
        thread.start()
        thread.join()
        msg, ctx = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert msg["body"] == "hello"
        assert ctx == "alice"

    @pytest.mark.asyncio
    async def test_multiple_concurrent_posts(self):
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        def post(i):
            loop.call_soon_threadsafe(queue.put_nowait, ({"body": f"msg-{i}"}, f"ctx-{i}"))
        threads = [threading.Thread(target=post, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        received = []
        for _ in range(10):
            item = await asyncio.wait_for(queue.get(), timeout=1.0)
            received.append(item)
        assert len(received) == 10

    @pytest.mark.asyncio
    async def test_write_stream_receives_notification(self):
        mock_stream = AsyncMock()
        msg = {"id": "ws-1", "nick": "alice", "body": "test", "ts": 1711036800.0}
        await inject_message(mock_stream, msg, "#general")
        session_msg = mock_stream.send.call_args[0][0]
        assert session_msg.message.root.method == "notifications/claude/channel"
