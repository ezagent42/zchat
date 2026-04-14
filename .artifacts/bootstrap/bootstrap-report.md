---
type: bootstrap-report
id: bootstrap-report-001
status: executed
producer: skill-0
created_at: "2026-04-10"
---

# Bootstrap Report: zchat

## 环境问题与解决

### Hard Dependencies（已修复）

1. **ergo languages 目录缺失**
   - 发现：Homebrew 安装的 ergo 不含 `languages/` 目录，导致 ergo 启动失败
   - 修复：从 `/tmp/ergo-2.18.0-linux-x86_64/languages` 复制到 `~/.local/share/ergo/languages`
   - 参考：`docs/discuss/e2e-log/2026-04-08-quickstart-test.md` Bug 1

2. **ergo TLS 配置导致启动失败**
   - 发现：`irc_manager.py:83` 的 TLS 删除正则不够彻底，ergo `defaultconfig` 中的 TLS cert/key 引用未删除
   - 修复：修改 `irc_manager.py:82-83`，用两个正则分别删除 `:6697` 监听行和 TLS cert/key 配置块
   - 代码修改：`zchat/cli/irc_manager.py` 第 82-83 行

### Soft Dependencies（未修复 / 不影响）

3. **asciinema 缺失**
   - 状态：上次 bootstrap 已自动安装
   - 影响：仅影响 pre-release 录制，不影响测试

4. **docker 缺失**
   - 状态：未安装
   - 影响：当前无测试依赖 docker

5. **port 6697 未监听**
   - 状态：TLS 端口不需要（已通过 TLS 配置修复绕过）
   - 影响：无

## 测试执行结果

### 汇总

| 测试套件 | Passed | Failed | Error | Skip |
|----------|--------|--------|-------|------|
| Unit tests | 196 | 1 | 0 | 0 |
| E2E tests | 9 | 4 | 0 | 0 |
| Channel-server | 12 | 0 | 0 | 0 |
| Protocol | 7 | 2 | 0 | 0 |
| **总计** | **224** | **7** | **0** | **0** |

### 关键改进

上次 bootstrap E2E 有 9 个 ERROR（环境问题），本次 0 个 ERROR。环境修复（ergo languages + TLS 配置）消除了全部环境导致的 error。

### 失败测试根因分类

| 测试 | 分类 | 根因 |
|------|------|------|
| `test_unreachable_server_raises` | 测试设计问题 | 依赖网络环境行为，WSL2 下 `192.0.2.1` 被快速拒绝而非超时 |
| `test_agent_send_to_channel` | MCP 超时 | Claude Code agent 在 30s 内未完成 MCP reply 操作 |
| `test_mention_triggers_reply` | MCP 超时 | @mention 后 agent 未在 30s 内响应 |
| `test_second_agent` | MCP 超时 | agent1 MCP 消息 30s 超时 |
| `test_agent_to_agent` | MCP 超时 | agent 间 MCP 通信 30s 超时 |
| `test_scoped_name_no_double_prefix` | 代码 bug | `scoped_name()` 不检查已有前缀 |
| `test_scoped_name_different_prefix` | 代码 bug | `scoped_name()` 不检查已有前缀 |

## 覆盖分析

### 代码测试覆盖

- **覆盖模块**：14/15 模块有测试覆盖
- **未覆盖模块**：`doctor` 模块无测试

### 操作 E2E 覆盖

- **已覆盖流程**：9/24 用户流程（含 4 个 MCP 超时 fail）
- **E2E 缺口**：13 个用户流程待补
- **缺口原因**：E2E 测试集中在核心 agent 生命周期（create/stop/list/restart/send），尚未覆盖 project 管理、IRC 配置、template、auth、setup、shutdown 等 CLI 子命令

## 决策记录

1. **ergo TLS fix 判定为代码修复（bug fix）**
   - `irc_manager.py` 的正则修改是代码层面的 bug fix，不是一次性配置变更
   - 修复后所有新环境都能正确启动 ergo

2. **test_unreachable_server_raises 判定为测试设计问题**
   - 1 个 unit test fail，根因是测试假设 `192.0.2.1` 会超时，但 WSL2 网络栈快速返回 connection refused
   - 判定为代码 bug（测试设计问题），不是环境问题

3. **E2E 的 4 个 MCP 超时判定为功能问题**
   - Claude Code agent 响应时间超过 30s 导致超时
   - 判定为功能问题（Claude Code 响应时间），不是环境问题
   - 后续可考虑增大超时或引入重试机制

4. **protocol 的 2 个 scoped_name fail 判定为代码 bug**
   - `scoped_name()` 函数不检查输入是否已有前缀，导致双前缀
   - 不影响 bootstrap 产出，需在后续迭代中修复
