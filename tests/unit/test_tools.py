"""Tests for reply tool logic in server.py."""
import json
import os
import pytest
from unittest.mock import MagicMock

# Patch AGENT_NAME before importing tools (scoped to creator per issue #2)
os.environ["AGENT_NAME"] = "alice:agent0"

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "weechat-channel-server"))
from server import _handle_reply

class TestReplyTool:
    @pytest.fixture
    def mock_zenoh(self):
        session = MagicMock()
        session.put = MagicMock()
        return session

    @pytest.mark.asyncio
    async def test_reply_to_private(self, mock_zenoh):
        result = await _handle_reply(mock_zenoh, {"chat_id": "alice", "text": "hello"})
        assert "Sent" in result[0].text
        mock_zenoh.put.assert_called_once()
        key = mock_zenoh.put.call_args[0][0]
        assert key == "wc/private/alice_alice:agent0/messages"
        msg = json.loads(mock_zenoh.put.call_args[0][1])
        assert msg["nick"] == "alice:agent0"
        assert msg["body"] == "hello"

    @pytest.mark.asyncio
    async def test_reply_to_channel(self, mock_zenoh):
        result = await _handle_reply(mock_zenoh, {"chat_id": "#general", "text": "hi"})
        key = mock_zenoh.put.call_args[0][0]
        assert key == "wc/channels/general/messages"

    @pytest.mark.asyncio
    async def test_reply_message_format(self, mock_zenoh):
        await _handle_reply(mock_zenoh, {"chat_id": "bob", "text": "test"})
        msg = json.loads(mock_zenoh.put.call_args[0][1])
        for field in ("id", "nick", "type", "body", "ts"):
            assert field in msg
        assert isinstance(msg["ts"], float)
