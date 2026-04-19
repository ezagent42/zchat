---
type: code-diff
id: code-diff-v5-phase1
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 1
related:
  - eval-doc-010
  - test-plan-011
  - test-diff-v5-phase1
spec: docs/spec/channel-server-v5.md §7.3
plan: docs/discuss/plan/v5-refactor-plan.md §Phase-1
---

# Code Diff: V5 Phase 1 — A 类清理

## 改动摘要

恢复 V4 1f1233c 误删的能力；清理无业务争议的死代码。

## 文件清单

**新增（zchat-channel-server）：**
- `commands/reply.md` — `/zchat:reply` slash command
- `commands/dm.md` — `/zchat:dm`
- `commands/join.md` — `/zchat:join`
- `commands/broadcast.md` — `/zchat:broadcast`

**修改（zchat-channel-server）：**
- `agent_mcp.py` — 恢复 `join_channel` MCP tool + handler
- `src/feishu_bridge/bridge.py` — `_processed_msg_ids` 改 `collections.deque(maxlen=10000)` + 配套 `_processed_msg_id_set`
- `src/feishu_bridge/group_manager.py` — 删 `is_operator_in_customer_chat` 死代码
- `src/feishu_bridge/config.py` — 删 `agent_nick_pattern` 字段定义

## 关键 diff

```python
# agent_mcp.py 恢复 join_channel
Tool(name="join_channel",
     description="Join an IRC channel",
     inputSchema={"type": "object",
                  "properties": {"channel_name": {"type": "string"}},
                  "required": ["channel_name"]})

async def _handle_join_channel(state: dict, args: dict) -> str:
    channel = args["channel_name"]
    state["connection"].join(f"#{channel}")
    return f"joined #{channel}"
```

```python
# bridge.py 内存泄漏修复
self._processed_msg_id_queue = deque(maxlen=10000)
self._processed_msg_id_set = set()
def _track_processed(self, msg_id):
    if msg_id in self._processed_msg_id_set: return True
    if len(self._processed_msg_id_queue) == 10000:
        self._processed_msg_id_set.discard(self._processed_msg_id_queue[0])
    self._processed_msg_id_queue.append(msg_id)
    self._processed_msg_id_set.add(msg_id)
    return False
```

## 验收

- `ls commands/` 4 文件
- `grep -r "is_operator_in_customer_chat" src/` 无匹配
- `grep -r "agent_nick_pattern" src/` 无匹配
- unit: tests/unit/test_agent_mcp.py 通过
