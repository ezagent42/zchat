---
type: test-diff
id: test-diff-004
status: merged
producer: skill-3
created_at: "2026-04-13T15:00:00Z"
related:
  - test-plan: test-plan-007
  - eval-doc: eval-weechat-cache-006
---

# Test Diff: WeeChat server cache 强制更新单元测试（fix #42）

## 来源
- test-plan: `test-plan-007`（TC-01 ~ TC-08）
- 文件: `tests/unit/test_irc_manager_weechat_cmd.py`

## 测试策略

直接调用 `IrcManager._build_weechat_cmd()` 并断言返回的命令字符串中包含正确的 `/set` 语句，
不需要启动真实 WeeChat 进程。

## 新增测试

### 文件：`tests/unit/test_irc_manager_weechat_cmd.py`（+99 行）

| 测试类 | 测试方法 | 覆盖 TC |
|-------|---------|---------|
| TestWeechatCmdAddresses | test_set_addresses_present | TC-01 |
| TestWeechatCmdAddresses | test_set_addresses_after_server_add | TC-02 |
| TestWeechatCmdSsl | test_ssl_off_when_tls_false | TC-03 |
| TestWeechatCmdSsl | test_ssl_on_when_tls_true | TC-04 |
| TestWeechatCmdNicks | test_set_nicks_present | TC-05 |
| TestWeechatCmdNicks | test_set_nicks_reflects_nick_override | TC-06 |
| TestWeechatCmdServerChange | test_new_server_reflected_in_addresses | TC-07 |
| TestWeechatCmdServerChange | test_new_server_reflected_in_server_add | TC-08 |

## 运行结果

```
uv run --no-sync pytest tests/unit/test_irc_manager_weechat_cmd.py -v
8 passed in 0.17s
```

验证时间：2026-04-14，Python 3.13.12
