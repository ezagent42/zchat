"""Tests for wc_protocol shared module."""


def test_make_private_pair_sorted():
    from wc_protocol.topics import make_private_pair
    assert make_private_pair("bob", "alice") == "alice_bob"
    assert make_private_pair("alice", "bob") == "alice_bob"


def test_channel_topic():
    from wc_protocol.topics import channel_topic
    assert channel_topic("general") == "wc/channels/general/messages"


def test_private_topic():
    from wc_protocol.topics import private_topic
    assert private_topic("alice_bob") == "wc/private/alice_bob/messages"


def test_presence_topic():
    from wc_protocol.topics import presence_topic
    assert presence_topic("alice") == "wc/presence/alice"


def test_channel_presence_topic():
    from wc_protocol.topics import channel_presence_topic
    assert channel_presence_topic("general", "alice") == "wc/channels/general/presence/alice"


def test_channel_presence_glob():
    from wc_protocol.topics import channel_presence_glob
    assert channel_presence_glob("general") == "wc/channels/general/presence/*"


def test_target_to_buffer_label_channel():
    from wc_protocol.topics import target_to_buffer_label
    assert target_to_buffer_label("channel:general", "alice") == "channel:#general"


def test_target_to_buffer_label_private():
    from wc_protocol.topics import target_to_buffer_label
    assert target_to_buffer_label("private:alice_bob", "alice") == "private:@bob"


def test_parse_input_msg():
    from wc_protocol.topics import parse_input
    assert parse_input("hello") == ("msg", "hello")


def test_parse_input_action():
    from wc_protocol.topics import parse_input
    assert parse_input("/me waves") == ("action", "waves")


def test_extract_other_nick():
    from wc_protocol.topics import extract_other_nick
    assert extract_other_nick("alice_bob", "alice") == "bob"
    assert extract_other_nick("alice_bob", "bob") == "alice"


def test_parse_target_key():
    from wc_protocol.topics import parse_target_key
    assert parse_target_key("channel:general") == ("channel", "general")
    assert parse_target_key("private:alice_bob") == ("private", "alice_bob")


def test_zenoh_default_endpoint():
    from wc_protocol.config import ZENOH_DEFAULT_ENDPOINT
    assert ZENOH_DEFAULT_ENDPOINT == "tcp/127.0.0.1:7447"


def test_build_zenoh_client_config_default():
    from wc_protocol.config import build_zenoh_config_dict
    result = build_zenoh_config_dict()
    assert result["mode"] == "client"
    assert result["connect/endpoints"] == ["tcp/127.0.0.1:7447"]


def test_build_zenoh_client_config_custom():
    from wc_protocol.config import build_zenoh_config_dict
    result = build_zenoh_config_dict(connect="tcp/10.0.0.1:7447,tcp/10.0.0.2:7447")
    assert result["connect/endpoints"] == ["tcp/10.0.0.1:7447", "tcp/10.0.0.2:7447"]


def test_scoped_name_adds_prefix():
    from wc_protocol.naming import scoped_name
    assert scoped_name("helper", "alice") == "alice:helper"


def test_scoped_name_no_double_prefix():
    from wc_protocol.naming import scoped_name
    assert scoped_name("alice:helper", "alice") == "alice:helper"


def test_scoped_name_different_prefix():
    from wc_protocol.naming import scoped_name
    assert scoped_name("bob:helper", "alice") == "bob:helper"


def test_signal_constants():
    from wc_protocol.signals import (
        SIGNAL_MESSAGE_SENT, SIGNAL_MESSAGE_RECEIVED, SIGNAL_PRESENCE_CHANGED
    )
    assert SIGNAL_MESSAGE_SENT == "zenoh_message_sent"
    assert SIGNAL_MESSAGE_RECEIVED == "zenoh_message_received"
    assert SIGNAL_PRESENCE_CHANGED == "zenoh_presence_changed"
