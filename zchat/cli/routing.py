"""routing.toml 读写 API — CLI 视角。

routing.toml 是动态频道↔agent 映射文件，与静态的 config.toml 分离。
由 zchat channel create / agent create --channel / agent join 写入。
由 channel-server 在运行时读取。
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
        return {"channels": {}, "operators": {}}
    with open(p, "rb") as f:
        data = tomllib.load(f)
    data.setdefault("channels", {})
    data.setdefault("operators", {})
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
        save_routing(project_dir, {"channels": {}, "operators": {}})


# ---------------------------------------------------------------------------
# 高层 API
# ---------------------------------------------------------------------------

def add_channel(
    project_dir: str | Path,
    channel_id: str,
    *,
    feishu_chat_id: str | None = None,
    squad_chat_id: str | None = None,
    squad_thread_root: str | None = None,
    default_agents: list[str] | None = None,
) -> None:
    """添加一个 channel 条目到 routing.toml。已存在则抛 ValueError。"""
    data = load_routing(project_dir)
    channels = data.setdefault("channels", {})
    if channel_id in channels:
        raise ValueError(f"Channel '{channel_id}' already exists")
    entry: dict = {}
    if feishu_chat_id:
        entry["feishu_chat_id"] = feishu_chat_id
    if squad_chat_id:
        entry["squad_chat_id"] = squad_chat_id
    if squad_thread_root:
        entry["squad_thread_root"] = squad_thread_root
    if default_agents:
        entry["default_agents"] = list(default_agents)
    entry["agents"] = {}
    channels[channel_id] = entry
    save_routing(project_dir, data)


def list_channels(project_dir: str | Path) -> list[dict]:
    """返回所有 channel 的列表，每项包含 channel_id 和配置字段。"""
    data = load_routing(project_dir)
    out = []
    for ch_id, ch in (data.get("channels") or {}).items():
        out.append({"channel_id": ch_id, **ch})
    return out


def channel_exists(project_dir: str | Path, channel_id: str) -> bool:
    """检查 channel 是否已在 routing.toml 中注册。"""
    data = load_routing(project_dir)
    return channel_id in data.get("channels", {})


def join_agent(
    project_dir: str | Path,
    channel_id: str,
    role: str,
    nick: str,
) -> None:
    """把某 agent nick 登记为某 channel 的某 role。若 channel 不存在抛 ValueError。"""
    data = load_routing(project_dir)
    channels = data.setdefault("channels", {})
    if channel_id not in channels:
        raise ValueError(
            f"channel '{channel_id}' not registered, run `zchat channel create`"
        )
    agents_map = channels[channel_id].setdefault("agents", {})
    agents_map[role] = nick
    save_routing(project_dir, data)


def remove_channel(project_dir: str | Path, channel_id: str) -> None:
    """从 routing.toml 移除 channel。不存在时静默忽略。"""
    data = load_routing(project_dir)
    channels = data.get("channels") or {}
    if channel_id in channels:
        del channels[channel_id]
        save_routing(project_dir, data)
