# 007 · Plugin 系统指南

> 所有条目都经过源码交叉验证（file:line 标注）。为什么这样设计、怎么用、怎么写、怎么对接外部系统。

## 1. 为什么有 plugin 层

CS (`channel-server`) 本身只做三件事：**IRC ↔ WS 协议翻译 + NAMES 熔断 + 命令路由分派**。一切业务语义（评分链路、求助 timer、活跃度跟踪、升级转结案率统计）全部从 CS 主干拆出到 plugin，通过**事件总线** 和 **命令分派**两个薄接口接入。

这样做的收益（由代码结构反推）：

1. **横向扩展**：加一种新业务语义 = 加一个新 plugin 文件，不碰 router/irc_connection
2. **关注点隔离**：router 不需要知道 "takeover 3 分钟超时自动 /release" 这种业务规则
3. **可独立测试**：每个 plugin 直接 mock `emit_event` + 喂入 msg/event 即可（参见 `tests/unit/test_*_plugin.py`）
4. **运行时可组合**：`__main__.py` 按需 register，要不要 CSAT 功能就看要不要注册 `CsatPlugin`

## 2. 机制：三个接口 + 一条事件总线

### 2.1 Plugin 协议（`channel_server/plugin.py:12-36`）

```python
@runtime_checkable
class Plugin(Protocol):
    name: str
    def handles_commands(self) -> list[str]: ...        # 声明接管的 /cmd
    async def on_ws_message(self, msg: dict) -> None:   # 订阅所有 WS message
    async def on_ws_event(self, event: dict) -> None:   # 订阅所有 WS event
    async def on_command(self, cmd_name, msg) -> None:  # 处理自己声明的 /cmd
    def query(self, key, args=None) -> Any:             # 暴露只读状态
```

`BasePlugin` (同文件 L39-57) 给五个方法都提供了 no-op 默认实现，继承它即可只挑关心的覆盖。

### 2.2 PluginRegistry（`channel_server/plugin.py:60-107`）

```python
registry.register(plugin)                    # 启动时冲突检测即失败（L67-79）
registry.get_handler(cmd_name) -> Plugin     # cmd → plugin 路由表（L81）
registry.get_plugin(name) -> Plugin          # 按名查 plugin（L84）
await registry.broadcast_message(msg)        # 遍历所有 plugin on_ws_message（L90-97）
await registry.broadcast_event(event)        # 遍历所有 plugin on_ws_event（L99-106）
```

**冲突检测**：两个 plugin 都声明 `/resolve` → `register` 直接抛 `ValueError`，CS 启动即挂。好过上线后才发现谁吃了命令。

**异常隔离**：某 plugin 的 `on_ws_message` 抛异常只 log 继续遍历（L96-97），不影响其它 plugin。

### 2.3 三路广播（`channel_server/router.py:212-240`）

```python
async def emit_event(self, channel, event, data):
    msg = ws_messages.build_event(channel, event, data or {})
    await self._ws.broadcast(msg)              # 路径 1: 所有 bridge (WS client)
    await self._registry.broadcast_event(msg)  # 路径 2: 所有 plugin (in-process)
    # 路径 3: IRC __zchat_sys: 瘦身版给 channel 内 agent（L228-238）
    self._irc.privmsg(irc_channel, encode_sys(slim_payload))
```

一次 emit，三路送达：**bridge 做 UI / 外部 API；plugin 做副作用 / 聚合；agent 做自主决策**。

### 2.4 命令分派（`router.py` `_handle_message` L75-101）

```
bridge 发 content="/hijack" → router:
  1. 查 registry.get_handler("hijack") → ModePlugin
  2. await plugin.on_command("hijack", msg)
  3. 不转发 IRC（命令消费）
  4. 仍 broadcast_message 给其他 plugin 订阅（让 audit 能记录"被触发"）
```

IRC 侧 agent 发 `/hijack` 也走同分派（`forward_inbound_irc` L187-200）。命令**对称**。

## 3. 6 个官方 plugin 速查

| Plugin | 源码行数 | 命令 | emit event | 持久化 | 内存状态 |
|---|---|---|---|---|---|
| mode | 49 | `/hijack` `/release` `/copilot` | `mode_changed` | ❌ | `dict[channel, "copilot"\|"takeover"]` |
| sla | 214 | — | `sla_breach` / `help_requested` / `help_timeout` | ❌ | 两张 `dict[channel, asyncio.Task]` |
| resolve | 38 | `/resolve` | `channel_resolved` | ❌ | 无 |
| audit | 207 | — | — (只订阅) | ✅ `audit.json` | 全部由 JSON 恢复 |
| activation | 123 | — | `customer_returned` | ✅ `activation-state.json` | 全部由 JSON 恢复 |
| csat | 74 | — | `csat_request` / `csat_recorded` | ❌ (转调 audit) | 持有 audit 引用 |

**行数验证**：`wc -l src/plugins/*/plugin.py` = 123/207/74/49/38/214 共 705 行实现 6 种运营语义。resolve 是**最小可运行 plugin 模板**。

## 4. 持久化机制：路径、schema、恢复语义

### 4.1 存储路径（`channel_server/__main__.py:85-92`）

```python
data_dir = Path(_env("CS_DATA_DIR") or Path(routing_path).parent)
AuditPlugin(persist_path=data_dir / "audit.json")
ActivationPlugin(state_file=data_dir / "activation-state.json", ...)
```

默认落 `~/.zchat/projects/<proj>/audit.json` 和 `activation-state.json`（与 `routing.toml` 同目录）。`CS_DATA_DIR` env 可覆盖（E2E 测试用 tmpdir）。

### 4.2 audit.json schema（`plugins/audit/plugin.py:69-83`）

```json
{
  "channels": {
    "conv-001": {
      "state": "active|takeover|resolved",
      "created_at": "2026-04-22T...",
      "first_message_at": "...",
      "first_reply_at": "...",
      "takeovers": [
        {"at":"...", "triggered_by":"...", "released_at":"...", "released_by":"..."}
      ],
      "resolved_at": "...",
      "message_count": 42,
      "csat_score": 4
    }
  }
}
```

**写盘策略**（L60-67）：write-to-tmp + atomic rename，每次状态变更都 flush。不是日志追加，是全量覆盖当前快照。

### 4.3 CS 重启后的恢复语义

| plugin | 重启后状态 |
|---|---|
| audit | 全部恢复（`_load()` L49-58） |
| activation | 全部恢复（同 pattern L44-53） |
| mode | **全部丢失** → 默认回 `copilot` |
| sla | **timer 全部丢失** → 触发后才重启 timer |
| resolve | 无状态，不受影响 |
| csat | 无自身状态；依赖 audit 的 `csat_score` 字段 |

**设计取舍**：mode/sla timer 是运行时态，不回放；audit/activation 是业务数据，必须回放。重启对 takeover 状态是**硬 reset**（回 copilot），这是故意的——timer 丢了不能 fake 恢复。

### 4.4 CLI workspace ↔ plugin workspace

```
~/.zchat/projects/<proj>/
├── config.toml             ← CLI 写，CLI 读
├── routing.toml            ← CLI 写；CS routing_watcher 读 + hot-reload
├── credentials/            ← CLI 写（zchat bot add --app-secret）；bridge 读
├── audit.json              ← AuditPlugin 读写
├── activation-state.json   ← ActivationPlugin 读写
├── cs.log / bridge-*.log   ← 各自进程 stdout redirect
├── agents/<nick>/          ← agent_manager 管理的 workspace
└── state.json              ← agent/irc lifecycle (CLI 的 zellij tab 记录)
```

**关键红线**：plugin **不读** `routing.toml` / `credentials/` / `config.toml`。路由是 router 的职责，凭证是 bridge 的职责。plugin 只碰自己的 JSON。

**CLI 查 audit 数据** 走 `zchat audit status/report`，实现在 `zchat/cli/audit_cmd.py`——直接读 `audit.json` 文件，不走 plugin query API。所以 audit plugin 和 CLI 实际上**都只认这一份文件**，通过文件解耦。

## 5. 什么时候该加 plugin？

**该加** (对应 plugin 层职责)：

- 业务事件流转 / 聚合统计（审计、评分、活跃度分析）
- 基于消息或 event 的定时行为（SLA timer / 冷启动 / 自动归档）
- 协议内命令扩展（`/foo` 这种可以在所有 channel 通用的命令）
- 需要在 **CS 进程内响应** event 的逻辑（零网络往返，同进程 asyncio）

**不该加** (放错层)：

| 需求 | 该放哪 |
|---|---|
| 飞书卡片渲染 / 飞书 API 调用 | `feishu_bridge/` |
| Agent 回复内容 / 人格 / skill 触发规则 | `templates/<agent>/` |
| 消息路由 / NAMES 熔断 / mode 决定 @ 前缀 | `channel_server/router.py` core |
| IRC 连接管理 / 成员缓存 | `channel_server/irc_connection.py` |
| routing.toml 热加载 | `channel_server/routing_watcher.py` |
| bot / channel CRUD | `zchat/cli/` |

## 6. Plugin 开发指南（从空到上线）

### Step 1 — 新建目录

```
zchat-channel-server/src/plugins/myname/
├── __init__.py      # 可空
└── plugin.py        # 本体
```

### Step 2 — 最小骨架（仿 `resolve/plugin.py`）

```python
from __future__ import annotations
from typing import Awaitable, Callable
from channel_server.plugin import BasePlugin


class MynamePlugin(BasePlugin):
    name = "myname"

    def __init__(
        self,
        emit_event: Callable[[str, str, dict], Awaitable[None]],
    ) -> None:
        self._emit_event = emit_event

    def handles_commands(self) -> list[str]:
        return ["mycmd"]  # 或 [] 如果只订阅事件

    async def on_command(self, cmd_name: str, msg: dict) -> None:
        await self._emit_event(
            "myevent", msg.get("channel", ""), {"by": msg.get("source")}
        )

    # 可选：
    # async def on_ws_message(self, msg): ...
    # async def on_ws_event(self, event): ...
    # def query(self, key, args=None): ...
```

`emit_event` 签名严格是 `(event_name, channel, data)` — 参见 ResolvePlugin (`resolve/plugin.py:34-38`)。

### Step 3 — 在 `__main__.py` 注册（改 `channel_server/__main__.py:81-93` 那一段）

```python
from plugins.myname.plugin import MynamePlugin
...
registry.register(MynamePlugin(emit_event=emit_event))
```

注册顺序不影响正确性（事件广播走 dict 迭代，每个 plugin 独立），但影响同 event 多个 plugin 的**订阅响应顺序**。

### Step 4 — 持久化（如需要，仿 `activation/plugin.py`）

复制 `_load()` / `_save()` pattern：

```python
def _load(self):
    if not self._path.exists():
        return {"channels": {}}
    return json.loads(self._path.read_text("utf-8"))

def _save(self):
    self._path.parent.mkdir(parents=True, exist_ok=True)
    tmp = self._path.with_suffix(self._path.suffix + ".tmp")
    tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2))
    tmp.replace(self._path)   # atomic
```

注册时带路径：

```python
registry.register(MynamePlugin(
    emit_event=emit_event,
    state_file=data_dir / "myname-state.json",
))
```

### Step 5 — 单元测试（仿 `tests/unit/test_resolve_plugin.py`）

```python
from unittest.mock import AsyncMock
import pytest
from plugins.myname.plugin import MynamePlugin

@pytest.fixture
def emit_event():
    return AsyncMock()

@pytest.mark.asyncio
async def test_command_emits_event(emit_event):
    p = MynamePlugin(emit_event=emit_event)
    await p.on_command("mycmd", {"channel": "#c", "source": "alice"})
    emit_event.assert_awaited_once()
    ev_name, channel, data = emit_event.call_args[0]
    assert ev_name == "myevent" and data["by"] == "alice"
```

### Step 6 — 外部依赖

如需新库（如 `aiohttp`），加到 `zchat-channel-server/pyproject.toml` 的 `dependencies`（参见已有 6 个依赖声明位置）。然后 `uv sync` + 重启 CS。

## 7. 外部系统对接：用 plugin 把达标客户推到另一个系统

**场景**：客户在 zchat 里达到某些条件（如结案 + CSAT ≥4 + takeover=0），需要把该客户的对话数据 POST 到外部 CRM。

### 7.1 拆成两个 plugin 而不是一个

**设计原则**：qualification 规则和 export 通道是两件事，拆开方便换规则/换目的地。

```
plugins/
├── qualifier/plugin.py    ← 订阅 channel_resolved + csat_recorded，判断达标 → emit "customer_qualified"
└── exporter/plugin.py     ← 订阅 customer_qualified → HTTP POST 外部 CRM
```

这样**换一家 CRM** 只改 exporter；**改一版规则**（比如加"结案前至少 10 条消息"）只改 qualifier。两个 plugin 通过 `customer_qualified` event 解耦。

### 7.2 Qualifier plugin 实现

```python
# src/plugins/qualifier/plugin.py
from channel_server.plugin import BasePlugin
from typing import Any, Awaitable, Callable

class QualifierPlugin(BasePlugin):
    name = "qualifier"

    def __init__(
        self,
        emit_event: Callable[[str, str, dict], Awaitable[None]],
        audit_plugin: Any,        # 通过 DI 拿到 AuditPlugin 引用（见 csat 模式）
        min_csat: int = 4,
    ) -> None:
        self._emit_event = emit_event
        self._audit = audit_plugin
        self._min_csat = min_csat

    async def on_ws_event(self, event: dict) -> None:
        if event.get("event") != "csat_recorded":
            return
        channel = event.get("channel") or ""
        score = (event.get("data") or {}).get("score", 0)
        if score < self._min_csat:
            return
        # 读 audit 状态做规则判断（query("status") 见 audit/plugin.py:156-159）
        status = self._audit.query("status", {"channel": channel}) or {}
        if status.get("state") != "resolved":
            return
        if len(status.get("takeovers") or []) > 0:
            return  # 发生过 takeover 的不算
        await self._emit_event(
            "customer_qualified", channel,
            {"score": score, "message_count": status.get("message_count", 0)},
        )
```

**关键技术点 — plugin 读其他 plugin 的状态**：
- Plugin 模块之间**禁止 import**（红线）
- 但 `__main__.py` 可以用 DI 注入引用，**csat plugin 就是这么拿到 audit 引用的**（`plugins/csat/plugin.py:28-31`，字段名 `_audit`，直接调 `self._audit.record_csat(...)`）
- qualifier 复用这个 pattern：`__main__.py` 注册时把 `audit_plugin` 实例传进来
- qualifier 调 `audit.query("status", {"channel": ch})` 得到该 channel 的完整 dict（audit 的 `query` 实现在 `plugins/audit/plugin.py:154-167`）

### 7.3 Exporter plugin 实现

```python
# src/plugins/exporter/plugin.py
import json, aiohttp
from pathlib import Path
from channel_server.plugin import BasePlugin

class ExporterPlugin(BasePlugin):
    name = "exporter"

    def __init__(self, state_file, endpoint, api_token):
        self._path = Path(state_file)
        self._endpoint = endpoint
        self._token = api_token
        self._state = self._load()   # {"exported": [channel_id, ...]}

    def _load(self):
        if not self._path.exists():
            return {"exported": []}
        return json.loads(self._path.read_text("utf-8"))

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2))
        tmp.replace(self._path)

    async def on_ws_event(self, event):
        if event.get("event") != "customer_qualified":
            return
        channel = event.get("channel") or ""
        if channel in self._state["exported"]:
            return                                # 幂等去重
        data = event.get("data") or {}
        async with aiohttp.ClientSession() as s:
            async with s.post(
                self._endpoint,
                json={"channel": channel, **data},
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status < 300:
                    self._state["exported"].append(channel)
                    self._save()
                # 非 2xx 不加入 exported，下次还会重试
```

### 7.4 两个 plugin 在 `__main__.py` 接线

```python
from plugins.qualifier.plugin import QualifierPlugin
from plugins.exporter.plugin import ExporterPlugin
...
audit_plugin = AuditPlugin(persist_path=data_dir / "audit.json")
registry.register(audit_plugin)
# ...先 register 完其它 plugin 后...
registry.register(QualifierPlugin(
    emit_event=emit_event,
    audit_plugin=audit_plugin,       # ← DI 注入
    min_csat=4,
))
registry.register(ExporterPlugin(
    state_file=data_dir / "exporter-state.json",
    endpoint=_env("EXPORT_ENDPOINT", "https://crm.example.com/api/customers"),
    api_token=_env("EXPORT_TOKEN", ""),
))
```

### 7.5 事件流示意

```
客户打 4⭐  →  bridge emit csat_score event
                     ↓ (CS router.emit_event 三路广播)
   ┌─────────┬─────────┐
   ▼         ▼         ▼
  WS      plugins     IRC sys
  ↓       ↓           ↓
 bridge   csat 订阅→   agent 感知
         audit.record_csat(4)
         emit csat_recorded
                     ↓ (再一次 emit → broadcast)
            qualifier 订阅 csat_recorded
            查 audit.query("status") 判断达标
            emit customer_qualified
                     ↓
            exporter 订阅 customer_qualified
            检查 exported 去重 → aiohttp POST CRM
            成功 → 落盘 exported 列表
```

**整条链路 3 次 emit_event，每个 plugin 只负责一小段逻辑**，CRM 方换一个或加第二个下游（比如同时推到数仓）都只在 exporter 改。

### 7.6 CS 重启后怎么办

- qualifier 无状态 → 重启无影响，下次 event 来了重新判断
- exporter 的 `exported` 列表落盘 → 重启后不会重发
- audit 持久化 → 重启后 `audit.query` 依然返回完整历史

### 7.7 错误模式 & 容错

**幂等性**：exporter 的 `exported` 列表保证同一 channel 不二次推送。HTTP 失败不加入列表，下次 qualify 事件来了会重试。

**外部 API 挂了**：`on_ws_event` 抛异常被 `broadcast_event` 吞掉（`plugin.py:101-106` 的 try/except），不影响其它 plugin。但重试需要再次收到 `customer_qualified` event——可在 exporter 内部加"失败队列 + 后台重试 task"如需强保证。

**非 2xx 响应**：当前实现只按 status code 判断，加入 `exported` 的条件是 `< 300`。需要更严格（比如对端返回自定义 JSON 成功码）就在 resp.json() 后判断。

## 8. 红线 & 约束

### 8.1 模块 import 红线

| 允许 | 禁止 |
|---|---|
| `from channel_server.plugin import BasePlugin` | `from plugins.X.plugin import Y`（在 plugin 内）|
| `from zchat_protocol import irc_encoding, ws_messages` | `from feishu_bridge...` |
| 标准库 / 第三方 (aiohttp, asyncio, json) | 其它业务 plugin 直接 import |

**唯一的跨 plugin 引用方式**：`__main__.py` 实例化时 DI 注入，不是 import。参见 csat 拿 audit 的实现（`plugins/csat/plugin.py:25-31`）。

### 8.2 业务术语

- Plugin **目录名 + 类名** 中性（mode / audit / activation，不是 feishu_audit / admin_plugin）
- Plugin **emit 的 event name** 可以带业务词（实证：`activation/plugin.py:90` emit `customer_returned`）
- Plugin **event payload key** 应尽量中性（`"sender"` 而不是 `"customer_name"`；实证同上 L93）

### 8.3 Plugin 不该碰什么

- ❌ `routing.toml` —— 路由是 router 的职责
- ❌ `credentials/*.json` —— bridge 的凭证
- ❌ 其它 plugin 的持久化文件（`audit.json` 等）—— 走 DI + query API
- ❌ 直接调 IRC / WS（要调走 `emit_event` 总线）

## 9. 测试套路

每个 plugin 配一个 `tests/unit/test_<name>_plugin.py`：

```python
from unittest.mock import AsyncMock
import pytest
from plugins.myname.plugin import MynamePlugin

@pytest.fixture
def emit_event():
    return AsyncMock()

@pytest.mark.asyncio
async def test_event_triggers_emit(emit_event):
    p = MynamePlugin(emit_event=emit_event)
    await p.on_ws_event({"event": "some_event", "channel": "#c", "data": {...}})
    emit_event.assert_awaited_once_with("myevent", "#c", {...})
```

跑测试：

```bash
cd zchat-channel-server
uv run pytest tests/unit/test_<name>_plugin.py -v
```

E2E 测试放 `zchat-channel-server/tests/e2e/`，走起一个 CS 进程 + fake bridge 的方式（参考 `test_plugin_pipeline.py`）。

## 10. 常见坑

- **忘了在 `__main__.py` register** → plugin 代码写好但完全不触发（启动日志不报错）。check `registry.all_plugins()` 是否包含自己。
- **handles_commands 返回了已有命令** → CS 启动就崩（`ValueError: command 'resolve' claimed by X but already registered by resolve`，`plugin.py:74-76`）。
- **on_ws_event 里长时间 I/O 阻塞** → 所有后续 plugin 的 event 都被卡住（broadcast_event 是串行 await）。长操作用 `asyncio.create_task()` fire-and-forget。
- **持久化 JSON 忘了 atomic rename** → CS 崩的时候可能留下半截 JSON，重启 `_load` 抛异常然后**悄悄返回空状态**（`audit/plugin.py:56-58`）。永远走 write-to-tmp + rename。
- **Plugin 里 `import` 其它 plugin 模块** → 红线违例。需要引用走 `__main__.py` DI。
- **emit_event 的第一个参数搞反** → `emit_event(channel, event_name, data)` 是错的；正确是 `emit_event(event_name, channel, data)`（参见所有现有 plugin 的调用）。

## 关联

- 架构总览：`001-architecture.md` §3 plugins 表
- 事件语义与场景：`003-e2e-pre-release-test.md` TC-PR-2.5 / CSAT
- 红线原则：`005-dev-guide.md` 总则 + Q4 / Q11
- 协议层：`zchat-protocol/zchat_protocol/ws_messages.py`（event build/parse）
