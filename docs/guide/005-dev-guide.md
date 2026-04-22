# 005 · 开发指南 (Q&A)

> 红线优先 / 问题归位优先。每个 Q 给：判断方法 + 改哪里 + 不改哪里 + 为什么。

## 红线总则

```
agent_mcp.py     ─────╮
                      │  禁止互相 import
feishu_bridge/   ─────┤
                      │
channel_server/  ─────┤  只允许 import zchat-protocol
                      │
zchat-protocol/  ─────╯  独立，无外部 import
```

**业务术语红线**：`channel_server/` + `zchat-protocol/` + `zchat/cli/`（除 templates/）禁止出现 `customer / operator / admin / squad / feishu` 等业务命名。

---

## Q1 · 客户消息进 agent 后没收到 / 路由错误

**判断**：
1. `cs.log` 是否有 `[router] → IRC #conv-xxx: @yaosh-xxx __msg:...`?
2. `bridge-customer.log` 是否有入站 message + 转 WS?
3. WeeChat `#conv-xxx` 是否看到 cs-bot 的 `@nick __msg:` 行?

**改哪里**:
- 路由错误（@错 agent / 没 @）→ `zchat-channel-server/src/channel_server/router.py`
- bridge 没翻译 → `zchat-channel-server/src/feishu_bridge/bridge.py::_on_message`
- 协议编码出错 → `zchat-protocol/zchat_protocol/irc_encoding.py`

**不改哪里**:
- ❌ `agent_mcp.py` —— agent 是消息消费者不是生产者，路由问题不在这层
- ❌ template `soul.md` —— soul 不能修复路由，只能影响 agent 选择什么 skill

**为什么**：消息层和 agent 行为层严格分离。Router/bridge bug 必须在 server 层修，agent 模板不背锅。

---

## Q2 · agent 行为不对（不该 escalate 转人工却转了）

**判断**：
1. WeeChat 看 agent 实际发的消息（是不是 `__side:@operator ...`？）
2. agent workspace 的 `CLAUDE.md` 和 `.claude/skills/` 内容对吗？

**改哪里**:
- skill 触发条件不准 → `zchat/cli/templates/<agent>/skills/<name>/SKILL.md` 的 `description` (frontmatter)
- skill 步骤错 → 同 SKILL.md 的 body
- 多个 skill 冲突 → 重新分桶 + 在 description 里写明"only when X NOT Y"

**不改哪里**:
- ❌ `channel_server/` 任何代码 —— router 不感知 agent 决策
- ❌ plugin —— plugin 是被动响应消息/事件，不决定 agent 行为
- ❌ `agent_mcp.py` —— MCP tool 是基础能力（reply / list_peers），不写业务规则

**为什么**：agent 决策 = persona (CLAUDE.md) + workflow (SKILL.md) + Claude 模型本身。一切业务规则都在 template 层，不入 core。

修后**必须重启 agent**（Claude Code session 启动时一次性加载 CLAUDE.md/skills）：
```bash
cp -r zchat/cli/templates/<agent>/{soul.md,skills/} ~/.zchat/projects/<proj>/agents/<nick>/
cp zchat/cli/templates/<agent>/soul.md ~/.zchat/projects/<proj>/agents/<nick>/CLAUDE.md
zchat agent restart <name>
```

---

## Q3 · 想加新 sys 事件（如 `subscription_expired`）

**判断**：是 plugin 自然 emit（响应消息/事件），还是 bridge 入站新事件？

**改哪里**:
- plugin emit → 在对应 plugin (如新建 `plugins/subscription/plugin.py`) 里 `await self._emit_event("subscription_expired", channel, data)`
- bridge 翻译外部事件 → `bridge.py::_on_message` 之类的入站 handler 里 `self._bridge_client.send(ws_messages.build_event(...))`
- agent 收到后行为 → `templates/<agent>/skills/handle-subscription-expired/SKILL.md`

**不改哪里**:
- ❌ `router.py` —— router emit_event 是通用 3 路广播（plugin + WS + IRC sys），新 event name 不需要它认识
- ❌ `zchat-protocol/ws_messages.py` —— event name 是 string，不入 schema
- ❌ `irc_encoding.py` —— `__zchat_sys:` 前缀通用，event 内容随便填

**为什么**："channel + 消息格式" 二元抽象。新 event 是数据，不是新通道。

---

## Q4 · 想加新 plugin（如"自动翻译"）

**改哪里**:
- 新建 `zchat-channel-server/src/plugins/translate/{__init__.py,plugin.py}`
- `plugin.py` 继承 `channel_server.plugin.BasePlugin`，实现 `on_ws_message(msg)` / `on_ws_event(event)` / `handles_commands()`
- 在 `channel_server/__main__.py:80+` 一行 `registry.register(TranslatePlugin(...))`

**不改哪里**:
- ❌ `router.py` —— plugin registry 已通过 `broadcast_message/broadcast_event` 接所有 plugin，新 plugin 自动接入
- ❌ 其它 plugin —— plugin 之间不互相 import，只通过 emit_event 事件总线通信

**约束**：
- plugin 不能 import `feishu_bridge` 或具体业务模块
- plugin 内部用业务术语（如 `audit` 用 `customer_returned`）作为 event payload key 是允许的；但 plugin 名字 + 类名要中性

---

## Q5 · 想加新外部平台（Slack/Discord/...）

**改哪里**:
- 完整新建 `zchat-channel-server/src/<platform>_bridge/` 目录
- 参考 `feishu_bridge/` 复制结构（bridge / outbound / sender / group_manager / routing_reader / renderer）
- 新建 `zchat <platform> bot add` CLI 命令在 `zchat/cli/app.py` 注册（如果 bot 注册参数和飞书不同）

**不改哪里**:
- ❌ `channel_server/` —— bridge 通过 WS 协议接入，CS 不感知具体平台
- ❌ `agent_mcp.py` —— agent 只看到 IRC 消息，不知道哪个平台
- ❌ 其它 bridge —— 完全独立

**约束**：
- 新 bridge **必须**自己写 `routing_reader.py` 独立解析 routing.toml（红线：bridge 不依赖 CS routing 模块）
- 新 bridge 注册时 `bridge_type="<platform>"`，instance_id 唯一
- 出站 `kind="edit"` 语义：飞书是 reply-to-placeholder（API 限制），其它平台可以是真 patch（如 Slack `chat.update`）

详情参考 `004-migrate-guide.md`。

---

## Q6 · 想加新 MCP tool（agent 能调）

**改哪里**:
- `zchat-channel-server/agent_mcp.py` `register_tools()` 加 Tool 定义 + handler
- `zchat-channel-server/instructions.md` 列入工具表（Claude Code 默认加载 MCP server instructions）

**不改哪里**:
- ❌ template `soul.md` 别硬编码 tool 命令；让 Claude 自己根据 description 决策
- ❌ 不要在 plugin 里加 tool —— plugin 是 server 端被动响应，tool 是 agent 端主动调用

**约束**：
- Tool 必须在 `templates/*/start.sh` 的 `settings.local.json.permissions.allow` 列表里加白名单（否则 Claude Code 启动时阻塞等用户确认）

---

## Q7 · routing.toml 改动了 CS 没反应

**判断**：`grep -i "routing reloaded" ~/.zchat/projects/<proj>/cs.log | tail`

**改哪里**:
- watcher 没监听到 → `zchat-channel-server/src/channel_server/routing_watcher.py`（mtime 轮询）
- watcher 检测到了但路由没更新 → `router.py::update_routing()` 接收逻辑

**不改哪里**:
- ❌ 改 `routing.toml` 直接重启 CS（重启会破坏 reload 机制的正确性，也丢历史 IRC 连接）
- ❌ 在 plugin 里读 routing.toml —— 路由是 router 职责，plugin 只读自己的 state

---

## Q8 · 飞书 API 行为不对（卡片 patch 不刷新 / 消息 edit 失败）

**判断**: bridge log 是 200 成功但 UI 不更新（PATCH ok 但客户端不 refresh），还是 API 直接报错？

**改哪里**:
- API 包装 → `zchat-channel-server/src/feishu_bridge/sender.py`
- 业务路由（kind=msg/side/edit 怎么映射）→ `outbound.py::route()` / `on_edit()`
- 卡片 JSON → `feishu_renderer.py`
- 卡片必须有 `config.update_multi: true` 才能 patch 刷新（V6 phase 7 教训）

**不改哪里**:
- ❌ `channel_server/` —— 飞书 API 兼容性是 bridge 的事，CS 不知道
- ❌ `zchat-protocol/` —— 协议编码不感知飞书 SDK 限制

**典型 trap**：飞书 PATCH 对 card shape 大改不刷 UI → 改用 recall + resend 策略（参考 phase 7 CSAT 实现）。

---

## Q9 · agent 启动卡在确认 prompt 要手动按 Enter

**判断**：是 Claude Code 新版改了 prompt 措辞？

**改哪里**:
- `zchat/cli/agent_manager.py::_auto_confirm_startup` 的 `confirm_patterns` 列表加新关键词

**不改哪里**:
- ❌ template start.sh —— 启动命令本身没变
- ❌ Claude Code 升级（不是你的项目）

---

## Q10 · 死代码堆积 / 想清理

**步骤**:
1. 跑 dev-loop Skill 0 (`/project-builder`) 重生 `.artifacts/bootstrap/module-reports/`
2. 用 subagent 按模块深扫，产出 issues list（参考 R1 的 3 个 subagent prompt）
3. 按"高价值低风险"分批清，每批后跑全测试
4. 不删的就**加 inline 注释**：`REMOVED <date>: <name>. Reason: ... Restore: ...`（参考 `paths.py` / `runner.py` / `template_loader.py` V6 R4 注释格式）
5. 至少 3 轮 ralph-loop 收敛验证

**不改**:
- ❌ 别删测试只为了过 lint —— 测试反映真实使用场景，删测试就是删需求
- ❌ 别删 `zchat-protocol/*` 的 public API —— 它是协议合同，删除影响所有 bridge 实现

---

## Q11 · 想加 audit 新指标（如"平均响应时长"）

**改哪里**:
- `zchat-channel-server/src/plugins/audit/plugin.py` 加字段 + on_ws_message 时记录时间
- `zchat/cli/audit_cmd.py::_compute_aggregates` 加聚合计算

**不改哪里**:
- ❌ 别让 audit 跨 plugin 调用 —— audit 只看自己 plugin 收到的 event
- ❌ 别在 router 加埋点 —— 指标采集是 plugin 的事，router 只路由消息

---

## Q12 · 想加 IRC 直接 DM（agent 之间私聊）

**判断**：真的需要吗？大多数"协同"场景用 channel + `@nick` 已经够：

```
fast 在 #conv-001 发: __side:@yaosh-deep-001 请查 #12345 ... edit_of=<uuid>
deep 收到（mention 触发）→ 处理 → reply edit_of
```

如果**确实**需要 1:1 私聊（不让 channel 其它 agent 看到）：

**改哪里**:
- `irc_connection.py` 加 `on_privmsg` handler + `add_global_handler("privmsg", ...)`（当前仅 `on_pubmsg` 订阅 channel PRIVMSG；DM wiring 历史上从未实装，见 git log）
- `router.py` 加 DM 路由分支：target 是 nick 而不是 #channel 时走不同路径
- `agent_mcp.py` 加 DM 入站处理 + 新 MCP tool `dm(nick, text)`

**不改哪里**:
- ❌ 别用 channel + invite-only 模拟 DM —— 配置膨胀
- ❌ zchat-protocol 不需要新前缀（DM 还是 `__msg:` / `__side:`，target 区别在 IRC 层）

**当前状态**：V6 仅支持 channel PRIVMSG (`on_pubmsg`)，无 DM 入口；V7 真做 DM 时 router + agent_mcp + irc_connection 三处都要动，不只加 handler。

---

## Q13 · agent 想互相发现（"deep 在不在 channel"）

**已有机制**：

```python
# 在 agent 的 SKILL.md 里:
peers = list_peers(channel="#conv-001")
# 返回 ["yaosh-deep-001", "yaosh-fast-001"]，已剔除 self + 服务 nick
deep_peer = next((p for p in peers if "-deep-" in p), None)
```

`list_peers` 是 MCP tool（`zchat-channel-server/agent_mcp.py` 注册），底层查 `state["members"]` dict（由 irc_connection 的 `_on_namreply` / `_on_join/part/quit/nick` 维护并通过 `_publish_members` 镜像到 agent_mcp 的 state）。

**不要做**：
- ❌ 通过 routing.toml 查 agent 列表 —— V6 起 routing 不存 channel→agents 列表（roster 由 IRC NAMES 实时反映）
- ❌ 在 agent 之间约定 nick 命名做"硬编码 peer"（如 fast 总假定 deep-001 存在） —— 用 list_peers 动态发现，找不到就走 fallback skill

---

## Q14 · 测试坏了 / E2E 卡死

**判断**：unit 还是 e2e？是新代码引起的回归还是 fixture 老化？

**改哪里**:
- 新代码导致 E2E 失败 → 看是不是 V6 重构后 fixture 的 protocol 字段没同步（参考 `tests/e2e/test_csat_lifecycle.py` 改 `csat_score` event 通道的例子）
- E2E 跑超时 → 加 `--timeout 600`（CS env spin-up 慢）
- 飞书相关 E2E 启动失败 → bridge fixture 在 `tests/pre_release/` 已删（V6 重构后），下版重写

**不改哪里**:
- ❌ 不要为了让测试过而改业务代码 —— 先理解测试期望什么
- ❌ 不要 skip 测试当作"修了" —— skip = 删需求

---

## Q15 · 想加自定义 runner（如 OpenAI / Claude API 直连）

当前 zchat 只支持 Claude Code。要加其它：

**改哪里**:
- `zchat/cli/runner.py` 重新加回 `resolve_runner` + `list_runners`（V6 R4 删了，inline 注释里有 4 步重启计划）
- `zchat/cli/agent_manager.py::_spawn_tab` 改用 `resolve_runner` 而不是 `_resolve_template_dir`
- 在 `zchat/cli/app.py` 注册 typer 子命令 `zchat runner add/list/remove`
- 给每个 runner 写适配 MCP server（zchat-agent-mcp 现在内置了 Claude 流，新 runner 要写新的 stdio MCP）

**约束**：MCP server 必须暴露 `reply` tool 才能让 agent 发 IRC 消息回 channel。

---

## 总原则

| 直觉 | 反向校验 |
|---|---|
| "这个改动只动一处文件能解决" | 一般是对的；如果要改 3+ 文件，可能跨了红线，重新设计 |
| "在 channel_server 里加点业务" | **stop**。业务进 plugin 或 bridge |
| "在 agent 模板里写 if customer_id == 123" | **stop**。业务规则进 bridge / DB，不进 agent prompt |
| "在 plugin 里 import bridge" | **stop**。plugin 只 emit event，bridge 自己订阅 |
| "在 protocol 加新前缀" | 99% 不需要。先看现有 4 种前缀能否表达 |

## 关联

- 架构: `001-architecture.md`
- 协议层: `zchat-protocol/zchat_protocol/`
- 红线变更历史: git log + `.artifacts/eval-docs/eval-r2-r5-cleanup-013.md`
- 迁移到 zchat: `004-migrate-guide.md`
