# V6 收尾整合方案（confirmed scope）

> 2026-04-21 · 用户确认 V6 收尾的最终范围
>
> 作用：把分散在 `v6-help-request-notification-design.md` /
> `v6-placeholder-card-edit-design.md` / `v7-entry-as-coordinator.md` 三份 note
> 里**确实要在 V6 sprint 内做**的事收口到一处，明确**不做**的事和原因。
>
> 后续实施直接按本 note 的实现清单顺序推进。

## 1. 背景

V6 pre-release 测试（TC-PR-2.1 / 2.2 / 2.5）暴露 5 个根因：

1. **soul.md 决策树过长** → fast/deep/admin/squad 不可靠遵循
2. **template 没有 CLAUDE.md** → Claude Code 不自动加载 `soul.md`，依赖 MCP `instructions.md` 的弱间接（"read soul.md if exists"），长 soul 易被忽略
3. **`@operator` 求助** → sla plugin 启 timer 但不通知 operator，PRD US-2.5 失败
4. **routing.toml `agents` 字段** → 写死不维护，不被 router 用，但容易误导 reader
5. **router 没熔断** → entry agent 离线时消息无人接，无降级

第 1+2 是 **soul 拆 skills 重构**解决；第 3 是 **help_requested 通知链**；第 4+5 是 **router-level 改进**。

第 6 个根因（飞书 text 消息不可编辑 → PRD US-2.2 占位 edit 失败）需要 **占位卡片化方案**，但**本 V6 sprint 不做**（见 §4）。

## 2. 本次方案 · 必做 4 项

### §3.1 · 4 个 PRD agent template 重构成 soul + skills

**目标**：soul.md 砍到 ~25 行只描述人格 + 标准；决策树拆成 `.claude/skills/<name>/SKILL.md`。

**Claude Code skills 机制**（[官方文档](https://code.claude.com/docs/en/skills)）：
- `.claude/skills/<name>/SKILL.md` 带 YAML frontmatter `description`
- Claude 根据 description 关键词匹配当前任务自动加载 skill body
- 长 procedure 不占永久 context，触发时才装载，adherence 显著提升

**改动**（4 个 template，**不动 `templates/claude/` 基础模板**）：

```
templates/fast-agent/
├── soul.md                              # ~25 行：身份 / Voice / 边界 / 工具列表 / available skills 索引
└── skills/                              # 新增
    ├── delegate-to-deep/SKILL.md        # 占位 + __side:@deep + edit_of（PRD US-2.2）
    ├── escalate-to-operator/SKILL.md    # @operator side + 等候提示（PRD US-2.5）
    ├── handle-side-from-operator/SKILL.md # 无 @<me> 前缀的 __side: 采纳并 reply 客户
    └── handle-takeover-mode/SKILL.md    # mode_changed=takeover → 进副驾驶 only side

templates/deep-agent/
├── soul.md                              # ~25 行：身份 / 不直接面对客户 / edit_of 替换
└── skills/
    ├── handle-delegation/SKILL.md       # 收到 __side:@me edit_of=<uuid> → 查后 reply edit_of
    └── escalate-no-data/SKILL.md        # 查不到 → side 告诉 fast 走 @operator

templates/admin-agent/
├── soul.md                              # ~25 行：管理员助手身份
└── skills/
    ├── handle-status-command/SKILL.md   # /status → run_zchat_cli audit
    ├── handle-review-command/SKILL.md   # /review → 聚合报告
    ├── handle-dispatch-command/SKILL.md # /dispatch → agent create
    └── handle-natural-language/SKILL.md # 自然语言 → 意图识别 → 命令映射

templates/squad-agent/
├── soul.md                              # ~25 行：operator 工作空间助手
└── skills/
    ├── answer-status-query/SKILL.md     # operator 问对话状态 → run_zchat_cli + 格式化
    ├── handle-help-event/SKILL.md       # 收到 help_requested 系统事件 → 主聊播报
    └── handle-mode-event/SKILL.md       # mode_changed → 通知 operator
```

每个 SKILL.md frontmatter 模板：
```yaml
---
name: delegate-to-deep
description: Use when customer asks about order status, logistics, customs, inventory, or CRM data — anything needing backend lookup. Triggers placeholder + delegate to deep flow per PRD US-2.2.
---
[detailed playbook，从现 soul.md §复杂问题切过来]
```

**配套 start.sh 改动**（4 个）：
```bash
# 现有 soul.md cp 之后追加：
cp "$TEMPLATE_DIR/soul.md" ./soul.md
cp "$TEMPLATE_DIR/soul.md" ./CLAUDE.md           # ← 新增：让 Claude Code 自动加载 persona
mkdir -p .claude
if [ -d "$TEMPLATE_DIR/skills" ]; then           # ← 新增：拷贝 skills
  cp -r "$TEMPLATE_DIR/skills" .claude/skills
fi
```

**配套 settings.local.json 改动**（4 个 start.sh 的 jq 段）：
```jsonc
{
  // ... 已有字段
  "permissions": {
    "allow": [
      "mcp__zchat-agent-mcp__reply",
      "mcp__zchat-agent-mcp__join_channel",
      "mcp__zchat-agent-mcp__run_zchat_cli",
      "Skill"                                    // ← 新增：允许调用 skills
    ]
  }
}
```

**配套 instructions.md 改动**（`zchat-channel-server/instructions.md` §SOUL File 段）：
- 删 "At session start, read `./soul.md` if it exists" 那段
- 改成 "CLAUDE.md is auto-loaded; relevant skills auto-trigger by description"

**实施工具**：可用 `/skill-creator` 半自动生成 SKILL.md 骨架。

**工作量**：~1.5 人日（4 agent × 3-4 skill = 14 个 SKILL.md，内容是从现 soul.md 切的不是新写）。

### §3.2 · help_requested 通知链（PRD US-2.5）

详细方案见 `v6-help-request-notification-design.md` —— 本 note 不重复，只列实现清单：

| 模块 | 改动 |
|------|------|
| `src/plugins/sla/plugin.py` | 检测 `@operator` / `@人工` / `@admin` / `@客服` 时 emit `help_requested` event（保留原 180s timer） |
| `src/feishu_bridge/bridge.py` | customer bridge 首次见 conv 调 `get_chat_info` 拿群名，metadata 带 `customer_chat_name` |
| `src/feishu_bridge/bridge.py` | squad bridge 订阅 `help_requested` event → `update_card` 标 "🚨 求助中" + `reply_in_thread` 用 `<at user_id="all"></at>` |
| `src/feishu_bridge/feishu_renderer.py` | `build_conv_card` title 用 `metadata["customer_chat_name"]` 替代 `conv-001` 死号 |
| `src/feishu_bridge/bridge.py` | sender filter：忽略本 bot 自发消息（防回环） |
| `src/plugins/sla/plugin.py` | `help_timeout` event payload 带原文 text |

**0 operator_id 侵入**：用 `<at user_id="all"></at>` @所有人，bot 不需要知道 operator 具体身份，operator 离群/换人自动跟上。

**工作量**：~1.2 人日。

### §3.3 · Router 层熔断 + list_peers MCP 原语

详细方案见 `v7-entry-as-coordinator.md`（V7 主题部分提前到 V6 收尾做的子集）：

| 模块 | 改动 |
|------|------|
| `zchat-channel-server/src/channel_server/router.py` | `@entry` 前 check `entry in IRC NAMES`，不在则 emit `__zchat_sys:help_requested` 而不是空 @ |
| `zchat-channel-server/src/channel_server/irc_connection.py` | 暴露 channel members 查询接口（NAMES 缓存） |
| `zchat-channel-server/agent_mcp.py` | 新增 MCP tool `list_peers(channel) -> list[str]`，agent 可查同 channel 其他 nick（排除 cs-bot 等 service） |
| `templates/fast-agent/skills/delegate-to-deep/SKILL.md` | 委托前先 `list_peers()` 查 deep 是否在线，不在线 → 走 escalate-to-operator |

**注意**：保持 zchat / Socialware 边界。zchat 只提供 nick 列表原语，**不做** skill metadata 注册或工作流编排（那是 Socialware 的事）。

**工作量**：~0.7 人日（去掉 v7 note 里 routing.toml 清理部分，那放 §3.4）。

### §3.4 · routing.toml `agents` 死字段清理

| 模块 | 改动 |
|------|------|
| `zchat/cli/routing.py` | `join_agent` 不再写 `agents` 字段；保留 entry_agent 写入 |
| `zchat/cli/routing.py` | 删 `channel_agents` 函数 |
| `zchat-channel-server/src/channel_server/routing.py` | `ChannelRoute.agents` 字段删除；`load()` 不再读 |
| 既有 prod/ routing.toml | 手动清理已有 `[channels."#xxx".agents]` 段（CLI 无破坏性 migrate，手改即可） |
| tests | 删 `test_channel_agents` 测试用例 |

**工作量**：~0.2 人日。

## 3. 实施顺序（推荐）

1. **§3.1 skills 重构** —— 解 fast 不遵循 soul 的根因，让后面验证更快收敛
2. **§3.4 死字段清理** —— 同时进行，本来就该清的，不阻塞
3. **§3.2 help_requested 通知链** —— 解 TC-PR-2.5
4. **§3.3 router 熔断 + list_peers** —— 让 §3.1 的 `delegate-to-deep` skill 能查 peer

总工作量 **~3.6 人日**。

## 4. 不做的部分

### ❌ Placeholder 卡片化方案（`v6-placeholder-card-edit-design.md`）

**原因（用户 2026-04-21 决策）**：
> "_placeholder 的方案先不用改，这个涉及到三个仓库（zchat / zchat-channel-server / zchat-protocol），不好调试。"

**含义**：
- TC-PR-2.2 "客户看到一条占位消息就地替换成完整答复" 在 V6 收尾不验证
- fast → deep 委托链路本身仍然实现（§3.1 delegate-to-deep skill）；只是 deep 的 `__edit:` 在飞书侧实际不会替换占位（飞书 API 限制 + 当前 send_text 不可 patch）
- 替代体验：客户会看到 fast 的"稍等..." 文本 + deep 的最终答复 **两条独立消息**（不是 PRD 期望的"一条无缝替换"，但功能完整）
- **何时做**：V7 启动时单独排，三仓联调要专门挪一个 sprint

设计 note `v6-placeholder-card-edit-design.md` 保留，状态从 "V6 P10 待开发" 改为 "deferred to V7+"。

### ❌ 基础模板 `templates/claude/`

**原因（用户 2026-04-21 决策）**：
> "基础模板不用改。"

**含义**：
- `templates/claude/soul.md`（21 行通用 IRC chat 风格指引）保持原样
- `templates/claude/start.sh` 不加 CLAUDE.md cp、不加 skills cp
- 只有 4 个 PRD agent template（fast/deep/admin/squad）做 §3.1 重构
- 通用 `claude` agent 继续走"MCP instructions 弱间接 → agent 自己 read soul.md" 的老路径，简单场景够用

### ❌ V7 内容（除 §3.3 router 熔断外）

下列从 `v7-entry-as-coordinator.md` 移到 V7 sprint：
- 多 agent workflow chaining（翻译 → 查询 → 格式化）
- Socialware 接入 zchat soul.md
- skill metadata / role schema 等

下列从 `v7-roadmap-supervision.md` 留 V7：
- `supervises = ["tag:cs-customer", "pattern:conv-*"]` 复杂语法
- 多 squad 独立监管不同 customer 群组

## 5. 验收

V6 sprint 完成后预期通过：
- TC-PR-2.1 客户首响（已通过）
- TC-PR-2.2 fast → deep 委托（**不要求**就地替换；要求两条消息正确出现 + IRC 链路对）
- TC-PR-2.5 @operator 求助 → squad 群 @all 通知 + 卡片标"🚨 求助中"
- TC-PR-3.x admin 命令（依赖 §3.1 admin-agent skills）
- TC-PR-4.x squad 状态查询（依赖 §3.1 squad-agent skills）

## 6. 关联 note 状态更新

| Note | 原状态 | 新状态 |
|------|-------|-------|
| `v6-help-request-notification-design.md` | confirmed · 待开发 | confirmed · V6 收尾必做（§3.2） |
| `v6-placeholder-card-edit-design.md` | confirmed · 待开发 | **deferred to V7+**（用户决策跨仓难调试） |
| `v7-entry-as-coordinator.md` | confirmed · V7 启动 | router 熔断 + list_peers 提前到 V6 收尾（§3.3）；其余留 V7 |
| `v7-roadmap-supervision.md` | 设计期 | 不变（V7 主题） |
| `v6-prerelease-test-session2-note.md` | 16 bugs，多数已修 | 仍要 confirm §2.5 / §2.15 |

## 7. 状态

- **方案状态**：confirmed（用户 2026-04-21 拍板）
- **实施起点**：本 note 收口后即可启动 §3.1
- **生产工具**：用 `/skill-creator` 半自动生成 SKILL.md 骨架（用户提示）
- **归属阶段**：V6 P10（最终 sprint）
