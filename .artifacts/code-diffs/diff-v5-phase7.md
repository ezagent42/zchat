---
type: code-diff
id: code-diff-v5-phase7
status: completed
producer: skill-3
created_at: "2026-04-20T00:00:00Z"
phase: 7
related:
  - eval-doc-010
  - test-plan-011
  - test-diff-v5-phase7
spec: docs/spec/channel-server-v5.md §4.2 audit + activation
plan: docs/discuss/plan/v5-refactor-plan.md §Phase-7
---

# Code Diff: V5 Phase 7 — audit + activation plugin 恢复

## 改动摘要

恢复被 1f1233c 误删的 audit / activation plugin。audit 持久化 `audit.json`（per-channel 状态 + 聚合）。activation 检测客户在已 resolved channel 发言 → emit `customer_returned`。

## 文件清单

**新增（CS）：**
- `src/plugins/audit/__init__.py`
- `src/plugins/audit/plugin.py` — `AuditPlugin` (BasePlugin)
- `src/plugins/activation/__init__.py`
- `src/plugins/activation/plugin.py` — `ActivationPlugin`

**修改（CS）：**
- `src/channel_server/__main__.py` — 注册 `AuditPlugin` + `ActivationPlugin`

## 关键 schema（audit.json）

```json
{"channels": {"conv-x": {
  "state": "active|takeover|resolved",
  "created_at": "...", "first_message_at": "...", "first_reply_at": "...",
  "takeovers": [{"at":"...", "triggered_by":"op", "released_at":"...", "released_by":"op"}],
  "resolved_at": null, "message_count": 0, "csat_score": null}}}
```

## query 接口

- `query("status")` → {channels, aggregates}
- `query("status", {"channel": "conv-x"})` → 单 channel 详情
- `query("report")` → {aggregates}

## 验收

- unit: tests/unit/test_audit_plugin.py — mode_changed/resolved 入文件 + query 正确
- unit: tests/unit/test_activation_plugin.py — customer_returned 触发条件
- `__main__.py` 注册 6 plugin（mode/sla/resolve/audit/activation/csat）
