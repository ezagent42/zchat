"""单元测试：zchat/cli/routing.py 读写 API（独立于 CLI）。"""
from __future__ import annotations

import pytest

from zchat.cli.routing import (
    routing_path,
    load_routing,
    save_routing,
    init_routing,
    add_channel,
    list_channels,
    channel_exists,
    join_agent,
    remove_channel,
    set_entry_agent,
)


# ---------------------------------------------------------------------------
# init_routing
# ---------------------------------------------------------------------------

def test_init_routing_creates_file(tmp_path):
    init_routing(tmp_path)
    assert routing_path(tmp_path).exists()


def test_init_routing_idempotent(tmp_path):
    """调用两次不报错，文件内容不变。"""
    init_routing(tmp_path)
    add_channel(tmp_path, "#foo")
    init_routing(tmp_path)  # 不覆盖已有文件
    data = load_routing(tmp_path)
    assert "#foo" in data["channels"]


def test_init_routing_empty_structure(tmp_path):
    init_routing(tmp_path)
    data = load_routing(tmp_path)
    assert data["channels"] == {}
    assert data["bots"] == {}


# ---------------------------------------------------------------------------
# load_routing / save_routing
# ---------------------------------------------------------------------------

def test_load_routing_missing_file(tmp_path):
    data = load_routing(tmp_path)
    assert data == {"bots": {}, "channels": {}}


def test_save_and_load_roundtrip(tmp_path):
    original = {
        "bots": {"customer": {"credential_file": "credentials/customer.json", "lazy_create_enabled": True}},
        "channels": {"#ch-1": {"bot": "customer", "external_chat_id": "oc_abc", "agents": {}}},
    }
    save_routing(tmp_path, original)
    loaded = load_routing(tmp_path)
    assert loaded["channels"]["#ch-1"]["external_chat_id"] == "oc_abc"
    assert loaded["bots"]["customer"]["credential_file"] == "credentials/customer.json"


def test_save_routing_atomic(tmp_path):
    """原子写入：写完后文件存在，临时文件不存在。"""
    save_routing(tmp_path, {"bots": {}, "channels": {}})
    p = routing_path(tmp_path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    assert p.exists()
    assert not tmp.exists()


# ---------------------------------------------------------------------------
# add_channel
# ---------------------------------------------------------------------------

def test_add_channel_minimal(tmp_path):
    add_channel(tmp_path, "#minimal")
    data = load_routing(tmp_path)
    assert "#minimal" in data["channels"]
    assert data["channels"]["#minimal"] == {}


def test_add_channel_with_all_fields(tmp_path):
    add_channel(
        tmp_path, "#full",
        external_chat_id="oc_111",
        entry_agent="alice-fast-001",
    )
    data = load_routing(tmp_path)
    ch = data["channels"]["#full"]
    assert ch["external_chat_id"] == "oc_111"
    assert ch["entry_agent"] == "alice-fast-001"


def test_add_channel_duplicate_raises(tmp_path):
    add_channel(tmp_path, "#dup")
    with pytest.raises(ValueError, match="already exists"):
        add_channel(tmp_path, "#dup")


def test_add_multiple_channels(tmp_path):
    add_channel(tmp_path, "#ch-1")
    add_channel(tmp_path, "#ch-2")
    data = load_routing(tmp_path)
    assert len(data["channels"]) == 2


# ---------------------------------------------------------------------------
# list_channels
# ---------------------------------------------------------------------------

def test_list_channels_empty(tmp_path):
    assert list_channels(tmp_path) == []


def test_list_channels_returns_channel_id(tmp_path):
    add_channel(tmp_path, "#alpha")
    result = list_channels(tmp_path)
    assert len(result) == 1
    assert result[0]["channel_id"] == "#alpha"


def test_list_channels_includes_all_fields(tmp_path):
    add_channel(tmp_path, "#beta", external_chat_id="oc_b", entry_agent="alice-fast")
    result = list_channels(tmp_path)
    ch = result[0]
    assert ch["external_chat_id"] == "oc_b"
    assert ch["entry_agent"] == "alice-fast"


# ---------------------------------------------------------------------------
# channel_exists
# ---------------------------------------------------------------------------

def test_channel_exists_true(tmp_path):
    add_channel(tmp_path, "#exist")
    assert channel_exists(tmp_path, "#exist") is True


def test_channel_exists_false(tmp_path):
    assert channel_exists(tmp_path, "#nope") is False


# ---------------------------------------------------------------------------
# join_agent (V6 收尾后：只写 entry_agent，不存 agents 列表)
# ---------------------------------------------------------------------------

def test_join_agent_unknown_channel_raises(tmp_path):
    with pytest.raises(ValueError, match="not registered"):
        join_agent(tmp_path, "#ghost", "alice-bot")


def test_join_does_not_write_agents_field(tmp_path):
    """join_agent 不再维护 channel→agents 列表（roster 由 IRC NAMES 反映）。"""
    add_channel(tmp_path, "#ch")
    join_agent(tmp_path, "#ch", "alice-fast-001")
    data = load_routing(tmp_path)
    assert "agents" not in data["channels"]["#ch"]


# ---------------------------------------------------------------------------
# remove_channel
# ---------------------------------------------------------------------------

def test_remove_channel(tmp_path):
    add_channel(tmp_path, "#to-remove")
    remove_channel(tmp_path, "#to-remove")
    data = load_routing(tmp_path)
    assert "#to-remove" not in data["channels"]


def test_remove_channel_nonexistent_silent(tmp_path):
    """移除不存在的 channel 不报错。"""
    remove_channel(tmp_path, "#ghost")  # 不应抛异常


def test_remove_channel_leaves_others(tmp_path):
    add_channel(tmp_path, "#keep")
    add_channel(tmp_path, "#remove")
    remove_channel(tmp_path, "#remove")
    data = load_routing(tmp_path)
    assert "#keep" in data["channels"]
    assert "#remove" not in data["channels"]


# ---------------------------------------------------------------------------
# V6: entry_agent / bot
# ---------------------------------------------------------------------------

def test_add_channel_with_entry_agent_and_bot(tmp_path):
    from zchat.cli.routing import add_bot
    add_bot(tmp_path, "customer", credential_file="credentials/customer.json")
    add_channel(
        tmp_path, "#ch",
        external_chat_id="oc_xxx",
        bot="customer",
        entry_agent="alice-fast",
    )
    data = load_routing(tmp_path)
    ch = data["channels"]["#ch"]
    assert ch["external_chat_id"] == "oc_xxx"
    assert ch["bot"] == "customer"
    assert ch["entry_agent"] == "alice-fast"


def test_add_channel_unknown_bot_raises(tmp_path):
    from zchat.cli.routing import add_channel
    with pytest.raises(ValueError, match="not registered"):
        add_channel(tmp_path, "#ch", bot="ghost")


# ---------------------------------------------------------------------------
# V6: bot CRUD
# ---------------------------------------------------------------------------

def test_add_bot_writes_routing(tmp_path):
    from zchat.cli.routing import add_bot, list_bots
    add_bot(
        tmp_path, "customer",
        credential_file="credentials/customer.json",
        default_agent_template="fast-agent",
        lazy_create_enabled=True,
    )
    bots = list_bots(tmp_path)
    assert len(bots) == 1
    assert bots[0]["name"] == "customer"
    assert bots[0]["credential_file"] == "credentials/customer.json"
    assert bots[0]["lazy_create_enabled"] is True
    # V7: app_id 不再写 routing.toml
    assert "app_id" not in bots[0]


def test_add_bot_duplicate_raises(tmp_path):
    from zchat.cli.routing import add_bot
    add_bot(tmp_path, "customer", credential_file="credentials/customer.json")
    with pytest.raises(ValueError, match="already exists"):
        add_bot(tmp_path, "customer", credential_file="credentials/customer.json")


def test_remove_bot_idempotent(tmp_path):
    from zchat.cli.routing import add_bot, remove_bot, list_bots
    add_bot(tmp_path, "customer", credential_file="credentials/customer.json")
    remove_bot(tmp_path, "customer")
    remove_bot(tmp_path, "customer")  # 不存在不抛
    assert list_bots(tmp_path) == []


def test_first_join_auto_sets_entry(tmp_path):
    """首个 agent join 时自动设为 entry_agent（channel 还没 entry）。"""
    add_channel(tmp_path, "#ch")
    join_agent(tmp_path, "#ch", "alice-fast-001")
    data = load_routing(tmp_path)
    assert data["channels"]["#ch"]["entry_agent"] == "alice-fast-001"


def test_second_join_does_not_override_entry(tmp_path):
    """后续 agent join 不改变已有 entry_agent，除非 as_entry=True。"""
    add_channel(tmp_path, "#ch")
    join_agent(tmp_path, "#ch", "alice-fast-001")
    join_agent(tmp_path, "#ch", "alice-deep-001")
    data = load_routing(tmp_path)
    assert data["channels"]["#ch"]["entry_agent"] == "alice-fast-001"


def test_join_as_entry_overrides(tmp_path):
    """as_entry=True 强制改 entry_agent。"""
    add_channel(tmp_path, "#ch", entry_agent="pre-existing")
    join_agent(tmp_path, "#ch", "alice-deep-001", as_entry=True)
    data = load_routing(tmp_path)
    assert data["channels"]["#ch"]["entry_agent"] == "alice-deep-001"


def test_set_entry_agent(tmp_path):
    add_channel(tmp_path, "#ch")
    join_agent(tmp_path, "#ch", "alice-fast-001")
    set_entry_agent(tmp_path, "#ch", "alice-deep-999")
    data = load_routing(tmp_path)
    assert data["channels"]["#ch"]["entry_agent"] == "alice-deep-999"


def test_set_entry_agent_unknown_channel(tmp_path):
    with pytest.raises(ValueError, match="not registered"):
        set_entry_agent(tmp_path, "#ghost", "nick")
