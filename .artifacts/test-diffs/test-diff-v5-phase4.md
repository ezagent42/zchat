---
type: test-diff
id: test-diff-v5-phase4
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 4
related: [eval-doc-010, test-plan-011, code-diff-v5-phase4]
---

# Test Diff: V5 Phase 4

## 新增文件

- `zchat-channel-server/tests/unit/test_routing_watcher.py`

## 关键 case

| 测试 | TC | 验证 |
|------|----|------|
| test_no_change_no_reload | TC-V5-4.1 | mtime 不变 → router 不被调用 |
| test_new_channel_joins_irc | TC-V5-4.2 | 新增 channel → irc.join("#x") |
| test_removed_channel_parts_irc | TC-V5-4.2 | 删除 channel → irc.part("#x") |
| test_reload_exception_does_not_crash | TC-V5-4.3 | 加载异常 watcher 继续 |

## 跑分

unit 全过。
