---
type: eval-doc
id: eval-weechat-cache-006
status: confirmed
producer: skill-5
created_at: "2026-04-13T00:00:00Z"
mode: verify
feature: WeeChat server cache 强制更新
submitter: zyli
related:
  - issue: https://github.com/ezagent42/zchat/issues/42
---

# Eval: 切换 IRC 服务器后 WeeChat 仍连接旧服务器（缓存未更新）

## 基本信息
- 模式：验证
- 提交人：zyli
- 日期：2026-04-13
- 状态：confirmed（已确认为 bug，fix 已合并）

## Testcase 表格

| # | 场景 | 前置条件 | 操作步骤 | 预期效果 | 实际效果 | 差异描述 | 优先级 |
|---|------|---------|---------|---------|---------|---------|--------|
| 1 | 首次启动，WeeChat 无缓存 | 全新项目，`irc.conf` 不存在 | `zchat irc start` | 连接到 `config.toml` 中配置的服务器 | 正常工作 | 无差异 | P0 |
| 2 | 切换 IRC 服务器后重启，WeeChat 连接旧服务器 | 已运行过 WeeChat，`irc.conf` 缓存旧地址；`config.toml` 修改为新服务器 | `zchat shutdown && zchat irc start` | 连接新服务器 | "server already exists"，沿用旧缓存地址 | `/server add` 对已存在 server 静默忽略新参数 | P0 |
| 3 | fix 后：`/set` 强制覆盖缓存地址 | 同上 | `zchat irc start`（fix 已引入） | 连接新服务器 | fix 在 `/server add` 后追加 `/set addresses`、`/set ssl`、`/set nicks` 强制覆盖 | 无差异，fix 有效 | P0 |
| 4 | TLS 开关切换后缓存更新 | 旧缓存 TLS=on；`config.toml` 改为 TLS=off | `zchat irc start` | 以 TLS=off 连接 | fix 通过 `/set ssl off` 强制更新 | 无差异 | P1 |
| 5 | nick 变更后缓存更新 | 旧缓存 nick=alice；`config.toml` 改为 nick=bob | `zchat irc start` | 使用 nick=bob | fix 通过 `/set nicks "bob"` 强制更新 | 无差异 | P1 |

## 证据区

### 日志/错误信息

```
irc: server 'local-ergo' already exists
```
WeeChat 忽略新参数，沿用 `irc.conf` 缓存地址连接旧服务器。

### 根本原因（代码层）

`zchat/cli/irc_manager.py`（修复前）：
```python
f"/server add {srv_name} {server}/{port}{tls_flag} -nicks={nick}"
# 若 server 已存在，WeeChat 忽略此命令，irc.conf 缓存不更新
```

修复后（`irc_manager.py:273-276`）：
```python
f"/server add {srv_name} {server}/{port}{tls_flag} -nicks={nick}"
f"; /set irc.server.{srv_name}.addresses \"{server}/{port}\""
f"; /set irc.server.{srv_name}.ssl {tls_on_off}"
f"; /set irc.server.{srv_name}.nicks \"{nick}\""
```

## 分流结论

**分类**：确认 bug

**判断理由**：
- `/server add` 的"已存在则忽略"是 WeeChat 设计行为，zchat 未处理此情况
- 用户期望 `zchat irc start` 总以最新 `config.toml` 为准
- fix 通过追加 `/set` 命令绕过限制，方案验证有效

## 后续行动

- [x] eval-doc 已注册到 registry.json（eval-doc-006）
- [x] 确认为 bug（status: confirmed）
- [x] 修复代码已合并（commit `f57eb46`，`irc_manager.py:266-276`）
- [x] code-diff 已注册（code-diff-005）
- [x] test-plan 已生成（plan-weechat-cache-007，Skill 2）
- [x] 测试代码已编写（test_irc_manager_weechat_cmd.py，8/8 pass，Skill 3）
- [x] test-diff 已注册（test-diff-004）
- [x] 测试报告已生成（e2e-report-004，8/8 green，Skill 4）
- [x] GitHub issue #42 关联此 eval-doc
