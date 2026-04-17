---
type: test-plan
id: test-plan-009
status: draft
producer: skill-2
created_at: "2026-04-17T00:00:00Z"
trigger: "eval-doc-008"
related:
  - eval-doc-008
---

# Test Plan: V4 channel-architecture 重构

## 触发原因

eval-doc-008 记录了 V4 重构的 15 个核心 testcase。V4 将：
- zchat-protocol 收敛到 3 文件（纯格式+编解码）
- channel-server 重写为纯路由 + 插件框架
- feishu_bridge 作为零耦合 sibling package
- agent_mcp 原地换 import + 新增 `run_zchat_cli`
- 命令两路径：infra plugin 自声明 / 业务走 agent+CLI

**测试策略**：
1. Protocol 层：纯函数单元测试（高密度，快速）
2. Routing 层：模拟 IRC + WS 的集成测试（中密度）
3. Plugin 层：订阅/声明/命令派发契约测试
4. 耦合边界：import 结构静态校验（CI lint）
5. 端到端：现有 E2E 大量重写，按 PRD 用户故事组织
6. 基线保证：重构不使现有预存失败数增加

**覆盖缺口**：
- 当前 E2E 针对旧 conversation/mode/squad 概念，V4 需重写
- 插件框架 + registry 是新概念，无现有测试可参考
- `run_zchat_cli` MCP tool 是新增，无测试

---

## 用例列表

### P0 用例（核心路径，必须通过）

#### TC-001: IRC 前缀编解码往返一致

- **来源**：eval-doc-008 TC-V4-01
- **优先级**：P0
- **前置条件**：zchat-protocol v4 已收敛，`irc_encoding.py` 提供 encode_msg/encode_side/encode_edit/encode_sys/parse
- **操作步骤**：
  1. 构造一个 UUID + 文本 "你好，世界"
  2. `encoded = encode_msg(uuid, "你好，世界")`
  3. `parsed = parse(encoded)`
  4. 同理测试 `encode_side("建议退款")`、`encode_edit(uuid, "修正")`、`encode_sys({"a":1})`
  5. 测试无前缀纯文本 `parse("hello")`
- **预期结果**：
  - msg: parsed == {kind: "msg", message_id: uuid, text: "你好，世界"}
  - side: parsed == {kind: "side", text: "建议退款"}
  - edit: parsed == {kind: "edit", message_id: uuid, text: "修正"}
  - sys: parsed == {kind: "sys", payload: {"a":1}}
  - 纯文本: parsed == {kind: "plain", text: "hello"}
- **涉及模块**：zchat-protocol/irc_encoding.py

#### TC-002: WS JSON 信封构造解析

- **来源**：eval-doc-008 TC-V4-02
- **优先级**：P0
- **前置条件**：zchat-protocol v4 的 `ws_messages.py` 定义 WSType + build_message/build_command/build_event/parse
- **操作步骤**：
  1. `msg = build_message(channel="ch-1", source="ou_xxx", content="你好")`
  2. `parsed = parse(json.dumps(msg))`
  3. 同理 build_command/build_event 往返
- **预期结果**：
  - msg 包含 `type="message"`, `channel="ch-1"`, `source="ou_xxx"`, `content="你好"`
  - **不包含 `visibility` 字段**
  - parsed 返回结构化 dict，字段完整
  - 未知类型抛 ValueError
- **涉及模块**：zchat-protocol/ws_messages.py

#### TC-003: MessageVisibility 枚举彻底删除

- **来源**：eval-doc-008 TC-V4-13
- **优先级**：P0
- **前置条件**：V4 代码全部完成
- **操作步骤**：
  1. `grep -r "MessageVisibility" zchat-protocol/ zchat-channel-server/src/ zchat/zchat/` 排除 __pycache__ 和 .venv
  2. `grep -r "from zchat_protocol.message_types" zchat-protocol/ zchat-channel-server/src/ zchat/zchat/`
- **预期结果**：两次 grep 结果为空
- **涉及模块**：全仓

#### TC-004: 跨仓零 import 耦合

- **来源**：eval-doc-008 TC-V4-09
- **优先级**：P0
- **前置条件**：V4 代码全部完成
- **操作步骤**：
  1. `grep -rn "from channel_server\|import channel_server" zchat-channel-server/src/feishu_bridge/ zchat-channel-server/src/agent_mcp/ 2>/dev/null` → 必须空
  2. 反向 `grep -rn "from feishu_bridge\|import feishu_bridge" zchat-channel-server/src/channel_server/ 2>/dev/null` → 必须空
  3. agent_mcp 保持不拆仓但换 import：`grep -rn "__msg:\|__side:\|__edit:\|__zchat_sys:" zchat-channel-server/agent_mcp.py` → 除了来自 protocol import 的引用，不应有硬编码字面量
  4. CI lint 校验脚本 `tools/lint_imports.py` 可作为补充
- **预期结果**：所有 grep 结果为空（符合零耦合约束）
- **涉及模块**：channel-server 三个子 package

#### TC-005: Plugin 自声明命令注册

- **来源**：eval-doc-008 TC-V4-03
- **优先级**：P0
- **前置条件**：channel-server v4 plugin.py 定义 Plugin 基类 + PluginRegistry
- **操作步骤**：
  1. 定义 `class FooPlugin(Plugin): def handles_commands(): return ["hijack","release"]`
  2. `registry = PluginRegistry(); registry.register(FooPlugin())`
  3. `registry.get_handler("hijack")` → FooPlugin 实例
  4. `registry.get_handler("unknown")` → None
  5. 定义 `class BarPlugin(Plugin): def handles_commands(): return ["hijack"]`（与 Foo 冲突）
  6. `registry.register(BarPlugin())` → 抛 ValueError
- **预期结果**：注册成功；lookup O(1)；冲突抛异常
- **涉及模块**：channel-server/plugin.py

#### TC-006: /hijack 命令由 plugin 接管，不进 IRC

- **来源**：eval-doc-008 TC-V4-04
- **优先级**：P0
- **前置条件**：channel-server 运行，mode_plugin 已注册 hijack/release/copilot；mock irc_connection
- **操作步骤**：
  1. 模拟 WS 客户端发 `{type:"message", channel:"ch-1", source:"ou_xxx", content:"/hijack"}`
  2. 观察 irc_connection.privmsg 调用次数
  3. 查 mode_plugin 当前 ch-1 mode
- **预期结果**：
  - irc_connection.privmsg **未被调用**（命令被 plugin 消费）
  - mode_plugin 记录 ch-1 mode = takeover
- **涉及模块**：channel-server/router.py, plugins/mode

#### TC-007: Mode 决定入站消息 @prefix

- **来源**：eval-doc-008 TC-V4-05
- **优先级**：P0
- **前置条件**：
  - mode_plugin 记录 ch-1 mode = copilot；ch-2 mode = takeover
  - routing.toml 中 ch-1 和 ch-2 的 fast-agent 都是 "yaosh-agent-001"
- **操作步骤**：
  1. 发 WS `{type:"message", channel:"ch-1", source:"ou_x", content:"你好"}`
  2. 捕获 irc_connection.privmsg 参数
  3. 发 WS `{type:"message", channel:"ch-2", source:"ou_y", content:"你好"}`
  4. 捕获
- **预期结果**：
  - ch-1 下 IRC 消息含 `@yaosh-agent-001` prefix
  - ch-2 下 IRC 消息**不含** @prefix（纯 `__msg:<uuid>:你好`）
- **涉及模块**：channel-server/router.py, routing.py

#### TC-008: 业务命令 / 开头透传 IRC，由 agent 处理

- **来源**：eval-doc-008 TC-V4-07
- **优先级**：P0
- **前置条件**：无 plugin 声明 "status"；routing 表 ch-admin 的 admin-agent = "yaosh-admin-001"；mode_plugin 记录 ch-admin = copilot
- **操作步骤**：
  1. 发 WS `{type:"message", channel:"ch-admin", source:"ou_admin", content:"/status"}`
  2. 捕获 irc_connection.privmsg 参数
- **预期结果**：
  - registry.get_handler("status") → None
  - router 把它当作普通 message 路由
  - IRC 消息含 `@yaosh-admin-001 __msg:<uuid>:/status`
- **涉及模块**：channel-server/router.py

#### TC-009: admin-agent run_zchat_cli 工具调用 CLI

- **来源**：eval-doc-008 TC-V4-08
- **优先级**：P0
- **前置条件**：agent_mcp 注册 `run_zchat_cli` tool；mock subprocess.run
- **操作步骤**：
  1. 通过 MCP 客户端调 `run_zchat_cli(["agent","join","fast-agent","ch-1"])`
  2. 观察 subprocess.run 被调参数
  3. mock 返回 stdout "joined ok"
- **预期结果**：
  - subprocess.run 调用参数以 `["zchat","agent","join",...]` 开头
  - MCP 返回的内容包含 "joined ok"
  - 失败场景返回 stderr
- **涉及模块**：agent_mcp.py（或其 tools 模块）

#### TC-010: Mode 切换后立即生效于下条消息路由

- **来源**：eval-doc-008 TC-V4-04 + TC-V4-05 复合
- **优先级**：P0
- **前置条件**：ch-1 初始 mode = copilot
- **操作步骤**：
  1. 发普通消息 → 观察带 @prefix
  2. 发 /hijack → mode → takeover
  3. 发普通消息 → 观察不带 @prefix
  4. 发 /release → mode → copilot
  5. 发普通消息 → 观察带 @prefix
- **预期结果**：@prefix 在每次切换后立即反映新 mode
- **涉及模块**：channel-server/router.py, plugins/mode

### P1 用例（重要边界 / 辅助指标）

#### TC-011: SLA timer 超时自动 release + 发 event

- **来源**：eval-doc-008 TC-V4-06
- **优先级**：P1
- **前置条件**：sla_plugin 启动，timeout=180；ch-1 进入 takeover 触发 timer
- **操作步骤**：
  1. /hijack ch-1 → mode=takeover → sla_plugin 启 timer
  2. mock time 或 fast-forward 180s
  3. timer 过期触发回调
- **预期结果**：
  - sla_plugin emit 内部 command /release → mode_plugin 切回 copilot
  - emit event sla_breach → audit_plugin 可订阅
  - ch-1 mode 变 copilot
- **涉及模块**：plugins/sla, plugins/mode

#### TC-012: audit_plugin 订阅 event 维护计数

- **来源**：eval-doc-008 TC-V4-10
- **优先级**：P1
- **前置条件**：audit_plugin 启动，订阅 mode_changed event
- **操作步骤**：
  1. /hijack ch-1 → emit mode_changed(from=copilot,to=takeover)
  2. audit_plugin.query("takeover_count", {"channel":"ch-1"}) 应为 1
  3. /release → mode_changed → takeover_count 不增
  4. 再 /hijack → takeover_count = 2
- **预期结果**：takeover 次数仅在 → takeover 转换时增加
- **涉及模块**：plugins/audit, plugins/mode

#### TC-013: 飞书卡片 __edit: 刷新

- **来源**：eval-doc-008 TC-V4-11
- **优先级**：P1
- **前置条件**：feishu_bridge.outbound 维护 msg_id → feishu_msg_id 映射；mock 飞书 API
- **操作步骤**：
  1. agent 发 IRC `__msg:uuid1:占位` → bridge 收到 WS → 调飞书 send_message → 飞书返回 fm_abc → 映射 uuid1→fm_abc
  2. agent 发 IRC `__edit:uuid1:完整答案` → bridge 收到 → 调飞书 update_message(fm_abc, "完整答案")
- **预期结果**：update_message 被调；参数正确
- **涉及模块**：feishu_bridge/outbound.py

#### TC-014: 配置文件分层正确

- **来源**：eval-doc-008 TC-V4-12
- **优先级**：P1
- **前置条件**：CLI v4；空项目目录
- **操作步骤**：
  1. `zchat project create alpha --server 1.2.3.4 --port 6667`
  2. 读 `~/.zchat/projects/alpha/config.toml`
  3. `zchat channel create ch-1 --feishu-chat oc_abc`
  4. 读 `~/.zchat/projects/alpha/routing.toml`
- **预期结果**：
  - config.toml 含 IRC server/port/username 等静态字段，**不含** channels
  - routing.toml 含 `[channels."ch-1"]` 条目 + feishu_chat_id
  - 两文件职责分离
- **涉及模块**：zchat/cli/project.py, channel.py

#### TC-015: 插件 emit 内部 command 被自己接管

- **来源**：eval-doc-008 TC-V4-06 延伸
- **优先级**：P1
- **前置条件**：mode_plugin + sla_plugin 都已注册
- **操作步骤**：
  1. sla_plugin.emit({"type":"command","command":"release","channel":"ch-1"})
  2. channel-server 的 event loop 重新 dispatch 这条内部消息
  3. registry.get_handler("release") → mode_plugin
- **预期结果**：内部 emit 与外部 WS 入站消息走同一分派路径，符合"插件间通过 command/event 解耦"
- **涉及模块**：channel-server/plugin.py, plugins/mode, plugins/sla

### P2 用例（锦上添花 / 可选）

#### TC-016: routing.toml 热重载

- **来源**：eval-doc-008 TC-V4-15
- **优先级**：P2
- **前置条件**：channel-server 运行；CLI 可写 routing.toml
- **操作步骤**：
  1. `zchat channel create ch-new --feishu-chat oc_new` 后 CLI 发 SIGHUP 给 server
  2. server 重新加载 routing
  3. 发 WS 消息到 ch-new
- **预期结果**：新 channel 消息正确路由
- **涉及模块**：channel-server/routing.py, server.py

#### TC-017: mode_changed event 广播到 bridge

- **来源**：eval-doc-008 TC-V4-14
- **优先级**：P2
- **前置条件**：feishu_bridge 订阅 event
- **操作步骤**：
  1. /hijack ch-1 → mode_plugin emit event
  2. ws_server 广播
  3. feishu_bridge on_ws_event 捕获
- **预期结果**：bridge 收到 `{type:"event", event:"mode_changed", channel:"ch-1", ...}`
- **涉及模块**：channel-server/ws_server.py, feishu_bridge/bridge.py

#### TC-018: 原 PRD US-2.2 占位+续写端到端

- **来源**：PRD AutoService-UserStories.md US-2.2
- **优先级**：P1
- **前置条件**：完整 stack：ergo + channel-server + feishu_bridge mock + 一个 fast-agent
- **操作步骤**：
  1. 模拟客户发复杂问题
  2. 观察第一条 IRC 消息
  3. 15s 内观察第二条 IRC 消息（编辑）
  4. 检查飞书 mock 的 update_message 调用
- **预期结果**：
  - 1s 内 agent 发占位（`__msg:uuid:稍等...`）
  - ≤15s 后 agent 发续写（`__edit:uuid:完整答案`）
  - bridge 收到 edit → 飞书 update_message 一次（非新发一条）
- **涉及模块**：端到端

#### TC-019: 原 PRD US-2.5 @人工 路径端到端

- **来源**：PRD US-2.5
- **优先级**：P1
- **前置条件**：ch-1 + fast-agent；operator 身份 ou_op 在路由表
- **操作步骤**：
  1. 客户发复杂问题（copilot mode）
  2. agent 在 IRC 发 `@ou_op 请接管 #ch-1`
  3. 验证 bridge 识别 @ → 推送 squad thread 提示
  4. operator 在 squad 回 /hijack
  5. 验证 mode_plugin 切 takeover
- **预期结果**：全链路闭环，客户侧不中断
- **涉及模块**：端到端

#### TC-020: 原 PRD US-2.6 角色翻转计接管次数

- **来源**：PRD US-2.6
- **优先级**：P1
- **前置条件**：audit_plugin 启动；takeover_count=0
- **操作步骤**：
  1. 执行 TC-019
  2. query takeover_count
- **预期结果**：takeover_count == 1；event role_flipped 带 triggered_by, from, to 字段
- **涉及模块**：plugins/mode, plugins/audit

---

## 统计表

| 类别 | 数量 | 说明 |
|------|------|------|
| **总用例** | 20 | |
| P0 | 10 | 核心路径，必须通过 |
| P1 | 8 | 重要边界 + PRD 对齐 |
| P2 | 2 | 锦上添花，条件允许时实现 |
| **来源：eval-doc** | 15 | 来自 eval-doc-008 的 TC-V4-01 ~ TC-V4-15 |
| **来源：PRD** | 3 | US-2.2 / US-2.5 / US-2.6 端到端 |
| **来源：复合场景** | 2 | TC-010 / TC-015 组合多个 eval 点 |
| **单元测试** | 12 | TC-001 ~ TC-009 + TC-011 ~ TC-013 |
| **集成测试** | 5 | TC-010, TC-014 ~ TC-017 |
| **E2E** | 3 | TC-018 ~ TC-020 |

## 风险标注

### 高风险区域
- **plugin.py 插件框架**：新概念，无历史实现参考；TC-005 / TC-006 / TC-015 是关键
- **router.py @prefix 决策**：从 Gate 算法迁移过来，容易漏掉 takeover 分支；TC-007 / TC-010 必须通过
- **feishu_bridge 命令分拣改变**：从硬编码 set 改为无分拣，content 原样透传；TC-006 / TC-008 验证

### 回归风险
- **现有 24 个 E2E** 大部分依赖 conversation/mode/squad，需重写。V4 不强求 100% 迁移，但 PRD 核心流程（US-2.1 ~ US-2.6）必保留端到端。
- **现有单元测试** 260+ 大部分随 engine/ 目录一起删。新写目标 80-120 个，覆盖更高但数量少。

### 覆盖未知
- **agent_mcp 原地不动** 但 `run_zchat_cli` 是新工具，需要新写 mock 测试
- **SLA timer asyncio 实现** 的并发安全，需要 stress test（本 plan 未覆盖，列为后续 follow-up）

### 预存失败不增约束
重构过程中保证：
- protocol 2 个预存失败（test_scoped_name_*）不变
- cs 1 个预存失败（test_auto_hijack）—— 如果 feishu_bridge 结构变化导致它变 pass 或 fail，需单独记录
- zchat 3 个预存失败（test_unreachable_server_raises / test_generate_layout_* / test_load_defaults）不变

---

## Review 摘要

- 总用例 20，P0 10 个，P1 8 个，P2 2 个
- 15 来自 eval-doc，3 来自 PRD，2 复合场景
- 覆盖 protocol 编解码、routing、plugin 注册、mode 决策、CLI 集成、端到端 PRD 流程
- 高风险区域：plugin.py / router.py / bridge 命令分拣
- 未覆盖：asyncio 并发 stress、webhook 边界、超长消息

## Next

用户 confirm → 状态改 confirmed → Skill 3 基于此 plan 产出 pytest 代码。
