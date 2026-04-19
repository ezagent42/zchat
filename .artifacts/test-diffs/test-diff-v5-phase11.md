---
type: test-diff
id: test-diff-v5-phase11
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 11
related: [eval-doc-010, test-plan-011, code-diff-v5-phase11]
---

# Test Diff: V5 Phase 11

## 新增文件

- `tests/e2e/test_admin_commands_via_cli.py`（zchat 主仓）

## 关键 case

| 测试 | TC | 验证 |
|------|----|------|
| test_status_command_mapping | TC-V5-11.1 | runner.invoke(app, ["audit","status","--json"]) exit_code 0 + 含 channels/aggregates |
| test_review_command_mapping | TC-V5-11.2 | ["audit","report","--json"] 输出 escalation_resolve_rate / csat_mean |
| test_dispatch_command_args_parse | TC-V5-11.3 | ["agent","create","--help"] 含 --type / --channel |
| test_channel_list_command | TC-V5-11.4 | ["channel","--help"] 含 create/list/remove/set-entry |
| test_soul_md_only_references_existing_tools | TC-V5-2.1 | 4 soul.md 不含死 tool（重复覆盖 Phase 2） |
| test_all_start_sh_whitelist_existing_tools | TC-V5-11.5 | 5 start.sh 白名单含 reply/join_channel/run_zchat_cli |

## 跑分

e2e 通过（fixture populated_audit + monkeypatch CS_DATA_DIR）。
