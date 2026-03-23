"""Tests for weechat-channel-server/message.py"""

from message import (
    MessageDedup,
    detect_mention,
    clean_mention,
    chunk_message,
)
from wc_protocol.topics import make_private_pair, private_topic, channel_topic, presence_topic


class TestMessageDedup:
    def test_first_message_not_duplicate(self):
        d = MessageDedup()
        assert d.is_duplicate("msg-1") is False

    def test_same_id_is_duplicate(self):
        d = MessageDedup()
        d.is_duplicate("msg-1")
        assert d.is_duplicate("msg-1") is True

    def test_different_ids_not_duplicate(self):
        d = MessageDedup()
        d.is_duplicate("msg-1")
        assert d.is_duplicate("msg-2") is False

    def test_capacity_eviction(self):
        d = MessageDedup(capacity=3)
        d.is_duplicate("a")
        d.is_duplicate("b")
        d.is_duplicate("c")
        # At capacity now. Adding "d" evicts "a".
        assert d.is_duplicate("d") is False
        # "a" was evicted, so it's no longer duplicate
        assert d.is_duplicate("a") is False
        # "c" and "d" should still be tracked
        assert d.is_duplicate("d") is True
        assert d.is_duplicate("c") is True

    def test_len(self):
        d = MessageDedup()
        d.is_duplicate("a")
        d.is_duplicate("b")
        assert len(d) == 2


class TestMentionDetection:
    def test_mention_present(self):
        assert detect_mention("hey @alice:agent0 do stuff", "alice:agent0") is True

    def test_mention_absent(self):
        assert detect_mention("hello everyone", "alice:agent0") is False

    def test_mention_different_agent(self):
        assert detect_mention("@bob:agent1 help", "alice:agent0") is False

    def test_mention_at_start(self):
        assert detect_mention("@alice:agent0 list files", "alice:agent0") is True

    def test_mention_at_end(self):
        assert detect_mention("help me @alice:agent0", "alice:agent0") is True

    def test_mention_no_collision_across_users(self):
        """alice:agent0 and bob:agent0 should not collide."""
        assert detect_mention("@bob:agent0 help", "alice:agent0") is False


class TestCleanMention:
    def test_removes_mention(self):
        assert clean_mention("@alice:agent0 list files", "alice:agent0") == "list files"

    def test_removes_mention_middle(self):
        assert clean_mention("hey @alice:agent0 do stuff", "alice:agent0") == "hey  do stuff"

    def test_no_mention_unchanged(self):
        assert clean_mention("hello world", "alice:agent0") == "hello world"


class TestMakePrivatePair:
    def test_alphabetical_order(self):
        assert make_private_pair("bob", "alice") == "alice_bob"

    def test_same_order(self):
        assert make_private_pair("alice", "bob") == "alice_bob"

    def test_same_nick(self):
        assert make_private_pair("alice", "alice") == "alice_alice"

    def test_agent_pair(self):
        assert make_private_pair("alice:agent0", "bob") == "alice:agent0_bob"


class TestTopicHelpers:
    def test_private_topic(self):
        assert private_topic("alice_bob") == "wc/private/alice_bob/messages"

    def test_channel_topic(self):
        assert channel_topic("general") == "wc/channels/general/messages"

    def test_presence_topic(self):
        assert presence_topic("alice:agent0") == "wc/presence/alice:agent0"


class TestChunkMessage:
    def test_short_message_single_chunk(self):
        assert chunk_message("hello") == ["hello"]

    def test_long_message_split(self):
        text = "a" * 5000
        chunks = chunk_message(text, max_length=2000)
        assert len(chunks) > 1
        assert "".join(chunks) == text

    def test_split_at_paragraph(self):
        text = "paragraph one\n\nparagraph two\n\nparagraph three"
        chunks = chunk_message(text, max_length=30)
        assert len(chunks) >= 2
        # Each chunk should be a clean split
        for chunk in chunks:
            assert len(chunk) <= 30

    def test_empty_message(self):
        assert chunk_message("") == [""]

    def test_exact_boundary(self):
        text = "a" * 4000
        assert chunk_message(text) == [text]
