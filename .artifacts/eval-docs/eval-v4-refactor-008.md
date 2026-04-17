---
type: eval-doc
id: eval-doc-008
status: draft
producer: skill-5
created_at: "2026-04-17T00:00:00Z"
mode: simulate
feature: v4-channel-architecture-refactor
submitter: zyli
related: []
---

# Eval: V4 channel-architecture 重构

## 基本信息

- 模式：模拟
- 提交人：zyli
- 日期：2026-04-17
- 状态：draft
- 基线：refactor/v3-audit 分支 HEAD
- 目标分支：refactor/v4（从 v3-audit 起）

## Feature 描述

将 zchat 三仓架构彻底抽象化，做到**最大解耦 + 业务零泄漏到 infra**：

1. **zchat-protocol** 收敛到 3 文件：`irc_encoding.py` / `ws_messages.py` / `naming.py`。纯格式定义 + 纯函数编解码，无状态、无业务词汇。
2. **zchat-channel-server** 重写为**纯路由 + 插件框架**：核心只做 IRC ↔ WS 转发；业务（mode、sla、audit、lifecycle）全部作为 plugin 通过 `handles_commands()` 自声明接管哪些命令。插件以 channel-server 一等公民存在，不外置。
3. **feishu_bridge** 作为 channel-server 同仓独立 package，**零 import 跨越边界**，只通过 WS + zchat_protocol 合同与核心通信。
4. **agent_mcp** 原地保留，只替换硬编码前缀字符串为 protocol import。新增 `run_zchat_cli` 工具，admin-agent 用它把 IM 群里的 `/status /dispatch /review` 翻译为 CLI 调用。
5. **配置分层**：`config.toml`（静态）+ `routing.toml`（动态 channel↔agent 映射）。
6. **命令两条路径**：
   - Infra 命令（`/hijack /release /copilot` 等）：由 plugin 自声明接管，channel-server 本地处理，不走 IRC。
   - 业务命令（`/dispatch /status /review` 等）：透传给 IRC，admin-agent 调 CLI 执行。

## 设计原则（硬约束）

- `channel_server/` 只 import `zchat_protocol + stdlib + irc + websockets`
- `feishu_bridge/` 只 import `zchat_protocol + stdlib + lark_oapi + websockets`
- `agent_mcp` 只 import `zchat_protocol + stdlib + mcp + irc`
- 三者之间零 Python import；通过 WS 合同 + IRC PRIVMSG 对话
- **bridge 不硬编码任何命令集合**；命令路由由 channel-server 的 PluginRegistry 根据 plugin 自声明完成
- protocol 里 0 个 method，0 个 I/O，全是 dataclass + pure function
- `MessageVisibility` enum 删除；消息种类由 IRC 前缀承载（唯一真源）

## PRD 对齐校验

| PRD 需求 | V4 覆盖方案 | 对应 Test Case |
|---------|-------------|---------------|
| US-2.1 3s 问候 | 路由最短路径 | TC-V4-02, TC-V4-07 |
| US-2.2 占位 + `__edit:` 续写 | protocol irc_encoding 保留 EDIT | TC-V4-01 |
| US-2.3 分队卡片实时刷新 | feishu_bridge outbound 渲染 | TC-V4-11 |
| US-2.4 Copilot 监管模式 | mode_plugin + router | TC-V4-05 |
| US-2.5 `@人工` / `/hijack` | mode_plugin 自声明 `hijack` | TC-V4-04 |
| US-2.6 角色翻转 + 接管次数 | mode_plugin emit event + audit_plugin 订阅 | TC-V4-05, TC-V4-10 |
| US-3.2 `/status /dispatch /review` | admin-agent + `run_zchat_cli` | TC-V4-09 |
| US-3.3 SLA 告警 + 自动 release | sla_plugin timer + 内部 command | TC-V4-06 |
| 计费指标（接管次数/CSAT/达成率） | audit_plugin 订阅 event 维护 | TC-V4-10 |

## Testcase 表（模拟效果）

| #  | 场景 | 前置条件 | 操作步骤 | 预期效果 | 模拟效果（基于设计分析） | 差异描述 | 优先级 |
|----|------|---------|---------|---------|---------------------|---------|-------|
| TC-V4-01 | IRC 前缀往返一致 | protocol v4 三文件 | `encode_msg(id, "你好")` 然后 `parse()` 结果 | kind=msg, text="你好", message_id=id | 纯函数实现、双向无损；同理 side/edit/sys 四种前缀 | 无差异 | P0 |
| TC-V4-02 | WS JSON 信封构造解析 | protocol v4 | `build_message(ch, src, content)` 然后 `parse()` | type=message, channel/source/content 字段保留 | 符合；无 visibility 字段（已删） | 无差异 | P0 |
| TC-V4-03 | Plugin 自声明命令注册 | channel-server v4 | mode_plugin.handles_commands() 返回 ["hijack","release","copilot"]；加载后 registry.get_handler("hijack") 返回 mode_plugin | 注册成功；重复注册同一命令抛 ValueError | 注册表 O(1) lookup；冲突检测在 register() 中 | 无差异 | P0 |
| TC-V4-04 | `/hijack` 命令分派 | channel-server + mode_plugin 已启动 | bridge 发 WS message content="/hijack" channel="ch-1" | router 识别命令 → registry.get_handler("hijack") → 派给 mode_plugin → mode["ch-1"]=takeover | 符合；命令消息**不**转发到 IRC（plugin 消费） | 无差异 | P0 |
| TC-V4-05 | Mode 影响 @prefix | mode_plugin 记录 ch-1=takeover | bridge 发客户消息 "你好" 到 ch-1 | router 查 mode=takeover → IRC PRIVMSG 无 @agent prefix | agent 看不到 @ 不响应；operator 在飞书群自己回 | 无差异 | P0 |
| TC-V4-06 | SLA 自动 release | ch-1 切 takeover + sla_plugin 开 timer | 180s 内无 operator 发消息 | sla_plugin timer 超时 → 内部 emit command /release → mode_plugin 切回 copilot → 下一条消息 prefix 恢复 @agent | 同时 emit event `sla_breach` 供 audit 订阅 | 无差异 | P1 |
| TC-V4-07 | 无 @ 业务命令透传 IRC | 无 plugin 声明 `status` | bridge 发 content="/status" channel="ch-admin" | router 查 registry 无 handler → 作为普通 message 路由 → IRC PRIVMSG @admin-agent __msg:...:/status | admin-agent 收到 @ 自己 + / 开头 | 无差异 | P0 |
| TC-V4-08 | admin-agent 调 CLI | admin-agent 启动 + run_zchat_cli MCP tool 注册 | admin-agent 收到 "/dispatch fast-agent ch-1" | 解析 → run_zchat_cli(["agent","join","fast-agent","ch-1"]) → subprocess.run → CLI 改 routing.toml | 输出作为回复发回 IRC；soul.md 约定响应格式 | 无差异 | P0 |
| TC-V4-09 | 零 Python 跨仓 import | V4 代码全部写完 | `grep -r "from channel_server" src/feishu_bridge/ src/agent_mcp/`；`grep -r "from feishu_bridge" src/channel_server/` 反向；等等 | 所有 grep 结果为空 | 通过 `import` 约束测试强制；CI 可加 lint 规则 | 无差异 | P0 |
| TC-V4-10 | audit_plugin 订阅 event | audit_plugin 启动 + mode_plugin 工作 | 执行 `/hijack` → mode_plugin 发 event role_flipped | audit_plugin on_ws_event 捕获，计数+1；CLI `zchat audit query --type=takeover_count` 返回 1 | audit_plugin 维护 dict + 支持查询接口；CLI 通过 admin API 查 | 无差异 | P1 |
| TC-V4-11 | 卡片 __edit: 实时刷新 | feishu_bridge 记录 msg_id 映射 | agent 发 `__msg:uuid1:你好` 然后 `__edit:uuid1:您好` | bridge 收到 edit → 查映射 → 调飞书 update_message | 保留现有 VisibilityRouter.on_edit 逻辑，移入 feishu_bridge.outbound | 无差异 | P1 |
| TC-V4-12 | 配置文件分层 | zchat CLI v4 | `zchat project create x`；`zchat channel create ch-1 --feishu-chat oc_xxx` | config.toml 只含 IRC server/default type 等；routing.toml 出现 `[channels."ch-1"]` 条目 | CLI 对应命令区分写入目标 | 无差异 | P1 |
| TC-V4-13 | MessageVisibility 枚举移除 | protocol v4 | `grep -r "MessageVisibility" zchat-protocol/ zchat-channel-server/` | 所有结果为 0；消息种类由 parse() 返回的 kind 字段表达 | 彻底删除枚举定义；所有消费点改用 kind | 无差异 | P0 |
| TC-V4-14 | Mode 切换事件广播 | channel-server + feishu_bridge 运行 | `/hijack ch-1` 触发 | mode_plugin emit event mode_changed → ws_server 广播 → feishu_bridge 收到 → 刷新 squad card 显示 "当前 takeover" | bridge 订阅 event 做 UI 更新 | 无差异 | P2 |
| TC-V4-15 | routing.toml 热重载 | channel-server 运行中 | CLI 执行 `zchat agent join fast-agent ch-1` 修改 routing.toml；发 SIGHUP 给 server | routing 表刷新；下条 ch-1 消息正确 @ 新 agent | 实现细节：watcher 或 SIGHUP handler 重新加载 | 无差异 | P2 |

## 范围外（不在 V4 scope，后续项）

- `zchat-audit-service` 独立仓（audit_plugin 已覆盖核心功能，独立化是 V5 考虑）
- Web 仪表盘（PRD US-3.1）
- Dream Engine 深化实现（PRD Epic 4）
- 多 bridge 扩展（除 feishu 之外的 IM）
- 合规预检（agent skill 层）

## 风险点

1. **agent_mcp 不拆仓**但接口改动：添加 `run_zchat_cli` 工具需要 admin-agent soul.md 同步更新响应逻辑；现有 fast/deep-agent 不受影响。
2. **SLA timer plugin**：在 channel-server 进程里跑 timer 可能影响 IRC 事件循环；必须用 asyncio 或独立 thread 隔离。
3. **命令串台风险**：如果某 plugin 错误声明已有 infra 命令，会抢 agent 的命令处理。`PluginRegistry.register()` 检测冲突并抛异常，启动即报错避免运行时问题。
4. **routing.toml 热重载竞态**：CLI 写 toml 与 server 读 toml 需要文件锁或原子写；用 `pathlib.Path.write_text` + temp file rename 保证原子性。
5. **E2E 测试大量重写**：现有 E2E 依赖 conversation/mode/squad 概念，V4 下需按新接口重写。估计 30-50% E2E 用例需要重构。
6. **PRD 某些计费指标**（CSAT、达成率）需 audit_plugin + CLI query 支持；本次重构覆盖架构骨架，计算逻辑作为 plugin 内部实现放入 V4 scope。

## 执行计划（6 步）

| 步骤 | 工作内容 | 改动仓 |
|------|---------|--------|
| V4-S1 | protocol 收敛到 3 文件（删 7 个原语模块，合并 sys_messages 到 irc_encoding） | zchat-protocol |
| V4-S2 | channel-server 新建 src/channel_server/ 核心（routing + irc_connection + ws_server + router + plugin.py） + 官方插件 src/plugins/ (mode/sla/audit/lifecycle) | zchat-channel-server |
| V4-S3 | feishu_bridge 重组为 src/feishu_bridge/（零 import channel_server；内部不分拣命令） | zchat-channel-server |
| V4-S4 | agent_mcp.py 原地换 import + 新增 run_zchat_cli 工具 + admin-agent soul.md 更新 | zchat-channel-server + zchat/cli/templates |
| V4-S5 | CLI 配置分 config.toml 静态 / routing.toml 动态，`zchat channel create` 等命令对齐 | zchat |
| V4-S6 | 全仓单元 + E2E 回归，ralph-loop 审残留，三 commit 分别提交 | 全部 |

## 成功标准

1. 15 个 testcase 全部通过（新写 pytest + E2E）
2. `grep` 零 Python 跨包 import
3. `grep "MessageVisibility"` 全仓零结果
4. protocol 总代码行数 < 200（当前约 350）
5. channel-server 核心（非 plugin、非 bridge）代码行数 < 800（当前 engine/ 约 2500）
6. PRD 对齐表所有 ✓
7. 预存失败数不增（baseline：protocol 2 + cs 1 + zchat 3）

## 后续（Phase 2-7）

本 eval-doc 作为 Phase 1 输出。下游：
- Phase 2-3: Skill 2 从本 eval-doc 生成 test-plan（15 个 TC 扩展 + 补充边界）
- Phase 4: Skill 3 基于 test-plan 写 pytest 代码
- Phase 5: Skill 4 运行测试 + 报告
- Phase 6: 按测试失败驱动实现 V4-S1 ~ V4-S6
- Phase 7: Skill 5 verify 模式记录实现中发现的问题
