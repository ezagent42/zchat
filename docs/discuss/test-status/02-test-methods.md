# 测试方式与实现分析

> 分析日期：2026-04-09

## 四层测试体系

```
┌─────────────────────────────────────────────────┐
│ 预发布验收（Pre-release）                         │
│ asciinema 录制 + pytest 自动化                    │
│ 覆盖完整 CLI 生命周期                              │
├─────────────────────────────────────────────────┤
│ E2E 测试                                         │
│ pytest + IrcProbe + Zellij                       │
│ 覆盖消息全链路（WeeChat → IRC → Agent → 回复）    │
├─────────────────────────────────────────────────┤
│ 集成测试（placeholder，未实现）                     │
│ pytest + 真实 IRC server                         │
├─────────────────────────────────────────────────┤
│ 单元测试                                         │
│ pytest，纯逻辑，mock 外部依赖                      │
│ ~2 秒完成                                        │
└─────────────────────────────────────────────────┘
```

## 1. 单元测试

**运行命令**：`uv run pytest tests/unit/ -v`
**执行时间**：~2 秒
**CI 集成**：GitHub Actions（macOS）

**实现方式**：
- 标准 pytest，无外部依赖
- 大量使用 `monkeypatch`、`tmp_path`、`unittest.mock`
- Zellij 操作通过 mock subprocess 测试
- 路径测试通过 `ZCHAT_HOME` 环境变量隔离

**覆盖领域**：

| 模块 | 测试文件 | 关注点 |
|------|----------|--------|
| AgentManager | test_agent_manager.py | scoped_name、workspace 创建、.ready 检测、状态持久化 |
| IrcManager | test_irc_check.py | TCP/TLS 连通性检查 |
| Project | test_project.py, test_project_create_params.py | 项目 CRUD、配置格式、server 预设 |
| Paths | test_paths.py | 环境变量 > 配置 > 默认值优先级 |
| Layout | test_layout.py | KDL 布局生成、agent tab、offline 过滤 |
| Migration | test_migrate.py | tmux→Zellij 配置/状态迁移 |
| Auth | test_auth.py | OIDC flow、token 缓存、刷新 |
| Template | test_template_loader.py | 模板加载、.env 渲染、hooks |
| Zellij | test_zellij_helpers.py | send_keys、capture_pane、wait_for_content |
| Update | test_update.py | 版本检测、升级逻辑 |

## 2. E2E 测试

**运行命令**：`uv run pytest tests/e2e/ -v -m e2e`
**执行时间**：~5-10 分钟
**外部依赖**：ergo + Zellij
**CI 集成**：无（需要外部服务）

### 实现架构

```
conftest.py (fixtures)
├── e2e_port        → 动态端口 (16667 + PID % 1000)
├── zellij_session  → headless Zellij session 创建/清理
├── e2e_context     → 临时 ZCHAT_HOME + 项目配置
├── ergo_server     → IrcManager.daemon_start()
├── zchat_cli       → subprocess CLI runner
├── irc_probe       → IRC 探针客户端（加入 #general，记录消息）
├── bob_probe       → 第二个 IRC 客户端
├── weechat_tab     → WeeChat Zellij tab
└── zellij_send     → Zellij 按键发送
```

### 测试阶段（test_e2e.py，9 个有序阶段）

```
Phase 1: WeeChat 连接 IRC        → irc_probe 检测 nick 出现
Phase 2: Agent 加入 IRC           → irc_probe 检测 agent nick
Phase 3: Agent 发送频道消息        → irc_probe 等待消息匹配
Phase 4: @mention 触发 agent 回复  → irc_probe 等待回复
Phase 5: 创建第二个 agent          → agent list 验证
Phase 6: Agent 间 @mention         → irc_probe 检测
Phase 7: 用户间对话               → bob_probe 收发验证
Phase 8: Agent 停止               → agent list 验证 offline
Phase 9: 系统关闭                 → 全部停止
```

### IrcProbe 实现（tests/shared/irc_probe.py）

核心测试工具，模拟 IRC 客户端：
- 基于 `irc.client.Reactor`，独立线程运行
- 自动加入指定频道，持续记录所有消息
- `wait_for_nick(nick, timeout)` — 轮询检测 nick 出现
- `wait_for_message(pattern, timeout)` — 正则匹配消息内容
- `privmsg(channel, text)` — 主动发送消息
- 支持 SASL 认证（TLS + token）

### Zellij 辅助（tests/shared/zellij_helpers.py）

```python
send_keys(session, target, text)     # 发送按键到 pane
capture_pane(session, target)        # 读取 pane 内容
wait_for_content(session, target, pattern, timeout)  # 等待内容出现
```

## 3. 预发布验收测试

**运行命令**：`./tests/pre_release/run.sh` 或 `uv run pytest tests/pre_release/ -v -m "prerelease and not manual"`
**执行时间**：~15-20 分钟
**外部依赖**：ergo + Zellij + WeeChat + Claude Code

### 覆盖范围

| 模块 | 文件 | 测试内容 |
|------|------|----------|
| 环境检查 | test_00_doctor.py | 依赖检测 |
| 项目管理 | test_01_project.py | create/list/show/use/remove |
| 模板系统 | test_02_template.py | list/show/create/set |
| IRC | test_03_irc.py | daemon start/stop、WeeChat start/stop |
| Agent | test_04_agent.py | create/list/status/send/restart/stop |
| 用户聊天 | test_04a_irc_chat.py | Alice↔Bob 频道消息 |
| 远程 IRC | test_04b_remote_irc.py | TLS+SASL 连接 |
| 插件安装 | test_05_setup.py | WeeChat 插件 |
| 认证 | test_06_auth.py | login/status/refresh/logout（manual） |
| 更新 | test_07_self_update.py | check/upgrade（manual） |
| 关闭 | test_08_shutdown.py | daemon 控制、完整 shutdown |

### asciinema 录制（walkthrough）

```bash
# walkthrough.sh 流程
asciinema rec --command "./walkthrough-steps.sh" output.cast
agg output.cast output.gif  # 可选：生成 GIF
```

`walkthrough-steps.sh` 执行完整 CLI 生命周期，录制产物：
- `.cast` 文件（asciinema 回放格式）
- `.gif` 动图（如果安装了 `agg`）

用途：人工 review 完整操作流程，确认 UI 表现。

## 4. 子模块测试

### channel-server

```bash
cd zchat-channel-server && uv run pytest tests/ -v
```

| 测试 | 内容 |
|------|------|
| test_detect_mention | `@agent` 语法识别 |
| test_clean_mention | 去除 mention 前缀 |
| test_chunk_message_* | 消息分片（UTF-8 边界感知） |
| test_sys_message_* | 系统消息编解码 |
| test_load_instructions_* | instructions.md 模板渲染 |

### protocol

```bash
cd zchat-protocol && uv run pytest tests/ -v
```

| 测试 | 内容 |
|------|------|
| test_scoped_name | `scoped_name("agent0", "alice")` → `"alice-agent0"` |
| test_sys_encode_decode | `__zchat_sys:` 编解码 roundtrip |

## 5. 测试隔离策略

| 策略 | 实现 |
|------|------|
| 文件隔离 | `tmp_path` + `ZCHAT_HOME` 环境变量 |
| 端口隔离 | 动态端口：`16667 + os.getpid() % 1000` |
| Session 隔离 | 测试专用 Zellij session，teardown 自动清理 |
| 进程隔离 | fixture teardown kill ergo/WeeChat 进程 |
