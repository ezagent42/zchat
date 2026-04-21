# V5 重构计划

> 2026-04-20 · 基于 `docs/spec/channel-server-v5.md` + 代码现状审阅 + PRD 对齐

## 0. 现状诊断（摘要）

代码现状审阅发现三类问题（详见 session Part 1-8 审阅报告）：

**A 类：1f1233c commit 留下的悬空引用（无设计争议）：**
- `commands/` 目录被删但 `start.sh:24-27` 仍尝试复制
- `join_channel` MCP tool 被删但 5 个 start.sh 的 settings.json 仍白名单它
- `send_side_message` tool 被删但 fast-agent soul.md:10,18 仍引用
- `/close` 命令被删（lifecycle plugin），无 plugin 接管
- auto-hijack 被删但检测函数 `is_operator_in_customer_chat` 和其测试仍在
- bridge `_processed_msg_ids` 无边界增长（内存泄漏）
- bridge 配置 `agent_nick_pattern` 读入但未使用

**B 类：soul.md 引用不存在的 tool：**
- fast-agent: `send_side_message`
- admin-agent 前半：`query_status() / query_review() / assign_agent()` tool（不存在）
- squad-agent: `query_squad() / assign_agent() / reassign_agent()` tool（不存在）

**C 类：Spec 要求但代码没有：**
- `entry_agent` 字段（router 实际遍历所有 agent 各 @ 一次）
- `bot_id` 字段（当前 routing 表无此字段，bridge 跨层 import CS routing）
- CS watch routing.toml
- emit_event 发 IRC `__zchat_sys:` + agent 感知
- bridge bot_added → CLI 懒创建
- audit plugin（被删，admin `/review` 无数据源）
- activation plugin（被删，客户回访无法检测）
- CSAT 完整链路（bridge 有收分逻辑但 CS 端缺 csat plugin）
- sla 求助 timer（只有 takeover timer）
- admin-agent 的 `/status /review /dispatch` 实现

## 1. 重构原则

1. 不破坏 V4 已正确实现的（mode/sla/resolve plugin 核心逻辑、router 分派、bridge 的 parsers/renderer/card_action）
2. 每 Phase 可验证，走 dev-loop 五步（eval-doc → test-plan → test-diff → code-diff → e2e-report）
3. Phase 结束跑 ralph-loop 扫残留（死代码 / 跨层 import / 悬空引用）
4. 所有测试通过零跳过零错误
5. 证据链存 `.artifacts/`（skill-6 注册）

## 2. Phase 列表（共 11 个）

### Phase 1: A 类清理（P0，无设计争议）

**1.1 恢复 `commands/` 目录**（4 文件，从 git `1f1233c~1` 恢复并更新）

- `commands/reply.md` → 调 `reply` tool
- `commands/dm.md` → 调 `reply` tool（chat_id 不带 #）
- `commands/join.md` → 调 `join_channel` tool（Phase 1.2 恢复后）
- `commands/broadcast.md` → 循环调 `reply`

**1.2 恢复 `join_channel` MCP tool**

在 `agent_mcp.py:register_tools()` 加回来。handler: `connection.join(f"#{channel_name}")`。

**1.3 删除 auto-hijack 死代码**

- 删 `group_manager.is_operator_in_customer_chat` 方法
- 删 `tests/unit/test_group_manager.py` 对应测试
- grep 验证无调用点

**1.4 bridge 内存泄漏修复**

`bridge._processed_msg_ids` 用 `collections.deque(maxlen=10000)` 替换 `set`，或加 TTL 清理。

**1.5 删除未用的 `agent_nick_pattern`**

- 删 `bridge.py:95-97` 读取代码
- 删 `config.py` 字段定义
- grep 验证

**验收**：
- 全量测试通过
- `ls zchat-channel-server/commands/` 有 4 个 .md
- `grep -r "is_operator_in_customer_chat"` 无匹配
- `grep -r "agent_nick_pattern"` 无匹配
- 主库测试 + channel-server 测试全通过
- start.sh 能正常 exec claude（commands 复制不报错）

### Phase 2: soul.md 对齐已有 tool（P0）

**2.1 fast-agent/soul.md**

- 删 `send_side_message(@deep-agent)` 描述
- 改为 `reply(chat_id="#<channel>", text="@deep-agent 请分析: ... msg_id=<placeholder_uuid>", side=true)`

**2.2 admin-agent/soul.md**

- 删第 11-33 行对 `query_status() tool / query_review() tool / assign_agent() tool` 的引用
- 统一改为 `run_zchat_cli` 约定：
  - `/status` → `run_zchat_cli(["audit", "status"])`
  - `/review` → `run_zchat_cli(["audit", "report"])`
  - `/dispatch <agent> <channel>` → `run_zchat_cli(["agent", "create", <nick>, "--type", <agent-type>, "--channel", <channel>])`
- 保留 `f574a4d` 加的"命令处理约定"章节

**2.3 squad-agent/soul.md**

- 删 `query_squad() / assign_agent() / reassign_agent()` tool 引用
- 改为：squad-agent 在 `#squad-xxx` 里和 operator 聊天，处理管理指令。可用 `run_zchat_cli` 执行具体操作

**2.4 instructions.md**

- 确认列出 `reply / join_channel / run_zchat_cli` 三个 tool
- 新增说明：`__zchat_sys:` 事件会作为 system 消息注入 Claude（为 Phase 5 铺路）

**验收**：
- 全量测试通过
- `grep -rE "(send_side_message|query_status|query_review|query_squad|assign_agent|reassign_agent)\(\)" zchat/cli/templates/` 无匹配
- 4 个 soul.md 只引用 `reply | join_channel | run_zchat_cli`

### Phase 3: routing.toml Schema + entry_agent + CLI 扩展

**3.1 `src/channel_server/routing.py`**

```python
@dataclass
class ChannelRoute:
    channel_id: str
    external_chat_id: str | None = None
    bot_id: str | None = None
    entry_agent: str | None = None
    agents: dict[str, str] = field(default_factory=dict)
    role_map: dict[str, str] = field(default_factory=dict)  # 可选

# RoutingTable 新增方法
def entry_agent(self, channel_id: str) -> str | None:
    ch = self.channels.get(channel_id)
    return ch.entry_agent if ch else None
```

load() 解析新字段。向后兼容：无 `entry_agent` 字段的条目降级为 `None`（router 会 log warning）。

**3.2 `src/channel_server/router.py` 改 `_route_to_irc`**

```python
entry = self._routing.entry_agent(channel)
if mode in ("copilot", "auto"):
    if entry:
        self._irc.privmsg(irc_channel, f"@{entry} {encoded}")
    else:
        log.warning("channel %s has no entry_agent", channel)
else:  # takeover
    self._irc.privmsg(irc_channel, encoded)
```

**3.3 `zchat/cli/routing.py` 支持新字段**

- `add_channel` 接受 `entry_agent`, `bot_id`
- `join_agent` 首次加入 channel（agents 为空）自动设为 entry_agent
- 新方法 `set_entry_agent(channel, nick)`
- 新方法 `remove_channel(channel)`

**3.4 `zchat/cli/app.py` CLI 扩展**

- `zchat channel create <name>` 加 `--entry-agent` `--bot-id` 选项
- `zchat channel remove <name> [--stop-agents]`（新命令）
  - 删除 routing.toml 条目
  - `--stop-agents` 时停掉此 channel 所有 agent 进程
- `zchat channel set-entry <channel> <nick>`（新命令）

**3.5 测试**

- `test_routing.py`: ChannelRoute 字段解析；向后兼容无 entry_agent 的老格式
- `test_router.py`: 只 @ entry_agent；无 entry_agent 时 warning；takeover 不加 @
- `test_routing_cli.py`: --entry-agent --bot-id 写入；remove 清理；set-entry 修改
- `test_channel_cmd.py`: 新 CLI 命令行为

**验收**：
- 全量测试通过
- `router._route_to_irc` 在 copilot 下只发 1 条 IRC（不遍历所有 agent）
- `zchat channel remove` 能清理 routing.toml 条目
- routing.toml 新格式支持 bot_id / entry_agent 字段

### Phase 4: CS watch routing.toml + auto reload

**4.1 新增 `src/channel_server/routing_watcher.py`**

```python
async def watch_routing(path, router, irc_conn, interval=2.0):
    """轮询 mtime，变化则 reload + JOIN/PART 差异 channel。"""
    last_mtime = path.stat().st_mtime if path.exists() else 0
    last_channels = set(router._routing.channels.keys())
    while True:
        await asyncio.sleep(interval)
        try:
            mtime = path.stat().st_mtime if path.exists() else 0
            if mtime == last_mtime:
                continue
            last_mtime = mtime
            new_routing = load_routing(path)
            router.update_routing(new_routing)
            new_channels = set(new_routing.channels.keys())
            for ch in new_channels - last_channels:
                irc_conn.join(f"#{ch}")
            for ch in last_channels - new_channels:
                irc_conn.part(f"#{ch}")
            last_channels = new_channels
        except Exception:
            log.exception("watch routing reload error")
```

**4.2 Router 加 `update_routing(new_table)`**

```python
def update_routing(self, new_routing: RoutingTable) -> None:
    self._routing = new_routing
```

**4.3 IRCConnection 加 `part(channel)`**

如果没有的话。

**4.4 `__main__.py` 启动 watcher task**

```python
watcher_task = asyncio.create_task(
    watch_routing(Path(routing_path), router, irc_conn)
)
```

**4.5 测试**

- `test_routing_watcher.py`: mock file mtime 变化 + load 调用 + JOIN/PART 差异触发
- 可选 e2e：启动 CS → 修改 routing.toml → 2 秒内观察 IRC JOIN

**验收**：
- 修改 routing.toml 后 2 秒内 CS 自动 reload
- 新 channel 自动 JOIN，删除的 channel 自动 PART
- 测试覆盖 mtime 不变、新增、删除、修改 entry_agent 四种场景

### Phase 5: emit_event 发 IRC sys 消息 + agent 感知

**5.1 `router.emit_event` 加 IRC 分支**

```python
async def emit_event(self, channel: str, event: str, data: dict | None = None) -> None:
    msg = ws_messages.build_event(channel, event, data or {})
    await self._ws.broadcast(msg)
    await self._registry.broadcast_event(msg)
    if channel:
        try:
            payload = irc_encoding.make_sys_payload(
                nick="cs-bot", sys_type=event, body=data or {},
            )
            self._irc.privmsg(f"#{channel}", irc_encoding.encode_sys(payload))
        except Exception:
            log.exception("irc sys broadcast failed")
```

**5.2 `agent_mcp.py` 支持 sys 消息注入**

```python
def _on_pubmsg(conn, event):
    body = event.arguments[0]
    parsed = irc_encoding.parse(body)
    if parsed["kind"] == "sys":
        # 注入 system event 到 Claude
        msg = {
            "id": os.urandom(4).hex(),
            "nick": event.source.nick,
            "type": "sys",
            "body": parsed["payload"],
            "ts": time.time(),
        }
        loop.call_soon_threadsafe(queue.put_nowait, (msg, event.target))
        return
    # 原有 @mention 逻辑不变
    ...
```

`inject_message` 对 type="sys" 的消息加特殊标记（notification content 前缀 `[system event] `）。

**5.3 测试**

- `test_router.py`: emit_event 同时触发 WS broadcast + plugin broadcast + IRC sys
- `test_agent_mcp.py`: sys 消息识别 + 注入 queue + 不触发 @mention 死循环

**验收**：
- /hijack 后 agent 能从 inject queue 看到 mode_changed sys 消息
- sys 消息不会被 detect_mention 误匹配（avoid infinite loop）

### Phase 6: bridge 去跨层 + lazy create

**6.1 新增 `src/feishu_bridge/routing_reader.py`**

```python
import tomllib
from pathlib import Path

def read_bridge_mappings(routing_path: Path, bot_id: str) -> dict[str, str]:
    """external_chat_id → channel_id 映射（本 bot_id 负责的）。"""
    if not routing_path.exists():
        return {}
    with open(routing_path, "rb") as f:
        data = tomllib.load(f)
    result = {}
    for channel_id, ch in (data.get("channels") or {}).items():
        if ch.get("bot_id") == bot_id and ch.get("external_chat_id"):
            result[ch["external_chat_id"]] = channel_id
    return result

def reverse_mapping(m: dict[str, str]) -> dict[str, str]:
    return {v: k for k, v in m.items()}
```

**6.2 `bridge.py` 删跨层 import**

- 删 `from channel_server.routing import load as load_routing`
- `_load_channel_chat_map` 改用 `routing_reader.read_bridge_mappings`
- GroupManager 的 channel_chat_map 参数保留（或 bridge 内部管理）

**6.3 bridge config 扩展**

`config.py` 加字段：

```python
@dataclass
class BridgeBotConfig:
    bot_id: str                     # 飞书 app_id
    entry_agent_template: str       # 新群用什么模板
    channel_prefix: str             # 新 channel_id 前缀
    routing_path: str               # routing.toml 路径
```

**6.4 `bridge._on_bot_added` 实现懒创建**

```python
def _on_bot_added(self, data):
    chat_id = data.event.chat_id
    existing = routing_reader.read_bridge_mappings(self.config.routing_path, self.config.bot_id)
    if chat_id in existing:
        return  # 已有映射
    # 生成 channel_id
    suffix = chat_id[3:11] if len(chat_id) >= 11 else chat_id
    channel_id = f"{self.config.channel_prefix}{suffix}"
    asyncio.create_task(self._create_channel_and_agent(channel_id, chat_id))

async def _create_channel_and_agent(self, channel_id, chat_id):
    # 第一步：创建 channel + 初始 agent
    agent_name = f"{channel_id}-agent"
    await self._run_cli(
        "channel", "create", channel_id,
        "--external-chat", chat_id,
        "--bot-id", self.config.bot_id,
    )
    await self._run_cli(
        "agent", "create", agent_name,
        "--type", self.config.entry_agent_template,
        "--channel", channel_id,
    )
    # GroupManager 保留 register_customer_chat（用于权限/角色识别）
    self.group_manager.register_customer_chat(chat_id)

async def _run_cli(self, *args):
    proc = await asyncio.create_subprocess_exec(
        "zchat", *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        log.error("zchat %s failed: %s", args, stderr.decode())
```

**6.5 `bridge._on_disbanded` 清理路径**

```python
def _on_disbanded(self, data):
    chat_id = data.event.chat_id
    mappings = routing_reader.read_bridge_mappings(self.config.routing_path, self.config.bot_id)
    channel_id = routing_reader.reverse_mapping(mappings).get(chat_id)
    if channel_id:
        asyncio.create_task(self._run_cli("channel", "remove", channel_id, "--stop-agents"))
    self.group_manager.on_group_disbanded(chat_id)
```

**6.6 测试**

- `test_routing_reader.py`: 多 bot_id 过滤；空文件；格式错误
- `test_bridge.py`: mock subprocess，bot_added 调 CLI；disbanded 调 channel remove

**验收**：
- `grep "channel_server" src/feishu_bridge/` 无匹配（除注释外）
- 拉 bot 进新飞书群，日志显示两次 `zchat` subprocess 调用
- `chat.disbanded` 事件触发 `zchat channel remove`

### Phase 7: 恢复 audit + activation plugin（基础版）

**7.1 恢复 audit plugin（简化版）**

从 commit `1f1233c~1:src/plugins/audit/plugin.py` 参考，重写：

```python
class AuditPlugin(BasePlugin):
    name = "audit"
    
    def __init__(self, persist_path: Path):
        self._path = persist_path
        self._state = self._load()  # {channels: {...}, aggregates: {...}}
    
    async def on_ws_event(self, event):
        if event.get("event") == "mode_changed":
            self._record_mode_change(event)
        elif event.get("event") == "channel_resolved":
            self._record_resolve(event)
        self._save()
    
    def query(self, key, args=None):
        if key == "status":
            return self._build_status(args.get("channel") if args else None)
        if key == "report":
            return self._build_report()
```

持久化格式：`audit.json`，schema 见 spec §4.2。

**7.2 恢复 activation plugin**

从 commit `1f1233c~1:src/plugins/activation/plugin.py` 参考。简化：仅监听消息 + emit `customer_returned`，不决策。持久化 `activation-state.json`。

**7.3 `__main__.py` 注册**

```python
from plugins.audit.plugin import AuditPlugin
from plugins.activation.plugin import ActivationPlugin

registry.register(AuditPlugin(persist_path=project_dir / "audit.json"))
registry.register(ActivationPlugin(
    state_file=project_dir / "activation-state.json",
    emit_event=emit_event,
))
```

**7.4 测试**

- 恢复 `tests/unit/test_audit_plugin.py` + 加 JSON 持久化测试
- 恢复 `tests/unit/test_activation_plugin.py`

**验收**：
- audit 记录 mode_changed / channel_resolved 事件
- activation 检测客户回访 emit `customer_returned`
- 持久化 JSON 文件可见

### Phase 8: audit 扩展 — 仪表盘 6 指标（满足 US-3.1 + US-3.2）

**8.1 audit plugin 扩展追踪维度**

每个 channel 新增字段：

```json
{
  "state": "active|takeover|resolved",
  "created_at": "...",
  "first_message_at": "...",
  "first_reply_at": "...",           // agent 首次回复时间（on_ws_message 检测 agent nick 发言）
  "takeovers": [
    {
      "at": "...",
      "triggered_by": "operator",
      "first_operator_reply_at": "...",  // takeover 后 operator 首次发言（接单等待）
      "released_at": "...",
      "released_by": "operator|sla_timeout"
    }
  ],
  "resolved_at": null,
  "message_count": 0,
  "csat_score": null
}
```

Aggregates：

```json
{
  "total_takeovers": 42,
  "total_resolved": 38,
  "escalation_resolve_rate": 0.89,
  "avg_first_reply_seconds": 2.3,
  "avg_session_duration_seconds": 420,
  "avg_pickup_wait_seconds": 45,
  "csat_mean": 4.6
}
```

**8.2 audit 新 query key**

- `status` → 全局聚合（aggregates + active channels 列表）
- `status(channel=X)` → 单 channel 详情
- `report(since=T)` → 时间窗口内的数据 summary

**8.3 audit CLI**

新增 `zchat/cli/audit_cmd.py`：

```python
@audit_app.command("status")
def cmd_audit_status(channel: Optional[str] = None):
    """读 audit.json 返回格式化状态。"""
    # 直接读 JSON 文件，不走 CS

@audit_app.command("report")
def cmd_audit_report(since: Optional[str] = "yesterday"):
    """读 audit.json 返回报告。"""
```

**8.4 admin-agent soul.md 对接**

```
/status   → run_zchat_cli(["audit", "status"])
/review   → run_zchat_cli(["audit", "report"])
/dispatch → run_zchat_cli(["agent", "create", ..., "--channel", ...])
```

**8.5 测试**

- audit 跟踪 first_reply / takeover 时间戳
- CLI `zchat audit status` / `report` 输出格式
- admin-agent 执行 `/status` 返回活跃对话列表

**验收**：
- 模拟完整对话流程后，audit.json 有完整 6 维度数据
- `zchat audit status` 返回 active channels
- `zchat audit report` 返回聚合指标

### Phase 9: CSAT plugin

**9.1 新增 `src/plugins/csat/plugin.py`**

```python
class CsatPlugin(BasePlugin):
    name = "csat"
    
    def __init__(self, emit_event, audit_plugin=None):
        self._emit_event = emit_event
        self._audit = audit_plugin  # 用于写 score 回 audit.json
    
    async def on_ws_event(self, event):
        if event.get("event") == "channel_resolved":
            channel = event.get("channel")
            # 触发 bridge 发评分卡片
            await self._emit_event("csat_request", channel, {})
            # 注意：csat_request 是"事件"而非 message
            # bridge.py 已有 _handle_csat_request 监听 type="csat_request"
    
    async def on_ws_message(self, msg):
        # bridge 从 card action 转来的: content == "__csat_score:N"
        content = msg.get("content", "")
        if content.startswith("__csat_score:"):
            try:
                score = int(content.split(":", 1)[1])
            except (ValueError, IndexError):
                return
            channel = msg.get("channel")
            if self._audit:
                self._audit.record_csat(channel, score)
            # emit 通知其他 plugin
```

**9.2 bridge.py 确认 csat_request 处理路径**

当前代码（`bridge.py:387-399`）监听 `type="csat_request"` 的 WS 消息。但 csat plugin emit 的是 event。需要调整：

方案：csat plugin emit event → CS `emit_event` 同时 WS broadcast → bridge 的 `_on_bridge_event` 对 event 字段做匹配：

```python
# bridge._on_bridge_event
if msg.get("type") == "event" and msg.get("event") == "csat_request":
    self._handle_csat_request(channel, msg)
```

**9.3 `__main__.py` 注册 csat plugin**

```python
from plugins.csat.plugin import CsatPlugin
csat = CsatPlugin(emit_event=emit_event, audit_plugin=audit_plugin)
registry.register(csat)
```

**9.4 测试**

- channel_resolved → csat 发 csat_request event
- 接收 `__csat_score:N` → 记录到 audit
- 端到端（mock bridge）：resolve → csat_request → card.action → score → audit.csat_score 更新

**验收**：
- resolve 后 bridge 能触发 CSAT 卡片（通过 event 路径）
- 客户评分记录到 audit.json

### Phase 10: sla 扩展 — 求助 timer（US-2.5）

**10.1 sla plugin 订阅 `on_ws_message` 检测求助 pattern**

```python
HELP_MENTION_PATTERNS = ["@operator", "@人工", "@admin"]

class SlaPlugin(BasePlugin):
    # 已有：takeover timer
    
    async def on_ws_message(self, msg):
        content = msg.get("content", "")
        channel = msg.get("channel", "")
        parsed = irc_encoding.parse(content)
        if parsed.get("kind") != "side":
            return
        text = parsed.get("text", "")
        if any(p in text for p in HELP_MENTION_PATTERNS):
            # agent 发起求助
            self._start_help_timer(channel)
        else:
            # 检测到 operator 在该 channel 的 side 消息（回应求助）
            source = msg.get("source", "")
            if "operator" in source.lower() or source.startswith("ou_"):
                self._cancel_help_timer(channel)
    
    async def _start_help_timer(self, channel):
        self._cancel_help_timer(channel)
        task = asyncio.create_task(self._help_timeout_task(channel))
        self._help_timers[channel] = task
    
    async def _help_timeout_task(self, channel):
        try:
            await asyncio.sleep(self._help_timeout_seconds)
        except asyncio.CancelledError:
            return
        # 超时 emit 事件（agent 通过 sys 消息感知，发安抚消息）
        await self._emit_event("help_timeout", channel, {
            "reason": "operator_no_response",
            "timeout_seconds": self._help_timeout_seconds,
        })
```

**10.2 fast-agent soul.md 扩展**

收到 `__zchat_sys:help_timeout` 注入时，按指导发客户安抚消息：

```
reply(text="抱歉让您久等，我继续为您服务...")
```

**10.3 测试**

- `test_sla_plugin.py`: 检测 side 中的 @operator pattern 启动 timer
- operator 回复（相同 channel 内的 side 消息）取消 timer
- 超时 emit help_timeout event
- 不影响已有 takeover timer 逻辑

**验收**：
- agent 发 `reply(side=true, text="@operator ...")` → sla 启动 timer
- 180s 无 operator 响应 → emit help_timeout → agent 发安抚消息
- 已有 takeover timer 功能完好

### Phase 11: admin-agent 命令完整实现

**11.1 admin-agent/soul.md 完整重写**

明确三个命令的处理流程：

```markdown
## 命令处理

### /status
1. 调用 run_zchat_cli(["audit", "status"])
2. 解析返回的 JSON（active channels + aggregates）
3. 格式化为易读文本，reply 到管理群

示例输出：
当前进行中对话：3 个
- conv-abc123: copilot 模式，已进行 5 分钟，消息 12 条
- conv-def456: takeover 中（operator: 小李），已 30s
- conv-xyz789: copilot，等待 agent 回复

### /review [yesterday|today|week]
1. run_zchat_cli(["audit", "report", "--since", <time>])
2. 格式化接管数 / CSAT 均值 / 升级转结案率 / SLA 达成率
3. reply

### /dispatch <agent-type> <channel-id>
1. 生成 agent nick（username + channel suffix）
2. run_zchat_cli(["agent", "create", <nick>, "--type", <agent-type>, "--channel", <channel-id>])
3. reply 执行结果
```

**11.2 squad-agent/soul.md 重写**

```markdown
# Squad Agent

职责：在客服分队群内与 operator 协同。

操作者可能发：
- 自然语言询问：`当前有几个等待接管？` → run_zchat_cli(["audit", "status"])
- 派发指令：`派 deep-agent 到 conv-xxx` → run_zchat_cli(["agent", "create", ..., "--channel", ...])
- 查看分队：`/squad` → run_zchat_cli(["agent", "list"])

squad-agent 不参与客户对话（客户 channel 里是 fast-agent/deep-agent）。
```

**11.3 完整 e2e 场景测试（手动或脚本）**

- 管理员在飞书管理群发 `/status` → 客户看到实时对话列表
- 管理员发 `/review` → 看到昨日报告
- 管理员发 `/dispatch deep-agent conv-xxx` → deep-agent 加入该 channel

**验收**：
- 三个 admin 命令通过 run_zchat_cli 实现
- admin-agent soul.md 无残留不存在的 tool 引用

## 3. 并行分组

```
Phase 1 (A 类清理, 0.5d)              ─┐
Phase 2 (soul.md 对齐, 0.3d)          ─┤ 可并行
                                       │
Phase 3 (entry_agent, 1d) ─────────────┤  C 类关键
  │                                    │
  ├─→ Phase 4 (watch, 0.5d) ───────────┤
  │                                    │
  ├─→ Phase 5 (IRC sys, 0.5d)─────────┤
  │                                    │
  ├─→ Phase 6 (bridge lazy, 1d)───────┘
  │   (依赖 Phase 3 的 --bot-id 写入)
  │
Phase 7 (audit/activation 基础, 0.5d) —— 独立
Phase 8 (audit 扩展, 1d) —— 依赖 Phase 7
Phase 9 (csat, 0.5d) —— 依赖 Phase 8（audit.record_csat）
Phase 10 (sla 求助 timer, 0.5d) —— 独立
Phase 11 (admin-agent 命令, 0.5d) —— 依赖 Phase 8（audit CLI）
```

**总预估：6.5 人/天**

执行顺序：
- 第 1 轮并行：Phase 1 + Phase 2（都是清理）
- 第 2 轮：Phase 3
- 第 3 轮并行：Phase 4 + Phase 5 + Phase 7 + Phase 10
- 第 4 轮：Phase 6 + Phase 8
- 第 5 轮并行：Phase 9 + Phase 11

## 4. Dev-loop 证据链

每 Phase 必须产出（用 skill-6 注册）：

1. `eval-doc`（Phase 前）：描述预期效果 + testcase 表
2. `test-plan`（Phase 前）：TC-ID + 优先级 + source
3. `test-diff`（Phase 中）：test-plan → pytest 代码
4. `code-diff`（Phase 中）：实现改动
5. `e2e-report`（Phase 后）：全量测试 + 证据

## 5. Ralph-loop 红线检查（每 Phase 后）

```bash
# 跨层 import 检查
grep -r "from channel_server" zchat-channel-server/src/feishu_bridge/  # 应无匹配
grep -r "from feishu_bridge" zchat-channel-server/src/channel_server/   # 应无匹配

# 业务语义泄漏检查
grep -rE "(admin|squad|customer)" zchat-channel-server/src/channel_server/  # 应无匹配（注释除外）

# 死代码检查
grep -rE "is_operator_in_customer_chat|agent_nick_pattern|send_side_message|query_status|query_review|assign_agent|reassign_agent|query_squad" \
    zchat-channel-server/src/ zchat/cli/  # 应无调用点

# 悬空引用检查
# start.sh 引用的所有 MCP tool 必须存在
# soul.md 引用的所有 tool 必须存在
```

## 6. 验收标准（全局）

### 6.1 Unit / 单元层验收

| US | 场景 | 需要工作 | 验证点 |
|----|-----|---------|--------|
| US-2.1 | 3s 问候 | Phase 6（懒创建）+ Phase 3（entry_agent） | 单元测试 + 飞书真机 |
| US-2.2 | 占位 + 编辑 | 现有 `__msg:` + `__edit:` 已支持 | 单元测试 + 飞书 update_message 验证 |
| US-2.3 | 客服群卡片 + thread | bridge 已实现 | 飞书真机：卡片出现 + thread 镜像 |
| US-2.5 | Agent 求助 + 180s timer | Phase 10 | 单元 + 飞书真机 |
| US-2.5 | /hijack | Phase 5（IRC sys 通知 agent） | 单元 + 飞书真机卡片按钮 |
| US-3.1 | 仪表盘数据 | Phase 7 + Phase 8 | CLI + 数据正确性 |
| US-3.2 | /status /review /dispatch | Phase 8 + Phase 11 | 飞书真机管理群 |
| CSAT | 评分闭环 | Phase 9 | 飞书真机：评分卡 → 分数入库 |
| 老客户回访 | activation 事件 | Phase 7 | 模拟已关闭 channel 再发消息 |
| routing.toml 动态变更 | CS 自动 reload | Phase 4 | 手动改文件 → CS log 验证 |

### 6.2 代码层断言

- 所有 unit + integration 测试通过零跳过零错误
- 跨层 import 检查无匹配（见 §5）
- 死代码检查无匹配（见 §5）
- 所有 start.sh 引用的 tool 实际存在
- 所有 soul.md 只引用 `reply / join_channel / run_zchat_cli`
- bridge 能通过 tomllib 独立读 routing.toml
- routing.toml 写入者唯一为 CLI

### 6.3 飞书 SDK 连通性验收（pre-release 必测）

**6.3.1 SDK 凭证与基础连接**

- [ ] 飞书 `app_id` 和 `app_secret` 通过 `.feishu-credentials.json` 或环境变量加载
- [ ] `lark_oapi.Client` 能成功初始化（不报 auth 错误）
- [ ] WSS 长连接建立成功：`CardAwareClient.start()` 不阻塞 / 不崩溃
- [ ] 测试：启动 bridge 后 5 秒内日志显示 "Feishu WS connected"

**6.3.2 飞书事件订阅**

针对 5 个事件，逐一在飞书真机触发并验证 bridge 收到：

- [ ] `im.message.receive_v1` — 客户群发消息 → bridge log 显示收到
- [ ] `im.chat.member.bot.added_v1` — 把 bot 拉进新群 → bridge 触发 `_on_bot_added`
- [ ] `im.chat.member.user.added_v1` — 有人加入群 → `on_member_added`
- [ ] `im.chat.member.user.deleted_v1` — 有人退群 → `on_member_removed`
- [ ] `im.chat.disbanded_v1` — 解散群 → `_on_disbanded`
- [ ] `card.action.trigger` — 点击卡片按钮 → `_on_card_action`

**6.3.3 飞书 API 调用（出站）**

- [ ] `sender.send_text(chat_id, text)` — 向客户群发文本，客户收到
- [ ] `sender.send_card(chat_id, card)` — 发 interactive card，卡片正确渲染
- [ ] `sender.update_message(msg_id, new_text)` — 编辑已发消息，客户看到内容更新
- [ ] `sender.reply_in_thread(parent_msg_id, text)` — 在 thread 里回复，客服群 thread 出现消息
- [ ] `sender.update_card(msg_id, new_card)` — 更新卡片内容，UI 刷新

**6.3.4 飞书 UI 渲染验证**

- [ ] 客户会话卡片（`build_conv_card`）显示：
  - title 包含对话 ID 和状态
  - mode 元信息正确（fast/copilot/takeover）
  - "接管" 和 "结案" 两个按钮可点击
  - 已结案状态下按钮消失
- [ ] CSAT 卡片（`csat_card`）显示：
  - 5 个星级按钮 ⭐ ~ ⭐⭐⭐⭐⭐ 可点
  - 点击后客户收到反馈
- [ ] 卡片按钮点击：
  - "接管" 按钮 → bridge 发出 `/hijack` → CS mode → takeover → 卡片 UI 更新为 "已接管"
  - "结案" 按钮 → bridge 发出 `/resolve` → CSAT 卡片出现
  - 评分按钮 → 分数进入 audit.json

**6.3.5 完整 PRD 场景真机测试**

按 PRD US 顺序，每条用飞书真机跑：

1. **US-2.1**: 拉 bot 进新飞书群 → 客户发 "你好" → **3 秒内** 客户看到 agent 问候
2. **US-2.2**: 客户问复杂问题 → 客户看到 "稍等..." → 几秒后被替换为完整答复（**一条消息变化**，不是两条）
3. **US-2.3**: 客户群有对话时 → 客服群出现对话卡片 + thread 里镜像每条消息
4. **US-2.5 Agent 求助**: agent 在 side thread @operator → operator 不回应 180s → agent 向客户发安抚 "抱歉让您久等"
5. **US-2.5 /hijack**: operator 点客服群卡片 "接管" → 卡片 UI 变 "已接管" → operator 在客户群直接回复，agent 不再主动回复
6. **US-3.2 /status**: 管理员在管理群发 `/status` → 看到当前对话列表
7. **US-3.2 /dispatch**: 管理员发 `/dispatch deep-agent conv-xxx` → deep-agent 进程被创建 + 加入该 channel（通过 `zchat agent list` 验证）
8. **US-3.2 /review**: 管理员发 `/review` → 看到 takeover 次数 / CSAT / 升级转结案率数字
9. **CSAT 完整**: `/resolve` → 客户群出现评分卡片 → 客户点 4 星 → 分数进 audit.json → `/review` 看到 CSAT=4.0
10. **老客户回访**: 已 resolve 的群客户再发消息 → `customer_returned` event 触发（bridge log 或 admin-agent 通知）
11. **routing 动态**: 手动 `zchat channel create conv-new` → CS log 2 秒内显示 JOIN #conv-new
12. **bridge 懒创建**: 拉 bot 进全新飞书群 → routing.toml 里自动出现新条目 + agent 进程启动

### 6.4 Pre-release 手动测试清单（对应 `tests/pre_release/`）

每个 US 场景在 `tests/pre_release/` 下对应一个 walkthrough 脚本或 markdown checklist。测试前：

1. 启动 ergo IRC server
2. 启动 channel-server
3. 启动 feishu-bridge（真实 `.feishu-credentials.json`）
4. 准备测试飞书账号（至少 1 个客户群、1 个客服群、1 个管理群）
5. 按 §6.3.5 列表逐条执行，记录通过/失败到 `tests/pre_release/evidence/<date>/`

**失败即阻塞**：任何一条失败，不进行后续 Phase，回头修复。

### 6.5 飞书 SDK 降级检测

验证如果飞书不可用 bridge 不崩溃：

- [ ] 网络断开时 bridge 日志显示 WSS 重连尝试
- [ ] 无效凭证启动 bridge → 明确报错，不 crash 整个进程
- [ ] 飞书 API 限流（429）时 bridge 记录 + 重试，不丢消息

## 7. 不做（明确范围外）

| 项 | 原因 |
|---|-----|
| US-1.x 上线向导 | 用户明确不做 |
| US-2.4 草稿机制 | 用户：通过 agent 行为调整，后续 |
| US-2.6 context 带入命令 | 用户：分步做，可通过 operator soul.md 实现，后续可写新命令 |
| US-3.3 5min 滚动平均 | 用户：先不做 |
| US-4.x Dream Engine | 用户明确不做 |
| agent-mcp 改为 WS 连 CS | 保持 IRC 直连，不改架构 |
| bridge per bot_type 多进程 | 单 bridge 进程足够，bot_id 字段区分 |

## 8. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Phase 3 改 router 破坏现有测试 | 全量 baseline 先跑；改完对比；每步小 commit |
| Phase 4 watch 竞态（CS reload 和 agent JOIN 时序）| 幂等 reload；新 channel JOIN 失败不影响旧 |
| Phase 6 bridge subprocess 并发 | CLI 已有原子写 tmp+rename |
| Phase 7 恢复的 plugin 和现有行为冲突 | 逐一启用，跑全量，必要时回退 |
| Phase 8 audit 数据结构变更破坏 JSON | schema 版本字段；升级脚本 |
| Phase 9 CSAT 断链修复影响 bridge 现有代码 | bridge.py:387-389 已有代码保留；只加 CS 侧 plugin |
| Phase 10 sla 求助 pattern 误判（operator 本来就在聊天）| 初版用严格 @operator/@admin/@人 前缀；后续可扩展 |

## 9. 下一步

1. 用户确认本 plan
2. 创建 Phase 1 eval-doc（用 skill-5 simulate 模式）
3. 开始执行 Phase 1
