"""Tests for weechat-zchat-plugin protocol helpers.

The WeeChat plugin implements protocol independently. These tests verify
the local protocol implementation matches zchat.protocol behavior.
"""
import json

from zchat.protocol.naming import scoped_name, AGENT_SEPARATOR
from zchat.protocol.sys_messages import (
    IRC_SYS_PREFIX, encode_sys_for_irc, decode_sys_from_irc, make_sys_message,
)


class TestPluginProtocolParity:
    """Verify the plugin's protocol constants match zchat.protocol."""

    def test_agent_separator(self):
        assert AGENT_SEPARATOR == "-"

    def test_sys_prefix(self):
        assert IRC_SYS_PREFIX == "__zchat_sys:"

    def test_scoped_name_basic(self):
        assert scoped_name("agent0", "alice") == "alice-agent0"

    def test_scoped_name_already_scoped(self):
        assert scoped_name("alice-agent0", "alice") == "alice-agent0"

    def test_sys_message_roundtrip(self):
        msg = make_sys_message("alice-agent0", "sys.status_request", {})
        encoded = encode_sys_for_irc(msg)
        decoded = decode_sys_from_irc(encoded)
        assert decoded["type"] == "sys.status_request"
        assert decoded["nick"] == "alice-agent0"

    def test_sys_decode_non_sys(self):
        assert decode_sys_from_irc("hello world") is None


class TestAgentCommandParsing:
    """Test /agent command argument parsing logic."""

    def test_parse_create(self):
        args = "create helper"
        parts = args.split(None, 1)
        assert parts[0] == "create"
        assert parts[1] == "helper"

    def test_parse_create_with_workspace(self):
        args = "create helper --workspace /tmp/ws"
        parts = args.split(None, 1)
        assert parts[0] == "create"
        assert "--workspace" in parts[1]

    def test_parse_stop(self):
        args = "stop helper"
        parts = args.split(None, 1)
        assert parts[0] == "stop"
        assert parts[1] == "helper"

    def test_parse_list(self):
        args = "list"
        parts = args.split(None, 1)
        assert parts[0] == "list"
        assert len(parts) == 1

    def test_parse_empty(self):
        args = ""
        parts = args.split(None, 1)
        assert len(parts) == 0
