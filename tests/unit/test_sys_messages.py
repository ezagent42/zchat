from wc_protocol.sys_messages import (
    SYS_PREFIX, IRC_SYS_PREFIX, is_sys_message, make_sys_message,
    encode_sys_for_irc, decode_sys_from_irc,
)


def test_sys_prefix():
    assert SYS_PREFIX == "sys."


def test_irc_sys_prefix():
    assert IRC_SYS_PREFIX == "__wc_sys:"


def test_is_sys_message_true():
    assert is_sys_message({"type": "sys.ping"}) is True
    assert is_sys_message({"type": "sys.stop_request"}) is True


def test_is_sys_message_false():
    assert is_sys_message({"type": "msg"}) is False
    assert is_sys_message({}) is False


def test_make_sys_message_fields():
    msg = make_sys_message("alice", "sys.ping", {})
    assert msg["nick"] == "alice"
    assert msg["type"] == "sys.ping"
    assert msg["body"] == {}
    assert msg["ref_id"] is None
    assert len(msg["id"]) == 8
    assert isinstance(msg["ts"], float)


def test_make_sys_message_with_ref_id():
    msg = make_sys_message("alice", "sys.pong", {}, ref_id="abc123")
    assert msg["ref_id"] == "abc123"


def test_encode_sys_for_irc():
    msg = make_sys_message("alice", "sys.ping", {})
    encoded = encode_sys_for_irc(msg)
    assert encoded.startswith("__wc_sys:")
    assert '"sys.ping"' in encoded


def test_decode_sys_from_irc():
    msg = make_sys_message("alice", "sys.ping", {})
    encoded = encode_sys_for_irc(msg)
    decoded = decode_sys_from_irc(encoded)
    assert decoded is not None
    assert decoded["type"] == "sys.ping"
    assert decoded["nick"] == "alice"


def test_decode_sys_from_irc_not_sys():
    assert decode_sys_from_irc("hello world") is None
    assert decode_sys_from_irc("{not sys}") is None


def test_decode_sys_from_irc_bad_json():
    assert decode_sys_from_irc("__wc_sys:not-json") is None
