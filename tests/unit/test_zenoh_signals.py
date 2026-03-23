"""Tests for weechat-zenoh signal format and input parsing."""
import json
from wc_protocol.topics import target_to_buffer_label, parse_input

class TestTargetToBufferLabel:
    def test_channel_format(self):
        assert target_to_buffer_label("channel:general", "alice") == "channel:#general"
    def test_private_format(self):
        assert target_to_buffer_label("private:alice_bob", "alice") == "private:@bob"
    def test_private_reverse_order(self):
        assert target_to_buffer_label("private:alice_bob", "bob") == "private:@alice"

class TestParseInput:
    def test_regular_message(self):
        assert parse_input("hello world") == ("msg", "hello world")
    def test_me_action(self):
        assert parse_input("/me waves") == ("action", "waves")
    def test_bare_me(self):
        assert parse_input("/me") == ("action", "")

class TestNickBroadcast:
    def test_nick_message_body_format(self):
        body = json.dumps({"old": "alice", "new": "alice2"})
        parsed = json.loads(body)
        assert parsed["old"] == "alice"
        assert parsed["new"] == "alice2"
