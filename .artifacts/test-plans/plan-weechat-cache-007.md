---
type: test-plan
id: test-plan-007
status: draft
producer: skill-2
created_at: "2026-04-13T00:00:00Z"
related:
  - eval-doc: eval-weechat-cache-006
  - issue: https://github.com/ezagent42/zchat/issues/42
---

# Test Plan: WeeChat server cache 强制更新（fix #42）

## 来源
- eval-doc: `eval-weechat-cache-006`
- 修复代码位置: `zchat/cli/irc_manager.py:266-283`

## 测试范围

`IrcManager._build_weechat_cmd()` 生成的 WeeChat 启动命令中，
`/server add` 之后必须紧跟 `/set` 命令覆盖缓存中的 addresses、ssl、nicks。

## Test Cases

| TC-ID | 场景 | 测试类型 | 优先级 | 前置条件 | 操作 | 断言 |
|-------|------|---------|-------|---------|------|------|
| TC-01 | 命令中包含 `/set addresses` | unit | P0 | 任意有效配置 | 调用 `_build_weechat_cmd()` | 返回字符串含 `/set irc.server.{name}.addresses "{server}/{port}"` |
| TC-02 | 命令中包含 `/set ssl` | unit | P0 | TLS=False | 同上 | 含 `/set irc.server.{name}.ssl off` |
| TC-03 | TLS=True 时 ssl 值为 on | unit | P0 | TLS=True | 同上 | 含 `/set irc.server.{name}.ssl on` |
| TC-04 | 命令中包含 `/set nicks` | unit | P1 | nick=testuser | 同上 | 含 `/set irc.server.{name}.nicks "testuser"` |
| TC-05 | `/set addresses` 在 `/server add` 之后 | unit | P0 | 任意配置 | 同上 | `addresses` 的位置在 `server add` 之后 |
| TC-06 | server/port 变更后命令反映新值 | unit | P1 | server=new.host, port=7000 | 同上 | addresses 中含 `new.host/7000` |

## 测试文件位置

- 新建：`tests/unit/test_irc_manager_weechat_cmd.py`
