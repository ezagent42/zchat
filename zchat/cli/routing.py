"""routing.toml 读写 API — CLI 视角（V6）。

routing.toml 是动态运行时配置（与静态 config.toml 分离）。
由 zchat bot/channel/agent 命令写入，由 channel-server / bridge 读取。

V6 schema：

    [bots."<bot_name>"]                   # 由 zchat bot add 写入
    app_id = "cli_..."
    credential_file = "credentials/<bot_name>.json"
    default_agent_template = "fast-agent"
    lazy_create_enabled = true

    [channels."conv-001"]                 # 由 zchat channel create 写入
    bot = "<bot_name>"
    external_chat_id = "oc_..."
    entry_agent = "yaosh-fast-001"        # 由 zchat agent create --channel 写入（首个 agent 自动）

注：channel 内有哪些 agent 不在 routing.toml 维护。运行时 roster 由 IRC NAMES 反映；
agent 之间发现 peer 用 `list_peers(channel)` MCP tool。
"""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

import tomli_w


def routing_path(project_dir: str | Path) -> Path:
    """返回 routing.toml 的路径。"""
    return Path(project_dir) / "routing.toml"


def load_routing(project_dir: str | Path) -> dict:
    """加载 routing.toml，不存在返回空 dict。"""
    p = routing_path(project_dir)
    if not p.exists():
        return {"bots": {}, "channels": {}}
    with open(p, "rb") as f:
        data = tomllib.load(f)
    data.setdefault("bots", {})
    data.setdefault("channels", {})
    return data


def save_routing(project_dir: str | Path, data: dict) -> None:
    """原子写入 routing.toml。"""
    p = routing_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = tomli_w.dumps(data)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(p)


def init_routing(project_dir: str | Path) -> None:
    """初始化一个空的 routing.toml（project create 时调用）。"""
    p = routing_path(project_dir)
    if not p.exists():
        save_routing(project_dir, {"bots": {}, "channels": {}})


# ---------------------------------------------------------------------------
# Bots（V6 新增）
# ---------------------------------------------------------------------------

def add_bot(
    project_dir: str | Path,
    name: str,
    *,
    app_id: str,
    credential_file: str | None = None,
    default_agent_template: str | None = None,
    lazy_create_enabled: bool = False,
    supervises: list[str] | None = None,
) -> None:
    """注册一个 bot 到 routing.toml [bots] 表。已存在抛 ValueError。

    supervises: 该 bot 监管哪些 bot 的 channels（V6 按 bot 名；V7+ 支持 tag:/pattern:）。
    """
    data = load_routing(project_dir)
    bots = data.setdefault("bots", {})
    if name in bots:
        raise ValueError(f"Bot '{name}' already exists")
    entry: dict = {"app_id": app_id, "lazy_create_enabled": lazy_create_enabled}
    if credential_file:
        entry["credential_file"] = credential_file
    if default_agent_template:
        entry["default_agent_template"] = default_agent_template
    if supervises:
        entry["supervises"] = list(supervises)
    bots[name] = entry
    save_routing(project_dir, data)


def list_bots(project_dir: str | Path) -> list[dict]:
    """返回所有已注册 bot 列表，每项含 name + 其余字段。"""
    data = load_routing(project_dir)
    return [{"name": n, **b} for n, b in (data.get("bots") or {}).items()]


def remove_bot(project_dir: str | Path, name: str) -> None:
    """从 routing.toml 移除 bot；不存在静默忽略。"""
    data = load_routing(project_dir)
    bots = data.get("bots") or {}
    if name in bots:
        del bots[name]
        save_routing(project_dir, data)


def bot_exists(project_dir: str | Path, name: str) -> bool:
    data = load_routing(project_dir)
    return name in (data.get("bots") or {})


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

def add_channel(
    project_dir: str | Path,
    channel_id: str,
    *,
    bot: str | None = None,
    external_chat_id: str | None = None,
    entry_agent: str | None = None,
) -> None:
    """添加 channel 到 routing.toml。已存在抛 ValueError。"""
    data = load_routing(project_dir)
    channels = data.setdefault("channels", {})
    if channel_id in channels:
        raise ValueError(f"Channel '{channel_id}' already exists")
    if bot and bot not in (data.get("bots") or {}):
        raise ValueError(
            f"Bot '{bot}' not registered, run `zchat bot add {bot} ...` first"
        )
    entry: dict = {}
    if bot:
        entry["bot"] = bot
    if external_chat_id:
        entry["external_chat_id"] = external_chat_id
    if entry_agent:
        entry["entry_agent"] = entry_agent
    channels[channel_id] = entry
    save_routing(project_dir, data)


def list_channels(project_dir: str | Path) -> list[dict]:
    """返回所有 channel 列表，每项含 channel_id + 配置字段。"""
    data = load_routing(project_dir)
    return [{"channel_id": ch_id, **ch} for ch_id, ch in (data.get("channels") or {}).items()]


def channel_exists(project_dir: str | Path, channel_id: str) -> bool:
    data = load_routing(project_dir)
    return channel_id in (data.get("channels") or {})


def join_agent(
    project_dir: str | Path,
    channel_id: str,
    nick: str,
    *,
    as_entry: bool = False,
) -> None:
    """把某 agent nick 登记到 channel。channel 不存在抛 ValueError。

    routing.toml 不存 channel→agents 列表（运行时由 IRC NAMES 反映）。
    本函数仅在以下两种情况写入 entry_agent：
      - as_entry=True：显式声明
      - channel 还没有 entry_agent：把当前 nick 设为 entry（首个 agent）
    """
    data = load_routing(project_dir)
    channels = data.setdefault("channels", {})
    if channel_id not in channels:
        raise ValueError(
            f"channel '{channel_id}' not registered, run `zchat channel create`"
        )
    ch = channels[channel_id]
    if as_entry or not ch.get("entry_agent"):
        ch["entry_agent"] = nick
        save_routing(project_dir, data)


def set_entry_agent(
    project_dir: str | Path,
    channel_id: str,
    nick: str,
) -> None:
    """显式修改 channel 的 entry_agent。channel 不存在抛 ValueError。"""
    data = load_routing(project_dir)
    channels = data.setdefault("channels", {})
    if channel_id not in channels:
        raise ValueError(f"channel '{channel_id}' not registered")
    channels[channel_id]["entry_agent"] = nick
    save_routing(project_dir, data)


def remove_channel(project_dir: str | Path, channel_id: str) -> None:
    """从 routing.toml 移除 channel；不存在静默忽略。"""
    data = load_routing(project_dir)
    channels = data.get("channels") or {}
    if channel_id in channels:
        del channels[channel_id]
        save_routing(project_dir, data)
