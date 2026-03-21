"""Tests for weechat-channel-server/server.py notification injection."""
import pytest
from unittest.mock import AsyncMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "weechat-channel-server"))

class TestInjectMessage:
    @pytest.mark.asyncio
    async def test_notification_format(self):
        from server import inject_message
        mock_stream = AsyncMock()
        msg = {"id": "test-001", "nick": "alice", "body": "hello", "ts": 1711036800.0}
        await inject_message(mock_stream, msg, "alice")
        mock_stream.send.assert_called_once()
        session_msg = mock_stream.send.call_args[0][0]
        notification = session_msg.message.root
        assert notification.method == "notifications/claude/channel"
        assert notification.params["content"] == "hello"
        assert notification.params["meta"]["user"] == "alice"
        assert notification.params["meta"]["chat_id"] == "alice"

    @pytest.mark.asyncio
    async def test_notification_channel_chat_id(self):
        from server import inject_message
        mock_stream = AsyncMock()
        msg = {"id": "test-002", "nick": "bob", "body": "hi", "ts": 1711036800.0}
        await inject_message(mock_stream, msg, "#general")
        session_msg = mock_stream.send.call_args[0][0]
        assert session_msg.message.root.params["meta"]["chat_id"] == "#general"

    @pytest.mark.asyncio
    async def test_notification_meta_fields(self):
        from server import inject_message
        mock_stream = AsyncMock()
        msg = {"id": "m-1", "nick": "alice", "body": "test", "ts": 1711036800.0}
        await inject_message(mock_stream, msg, "alice")
        meta = mock_stream.send.call_args[0][0].message.root.params["meta"]
        for field in ("chat_id", "message_id", "user", "ts"):
            assert field in meta
