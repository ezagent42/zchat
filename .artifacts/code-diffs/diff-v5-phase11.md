---
type: code-diff
id: code-diff-v5-phase11
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 11
related:
  - eval-doc-010
  - test-plan-011
  - test-diff-v5-phase11
spec: docs/spec/channel-server-v5.md §8.2, §10.7
plan: docs/discuss/plan/v5-refactor-plan.md §Phase-11
---

# Code Diff: V5 Phase 11 — admin-agent 命令完整实现

## 改动摘要

admin-agent / squad-agent soul.md 三命令完整化，全部走 `run_zchat_cli`。所有 5 个 start.sh 白名单加 `mcp__zchat-agent-mcp__run_zchat_cli`。

## 文件清单

**修改（zchat 主仓 templates）：**
- `zchat/cli/templates/admin-agent/soul.md` — 完整命令处理章节（/status /review /dispatch）
- `zchat/cli/templates/squad-agent/soul.md` — squad 协同 + run_zchat_cli 用法
- `zchat/cli/templates/admin-agent/start.sh` — settings.local.json 白名单
- `zchat/cli/templates/deep-agent/start.sh` — 同上
- `zchat/cli/templates/fast-agent/start.sh` — 同上
- `zchat/cli/templates/squad-agent/start.sh` — 同上
- `zchat/cli/templates/claude/start.sh` — 同上

## admin-agent 命令路径

```
/status                       → run_zchat_cli(["audit","status","--json"])
/review                       → run_zchat_cli(["audit","report","--json"])
/dispatch <type> <channel>    → run_zchat_cli(["agent","create",<nick>,"--type",<type>,"--channel",<channel>])
```

## start.sh 白名单（每个 5 文件）

```json
"permissions": {"allow": [
  "mcp__zchat-agent-mcp__reply",
  "mcp__zchat-agent-mcp__join_channel",
  "mcp__zchat-agent-mcp__run_zchat_cli"
]}
```

## 验收

- e2e: tests/e2e/test_admin_commands_via_cli.py — 5 测试覆盖
  - test_status_command_mapping
  - test_review_command_mapping
  - test_dispatch_command_args_parse
  - test_channel_list_command
  - test_soul_md_only_references_existing_tools
  - test_all_start_sh_whitelist_existing_tools
