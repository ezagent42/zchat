# 07 · 凭证管理 + token 缓存

## 1. 飞书 vs WeCom 凭证字段

### 飞书 `credentials/<bot>.json`
```json
{
  "app_id": "cli_a954xxxxx",
  "app_secret": "QkA9dKr..."
}
```

仅 2 字段。SDK 自动管理 access_token 缓存。

### WeCom 需要 5 字段
```json
{
  "type": "wecom",
  "corp_id": "ww123abcdef0123",
  "corp_secret": "xx-secret-yyyy",
  "agent_id": 1000002,
  "callback_token": "RandomString32B",
  "encoding_aes_key": "43-char-base64-AES-key-from-WeCom-console"
}
```

新增的 4 字段：
- `corp_id` 替代 app_id
- `corp_secret` 替代 app_secret
- `agent_id` — 自建应用的整数 ID
- `callback_token` — 回调 URL signature 用
- `encoding_aes_key` — 回调内容 AES 加密 key

**`type` 字段是新加的**：让 zchat 区分 feishu 还是 wecom。`zchat bot add` 加 `--type {feishu,wecom}` 参数。如果文件里有 `type` 字段优先；否则默认 `feishu`（向后兼容现有部署）。

## 2. routing.toml 改造

```toml
[bots.customer-wecom]
type = "wecom"                                          # ← 新字段
credential_file = "credentials/customer-wecom.json"
default_agent_template = "fast-agent"
lazy_create_enabled = true
# WeCom 特有：callback URL 公网部分（用于 zchat doctor 检查 + 文档化）
callback_public_url = "https://wecom-customer.inside.h2os.cloud/wecom/callback"
```

`type` 的兼容性：
- 旧 routing.toml `[bots.X]` 无 `type` 字段 → 默认 `feishu`，行为不变
- 新加 wecom bot 必须显式 `type = "wecom"`

CLI `zchat bot add` 改：
```bash
# 飞书（默认）
zchat bot add customer --credential credentials/customer.json

# WeCom
zchat bot add customer-wecom --type wecom --credential credentials/customer-wecom.json
```

cli 改动只 1 行（加 `--type` typer option），符合"cli 不绑业务"原则 — type 字段语义还是 routing.toml + bridge 自己解释。

## 3. wecom_bridge/config.py

```python
"""WeCom bridge 运行时配置。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WeComCredentials:
    corp_id: str
    corp_secret: str
    agent_id: int
    callback_token: str
    encoding_aes_key: str


@dataclass
class LazyCreateConfig:
    enabled: bool = False
    entry_agent_template: str = "fast-agent"
    channel_prefix: str = "conv-"


@dataclass
class WeComBridgeConfig:
    wecom: WeComCredentials
    bot_name: str = ""
    channel_server_url: str = "ws://127.0.0.1:9999"
    callback_host: str = "127.0.0.1"
    callback_port: int = 8788
    callback_public_url: str = ""    # caddy 反代后的公网 URL（log + doctor 显示）
    upload_dir: str = ".wecom-bridge/uploads"
    routing_path: str = "routing.toml"
    download_media: bool = True
    lazy_create: LazyCreateConfig = field(default_factory=LazyCreateConfig)


def build_config_from_routing(
    routing_path: str | Path,
    bot_name: str,
    *,
    channel_server_url: str = "ws://127.0.0.1:9999",
    callback_host: str = "127.0.0.1",
    callback_port: int = 8788,
) -> WeComBridgeConfig:
    """从 routing.toml [bots.<bot_name>] + credentials JSON 构造配置。"""
    from wecom_bridge.routing_reader import read_bot_config

    bot_cfg = read_bot_config(routing_path, bot_name)
    if not bot_cfg:
        raise ValueError(f"bot '{bot_name}' not found in {routing_path}")
    if bot_cfg.get("type") != "wecom":
        raise ValueError(
            f"bot '{bot_name}' type={bot_cfg.get('type')} != wecom; "
            f"use feishu_bridge instead"
        )

    cred_file = bot_cfg.get("credential_file")
    if not cred_file:
        raise ValueError(f"bot '{bot_name}' missing credential_file")

    project_dir = Path(routing_path).parent
    cred_path = project_dir / cred_file
    if not cred_path.is_file():
        raise FileNotFoundError(f"credentials not found: {cred_path}")

    import json as _json
    cred_data = _json.loads(cred_path.read_text(encoding="utf-8"))

    required = ["corp_id", "corp_secret", "agent_id", "callback_token", "encoding_aes_key"]
    missing = [k for k in required if not cred_data.get(k)]
    if missing:
        raise ValueError(f"credentials/{cred_file} missing: {missing}")

    bridge_subdir = project_dir / f".wecom-bridge-{bot_name}"

    return WeComBridgeConfig(
        bot_name=bot_name,
        wecom=WeComCredentials(
            corp_id=cred_data["corp_id"],
            corp_secret=cred_data["corp_secret"],
            agent_id=int(cred_data["agent_id"]),
            callback_token=cred_data["callback_token"],
            encoding_aes_key=cred_data["encoding_aes_key"],
        ),
        channel_server_url=channel_server_url,
        callback_host=callback_host,
        callback_port=callback_port,
        callback_public_url=bot_cfg.get("callback_public_url", ""),
        upload_dir=str(bridge_subdir / "uploads"),
        routing_path=str(routing_path),
        download_media=True,
        lazy_create=LazyCreateConfig(
            enabled=bot_cfg.get("lazy_create_enabled", False),
            entry_agent_template=bot_cfg.get("default_agent_template") or "fast-agent",
        ),
    )
```

## 4. access_token 缓存（token_manager.py）

WeCom access_token：7200 秒有效期。同 corp_id+secret 全局共享，**不能多处并发刷新**（会作废前一个）。

策略：
- 单进程：`wechatpy.session.MemoryStorage`（默认）
- 多进程同 bot：用 `wechatpy.session.RedisStorage` 或 文件锁版

zchat 单 bot 一个 wecom_bridge 进程，无并发问题 → 用默认 MemoryStorage 即可。

但 voice_bridge / agent / 其他工具如果未来也调 WeCom API（如发短信）→ 多进程 → 需要文件锁版：

```python
# wecom_bridge/token_manager.py
import json
import time
import fcntl
from pathlib import Path
from wechatpy.session import SessionStorage


class FileLockTokenStorage(SessionStorage):
    """跨进程文件锁的 access_token 存储。

    用 fcntl LOCK_EX 互斥访问 token cache 文件，
    避免多个 bridge 实例同时调 gettoken 互相 invalidate。
    """

    def __init__(self, file_path: str):
        self._path = Path(file_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text())
        except Exception:
            return {}

    def _write(self, data: dict) -> None:
        self._path.write_text(json.dumps(data))

    def get(self, key, default=None):
        with open(self._path, "a+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            f.seek(0)
            try:
                data = json.load(f) if f.read(1) else {}
            except Exception:
                data = {}
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        if not isinstance(data, dict):
            return default
        entry = data.get(key)
        if not entry:
            return default
        if entry.get("expires_at", 0) < time.time():
            return default
        return entry.get("value", default)

    def set(self, key, value, ttl=None):
        # 锁文件写
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "r+" if self._path.exists() else "w+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.seek(0)
                content = f.read()
                data = json.loads(content) if content else {}
            except Exception:
                data = {}
            data[key] = {
                "value": value,
                "expires_at": time.time() + (ttl or 7200) - 300,  # 5min 提前
            }
            f.seek(0)
            f.truncate()
            json.dump(data, f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def delete(self, key):
        if not self._path.exists():
            return
        with open(self._path, "r+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                data = json.load(f)
            except Exception:
                data = {}
            data.pop(key, None)
            f.seek(0)
            f.truncate()
            json.dump(data, f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

bridge.py 启动时：
```python
from wecom_bridge.token_manager import FileLockTokenStorage
from wechatpy.work import WeChatClient

storage = FileLockTokenStorage(
    f"{config.upload_dir}/../wecom_token_{config.wecom.corp_id}.json"
)
client = WeChatClient(
    corp_id=config.wecom.corp_id,
    secret=config.wecom.corp_secret,
)
client.session = storage
```

## 5. 凭证安全

| 字段 | 敏感度 | 泄露后果 |
|---|---|---|
| corp_id | 低 | 公开信息（开企业的人都能看到）|
| corp_secret | **高** | 攻击者能假冒应用 — rotate 即失效，需所有 bridge 重启 |
| agent_id | 低 | 公开 |
| callback_token | 中 | 攻击者能伪造 callback signature |
| encoding_aes_key | **高** | 攻击者能解密 callback 内容（含客户隐私） |

部署要求：
- credentials/wecom.json 权限 `chmod 600`
- git ignore（已经 ignore 全部 `credentials/`）
- 备份到 1Password / vault，不放 share dir

## 6. 凭证申请操作步骤（部署文档化）

1. 进 [企业微信管理后台](https://work.weixin.qq.com/wework_admin/) → 我的企业 → 企业信息 → 复制 corp_id
2. 应用管理 → 自建应用 → 创建新应用 → 填名称 / logo
3. 在新应用页：
   - 复制 AgentId
   - 复制 Secret（**仅一次显示，立即存到 1Password**）
   - 接收消息 → 设置：
     - URL：`https://wecom-customer.inside.h2os.cloud/wecom/callback`（公网可达）
     - Token：`openssl rand -hex 16` 生成
     - EncodingAESKey：点"随机生成"，43 字符 base64
   - 保存 → WeCom 立即 GET 验证（要先把 wecom_bridge 跑起来 + caddy 接好）
4. 应用权限：勾选"接收会话内容"
5. 把上面 5 字段写入 credentials/wecom.json

## 7. 文件位置 + 命名约定

| 文件 | 路径 | 备注 |
|---|---|---|
| credentials | `~/.zchat/projects/<proj>/credentials/<bot-name>.json` | 跟 feishu 同目录 |
| token cache | `~/.zchat/projects/<proj>/.wecom-bridge-<bot>/wecom_token_<corp_id>.json` | bridge 自己写，gitignore |
| upload dir | `~/.zchat/projects/<proj>/.wecom-bridge-<bot>/uploads/` | 下载的 media 文件 |
| log | `~/.zchat/projects/<proj>/log/wecom-<bot>.log` | 跟 feishu log 同位 |

## 8. 测试

```python
# tests/unit/test_wecom_config.py
import json
import pytest
from pathlib import Path
from wecom_bridge.config import build_config_from_routing


def test_load_complete_config(tmp_path):
    routing = tmp_path / "routing.toml"
    routing.write_text('''
[bots.cust-wecom]
type = "wecom"
credential_file = "credentials/cust-wecom.json"
default_agent_template = "fast-agent"
lazy_create_enabled = true
''')
    cred = tmp_path / "credentials" / "cust-wecom.json"
    cred.parent.mkdir()
    cred.write_text(json.dumps({
        "corp_id": "ww1",
        "corp_secret": "secret",
        "agent_id": 1000001,
        "callback_token": "tok",
        "encoding_aes_key": "x" * 43,
    }))
    cfg = build_config_from_routing(routing, "cust-wecom")
    assert cfg.wecom.corp_id == "ww1"
    assert cfg.wecom.agent_id == 1000001
    assert cfg.lazy_create.enabled is True


def test_missing_type_rejects(tmp_path):
    routing = tmp_path / "routing.toml"
    routing.write_text('[bots.x]\ncredential_file = "x.json"')
    with pytest.raises(ValueError, match="type="):
        build_config_from_routing(routing, "x")


def test_missing_creds_field_rejects(tmp_path):
    routing = tmp_path / "routing.toml"
    routing.write_text('[bots.x]\ntype = "wecom"\ncredential_file = "x.json"')
    cred = tmp_path / "x.json"
    cred.write_text('{"corp_id": "y"}')   # 缺 secret/agent_id/...
    with pytest.raises(ValueError, match="missing"):
        build_config_from_routing(routing, "x")
```
