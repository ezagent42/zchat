---
type: test-plan
id: test-plan-007
status: executed
producer: skill-2
created_at: "2026-04-13T00:00:00Z"
updated_at: "2026-04-14T00:00:00Z"
related:
  - eval-doc: eval-weechat-cache-006
  - code-diff: code-diff-005
  - test-diff: test-diff-004
  - issue: https://github.com/ezagent42/zchat/issues/42
---

# Test Plan: WeeChat server cache 强制更新（fix #42）

## 来源
- eval-doc: `eval-weechat-cache-006`
- code-diff: `code-diff-005`（commit `f57eb46`）
- 修复代码位置: `zchat/cli/irc_manager.py:266-276`（`_build_weechat_cmd`）

## 测试范围

`IrcManager._build_weechat_cmd()` 生成的 WeeChat 启动命令，
`/server add` 之后必须紧跟 `/set` 命令覆盖缓存中的 addresses、ssl、nicks。

## Test Cases

| TC-ID | 场景 | 测试类型 | 优先级 | 操作 | 断言 |
|-------|------|---------|-------|------|------|
| TC-01 | 命令中包含 `/set addresses` | unit | P0 | 调用 `_build_weechat_cmd()` | 含 `/set irc.server.{name}.addresses "{server}/{port}"` |
| TC-02 | `/set addresses` 在 `/server add` 之后 | unit | P0 | 同上 | `addresses` 位置在 `server add` 之后 |
| TC-03 | TLS=False 时 ssl 值为 off | unit | P0 | TLS=False | 含 `/set irc.server.{name}.ssl off` |
| TC-04 | TLS=True 时 ssl 值为 on | unit | P0 | TLS=True | 含 `/set irc.server.{name}.ssl on` |
| TC-05 | 命令中包含 `/set nicks` | unit | P1 | nick=testuser | 含 `/set irc.server.{name}.nicks "testuser"` |
| TC-06 | nick 变更后命令反映新值 | unit | P1 | nick=newuser | nicks 中含 `newuser` |
| TC-07 | server/port 变更后 addresses 反映新值 | unit | P1 | server=new.host, port=7000 | addresses 含 `new.host/7000` |
| TC-08 | `/server add` 也反映新 server/port | unit | P1 | 同上 | server add 命令含 `new.host/7000` |

## 验证结果

| TC-ID | 状态 |
|-------|------|
| TC-01 | PASS |
| TC-02 | PASS |
| TC-03 | PASS |
| TC-04 | PASS |
| TC-05 | PASS |
| TC-06 | PASS |
| TC-07 | PASS |
| TC-08 | PASS |

8/8 通过，见 `tests/unit/test_irc_manager_weechat_cmd.py`。
