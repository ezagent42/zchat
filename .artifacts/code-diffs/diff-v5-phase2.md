---
type: code-diff
id: code-diff-v5-phase2
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 2
related:
  - eval-doc-010
  - test-plan-011
  - test-diff-v5-phase2
spec: docs/spec/channel-server-v5.md §7.3-7.4
plan: docs/discuss/plan/v5-refactor-plan.md §Phase-2
---

# Code Diff: V5 Phase 2 — soul.md 对齐已有 tool

## 改动摘要

4 个 agent 模板的 soul.md 与 start.sh 全部对齐到只引用 3 个真实存在的 MCP tool（reply / join_channel / run_zchat_cli），删除所有指向已删除 tool 的描述。

## 文件清单

**修改（zchat 主仓 templates）：**
- `zchat/cli/templates/fast-agent/soul.md` — 删 `send_side_message(@deep-agent)`，改为 `reply(side=true)`
- `zchat/cli/templates/admin-agent/soul.md` — 删 `query_status / query_review / assign_agent` tool 描述，改为 `run_zchat_cli(["audit","status"])` 等
- `zchat/cli/templates/squad-agent/soul.md` — 删 `query_squad / assign_agent / reassign_agent` 引用
- `zchat/cli/templates/deep-agent/soul.md` — 微调，确认只引用 reply
- `zchat/cli/templates/admin-agent/start.sh` — 白名单加 `mcp__zchat-agent-mcp__run_zchat_cli`
- `zchat/cli/templates/deep-agent/start.sh` — 同上
- `zchat/cli/templates/claude/start.sh` — 同上
- `zchat-channel-server/instructions.md` — 列出 3 tool + 提到 `__zchat_sys:` 注入约定

## 关键约定（admin-agent soul.md）

```
/status   → run_zchat_cli(["audit", "status"])  → 解析 JSON → 格式化
/review   → run_zchat_cli(["audit", "report"])  → 解析 JSON → 格式化
/dispatch → run_zchat_cli(["agent", "create", <nick>, "--type", T, "--channel", C])
```

## 验收

- `grep -rE "(send_side_message|query_status|query_review|query_squad|assign_agent|reassign_agent)\(\)" zchat/cli/templates/` 无匹配
- e2e: tests/e2e/test_admin_commands_via_cli.py::test_soul_md_only_references_existing_tools 通过
- e2e: ::test_all_start_sh_whitelist_existing_tools 通过
