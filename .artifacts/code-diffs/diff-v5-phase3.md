---
type: code-diff
id: code-diff-v5-phase3
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 3
related:
  - eval-doc-010
  - test-plan-011
  - test-diff-v5-phase3
spec: docs/spec/channel-server-v5.md §2, §3.1, §3.2
plan: docs/discuss/plan/v5-refactor-plan.md §Phase-3
---

# Code Diff: V5 Phase 3 — routing.toml schema + entry_agent + CLI

## 改动摘要

routing 表新增 `entry_agent` / `bot_id` 字段；router 从遍历所有 agent 改为只 @ entry_agent；CLI 加 `channel remove` / `channel set-entry`。

## 文件清单

**修改（CS）：**
- `src/channel_server/routing.py` — `ChannelRoute` 加字段；`RoutingTable.entry_agent(channel_id)` 方法；load() 解析向后兼容
- `src/channel_server/router.py` — `_route_to_irc` 改用 `entry_agent` 路径

**修改（zchat 主仓 CLI）：**
- `zchat/cli/routing.py` — `add_channel(entry_agent, bot_id)`；`set_entry_agent`；`remove_channel`；`join_agent` 首次自动设为 entry
- `zchat/cli/app.py` — `channel create` 加 `--entry-agent --bot-id`；新命令 `channel remove [--stop-agents]` / `channel set-entry`

## 关键 diff（router.py）

```python
entry = self._routing.entry_agent(channel)
if mode in ("copilot", "auto"):
    if entry:
        self._irc.privmsg(irc_channel, f"@{entry} {encoded}")
    else:
        log.warning("[router] channel %r has no entry_agent; message not delivered to any agent", channel)
else:  # takeover
    self._irc.privmsg(irc_channel, encoded)
```

## 关键 diff（routing.py）

```python
@dataclass
class ChannelRoute:
    channel_id: str
    external_chat_id: str | None = None
    bot_id: str | None = None
    entry_agent: str | None = None
    agents: dict[str, str] = field(default_factory=dict)
```

## 验收

- unit: tests/unit/test_routing.py 解析新字段 + 向后兼容
- unit: tests/unit/test_router.py::test_copilot_mode_only_ats_entry_agent
- unit: tests/unit/test_routing_cli.py + test_channel_cmd.py
