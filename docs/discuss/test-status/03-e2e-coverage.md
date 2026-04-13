# E2E 测试覆盖率与缺口分析

> 分析日期：2026-04-09

## 当前 E2E 覆盖矩阵

### 通信链路

| 场景 | test_e2e.py | pre_release | walkthrough | 覆盖状态 |
|------|:-----------:|:-----------:|:-----------:|:--------:|
| WeeChat → IRC 连接 | Phase 1 | test_03 | Yes | ✅ 完整 |
| Agent → IRC 连接 | Phase 2 | test_04 | Yes | ✅ 完整 |
| Agent 发送频道消息 | Phase 3 | test_04 | Yes | ✅ 完整 |
| @mention 触发回复 | Phase 4 | test_04 | Yes | ✅ 完整 |
| Agent 间 @mention | Phase 6 | — | — | ⚠️ 仅 E2E |
| 用户间对话 | Phase 7 | test_04a | — | ✅ 完整 |
| 私聊（DM） | — | — | — | ❌ 未覆盖 |
| 系统消息（stop/join） | — | — | — | ❌ 未覆盖（仅 unit test） |
| 长消息分片 | — | — | — | ❌ 未覆盖（仅 unit test） |

### 生命周期

| 场景 | test_e2e.py | pre_release | walkthrough | 覆盖状态 |
|------|:-----------:|:-----------:|:-----------:|:--------:|
| 项目 create/list/remove | — | test_01 | Yes | ✅ 完整 |
| ergo daemon start/stop | — | test_03 | Yes | ✅ 完整 |
| WeeChat start/stop | — | test_03 | Yes | ✅ 完整 |
| Agent create | Phase 2 | test_04 | Yes | ✅ 完整 |
| Agent stop | Phase 8 | test_04 | Yes | ✅ 完整 |
| Agent restart | — | test_04 | Yes | ✅ 完整 |
| Agent send | — | test_04 | Yes | ✅ 完整 |
| 多 Agent 并存 | Phase 5-6 | — | — | ⚠️ 仅 E2E |
| shutdown | Phase 9 | test_08 | Yes | ✅ 完整 |
| 模板 create/set | — | test_02 | Yes | ✅ 完整 |

### 认证与远程

| 场景 | test_e2e.py | pre_release | walkthrough | 覆盖状态 |
|------|:-----------:|:-----------:|:-----------:|:--------:|
| OIDC login | — | test_06 (manual) | — | ⚠️ 手动 |
| SASL 远程连接 | — | test_04b | — | ✅ 有 |
| Token 刷新 | — | test_06 (manual) | — | ⚠️ 手动 |

### 基础设施

| 场景 | test_e2e.py | pre_release | walkthrough | 覆盖状态 |
|------|:-----------:|:-----------:|:-----------:|:--------:|
| Zellij session 创建 | conftest | conftest | — | ✅ fixture |
| Zellij tab 生命周期 | test_zellij_lifecycle | — | — | ✅ 有 |
| ergo languages 下载 | — | — | — | ❌ 未覆盖 |
| 配置迁移 tmux→Zellij | — | — | — | ❌ 仅 unit |
| start.sh 一键启动 | — | — | Yes | ⚠️ 仅 walkthrough |
| WeeChat 插件加载 | — | test_05 | Yes | ✅ 完整 |

## 缺口分析

### 高优先级缺口

1. **私聊（DM）E2E 测试缺失**
   - 单元测试覆盖了 `on_privmsg` 逻辑
   - 但端到端的 DM → channel-server → Claude → reply 链路无自动化验证
   - 建议：在 test_e2e.py 添加 DM phase

2. **系统消息 E2E 缺失**
   - `sys.stop_request`、`sys.join_request` 等只有 protocol 层 unit test
   - 通过 IRC 传输的完整 encode→decode→handle 链路无 E2E
   - 建议：在 test_e2e.py 添加 sys message phase

3. **ergo languages 自动下载未测试**
   - fix/language-dir 分支的修复没有对应测试
   - 建议：unit test mock subprocess + 集成测试验证实际下载

4. **start.sh / stop.sh 自动化测试缺失**
   - walkthrough 录制覆盖了，但无 pytest 自动断言
   - start.sh 的 Zellij session 创建 bug 就是因为缺乏测试

### 中优先级缺口

5. **HTTP_PROXY 对本地 IRC 连接的影响**
   - 第一轮测试中 channel-server 的 IRC 连接可能受 proxy 干扰
   - 无测试覆盖 proxy 环境下的本地连接

6. **Agent 间通信 E2E 薄弱**
   - test_e2e.py Phase 6 有 agent-to-agent mention
   - 但无验证：agent A reply → IRC → agent B 收到并处理

7. **配置迁移仅 unit test**
   - migrate.py 的 tmux→Zellij 迁移只有 mock 测试
   - 实际旧配置 → `project use` → 迁移成功的链路无 E2E

### 低优先级

8. **长消息分片 E2E**
   - chunk_message 有充分 unit test
   - 但 >4000 字符消息经 IRC 传输后的完整性无 E2E

9. **多项目切换**
   - pre_release 有 project create/use/remove
   - 但多项目间 agent 隔离性无测试

## 录制与可视化工具现状

### asciinema 录制

| 方面 | 状态 |
|------|------|
| 录制脚本 | `walkthrough.sh` + `walkthrough-steps.sh` ✅ |
| 输出格式 | `.cast`（asciinema）✅ |
| GIF 生成 | `agg` 可选 ✅ |
| CI 集成 | ❌ 无（仅手动执行） |
| 自动断言 | ❌ 无（纯录制，人工 review） |

### 浏览器截屏 / Agent 截屏

| 方面 | 状态 |
|------|------|
| Playwright | ❌ 未使用 |
| 浏览器自动化 | ❌ 无（zchat 是终端应用） |
| 终端截屏 | 通过 Zellij `capture_pane` 间接实现 |
| 截屏比对 | ❌ 无 |

### Claude Code Skill/Plugin 测试支持

| 方面 | 状态 |
|------|------|
| 测试相关 skill | ❌ 无专门的测试 skill |
| superpowers TDD skill | ✅ 可用但非 zchat 定制 |
| hookify 测试 hook | ❌ 无 |
| agent-setup 测试配置 | ❌ 无 |

## CI/CD 覆盖

```
GitHub Actions (test.yml)
├── ✅ 单元测试（macOS）
├── ❌ E2E 测试（需要 ergo + Zellij）
├── ❌ 预发布测试（需要完整环境）
└── ❌ asciinema 录制（手动）
```

**建议**：E2E 测试可以加入 CI，用 Docker 容器提供 ergo，Zellij 已在 CI 中安装。
