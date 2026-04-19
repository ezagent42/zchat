---
type: test-diff
id: test-diff-v5-phase2
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 2
related: [eval-doc-010, test-plan-011, code-diff-v5-phase2]
---

# Test Diff: V5 Phase 2

## 新增文件

- `tests/e2e/test_admin_commands_via_cli.py` 中加 case：
  - `test_soul_md_only_references_existing_tools` — TC-V5-2.1
  - `test_all_start_sh_whitelist_existing_tools` — TC-V5-2.2

## 校验

- 4 个 soul.md 不含 `send_side_message / query_status / query_review / query_squad / assign_agent / reassign_agent`
- 5 个 start.sh 不含 `mcp__zchat-agent-mcp__send_side_message`
- 5 个 start.sh 都含 `reply / join_channel / run_zchat_cli`

## 跑分

e2e 通过。
