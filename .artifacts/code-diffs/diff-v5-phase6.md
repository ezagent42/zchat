---
type: code-diff
id: code-diff-v5-phase6
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 6
related:
  - eval-doc-010
  - test-plan-011
  - test-diff-v5-phase6
spec: docs/spec/channel-server-v5.md §6, §10.1, §12 红线 2
plan: docs/discuss/plan/v5-refactor-plan.md §Phase-6
---

# Code Diff: V5 Phase 6 — bridge 去跨层 + lazy create

## 改动摘要

bridge 删除对 `channel_server.routing` 的 import，改用 `feishu_bridge/routing_reader.py` 通过 `tomllib` 直读 `routing.toml`。`bot_added` 事件触发 subprocess CLI 懒创建 channel + agent。`disbanded` 事件触发 `channel remove --stop-agents`。

## 文件清单

**新增（CS / feishu_bridge）：**
- `src/feishu_bridge/routing_reader.py` — `read_bridge_mappings(path, bot_id)` + `reverse_mapping`

**修改（CS / feishu_bridge）：**
- `src/feishu_bridge/bridge.py` — 删跨层 import；`_on_bot_added` 实现懒创建；`_on_disbanded` 调 `channel remove`；`_run_cli` async subprocess
- `src/feishu_bridge/config.py` — `BridgeConfig` 加 `routing_path` 等字段

## 关键 diff（routing_reader.py）

```python
import tomllib
def read_bridge_mappings(routing_path: Path, bot_id: str) -> dict[str, str]:
    """external_chat_id → channel_id（仅本 bot_id 负责的）。"""
    if not routing_path.exists(): return {}
    data = tomllib.loads(routing_path.read_text())
    result = {}
    for ch_id, ch in (data.get("channels") or {}).items():
        if ch.get("bot_id") == bot_id and ch.get("external_chat_id"):
            result[ch["external_chat_id"]] = ch_id
    return result
```

## 关键 diff（bridge.py 懒创建）

```python
async def _create_channel_and_agent(self, channel_id, chat_id):
    await self._run_cli("channel", "create", channel_id,
                        "--external-chat", chat_id,
                        "--bot-id", self.config.bot_id)
    agent_name = f"{channel_id}-agent"
    await self._run_cli("agent", "create", agent_name,
                        "--type", self.config.entry_agent_template,
                        "--channel", channel_id)
```

## 验收

- 红线 grep：`grep -r "from channel_server" src/feishu_bridge/` 仅 docstring 提及
- unit: tests/unit/test_routing_reader.py
- e2e: tests/e2e/test_bridge_lazy_create.py（mock subprocess）
