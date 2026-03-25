import time
from wc_protocol.sys_messages import SYS_PREFIX, is_sys_message, make_sys_message


def test_sys_prefix():
    assert SYS_PREFIX == "sys."


def test_is_sys_message_true():
    assert is_sys_message({"type": "sys.ping", "body": {}}) is True
    assert is_sys_message({"type": "sys.stop_request", "body": {}}) is True


def test_is_sys_message_false():
    assert is_sys_message({"type": "msg", "body": "hello"}) is False
    assert is_sys_message({"type": "action", "body": "waves"}) is False
    assert is_sys_message({}) is False


def test_make_sys_message_fields():
    msg = make_sys_message("alice", "sys.ping", {})
    assert msg["nick"] == "alice"
    assert msg["type"] == "sys.ping"
    assert msg["body"] == {}
    assert msg["ref_id"] is None
    assert "id" in msg
    assert len(msg["id"]) == 8
    assert isinstance(msg["ts"], float)


def test_make_sys_message_with_ref_id():
    msg = make_sys_message("alice", "sys.pong", {}, ref_id="abc123")
    assert msg["ref_id"] == "abc123"


def test_make_sys_message_with_body():
    msg = make_sys_message("alice", "sys.stop_request", {"reason": "user requested"})
    assert msg["body"] == {"reason": "user requested"}
