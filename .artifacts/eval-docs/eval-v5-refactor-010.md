---
type: eval-doc
id: eval-doc-010
status: confirmed
producer: skill-5
created_at: "2026-04-20T00:00:00Z"
mode: simulate
feature: v5-channel-server-refactor
submitter: yaosh
related:
  - test-plan-011
  - code-diff-v5-phase1
  - code-diff-v5-phase2
  - code-diff-v5-phase3
  - code-diff-v5-phase4
  - code-diff-v5-phase5
  - code-diff-v5-phase6
  - code-diff-v5-phase7
  - code-diff-v5-phase8
  - code-diff-v5-phase9
  - code-diff-v5-phase10
  - code-diff-v5-phase11
  - e2e-report-v5-final-001
spec: docs/spec/channel-server-v5.md
plan: docs/discuss/plan/v5-refactor-plan.md
---

# Eval: V5 Channel Server 重构

## 基本信息

- 模式：模拟（pre-impl evaluation）
- 提交人：yaosh
- 日期：2026-04-20
- 状态：confirmed
- 基线：refactor/v4 分支 HEAD（commit 1f1233c）
- 目标分支：refactor/v4（同分支累积，11 phase commits）
- 设计文档：`docs/spec/channel-server-v5.md`
- 实施计划：`docs/discuss/plan/v5-refactor-plan.md`

## 重构动机

V4 之后做了一轮过度精简（commit 1f1233c），删除了：
- `commands/` 目录（4 个 slash command md）
- `join_channel` MCP tool
- audit / activation plugin
- `__zchat_sys:` agent 感知通道
- 一系列 PRD 必需的能力（求助 timer / CSAT 链路 / lazy create / entry_agent）

V5 任务：在保持 V4 架构红线（4 条）的前提下，**恢复被错删的能力 + 补齐 PRD 缺口**，并让 dev-loop 能产出可执行的 pre-release 证据。

## Feature 描述（11 phase 概要）

| Phase | 主题 | 关键产出 |
|-------|-----|---------|
| 1 | A 类清理 | 恢复 commands/ 4 文件、join_channel tool、deque 替换 set 修内存泄漏、删 auto-hijack 死代码 |
| 2 | soul.md 对齐 | 4 个 agent 模板 soul.md 只引用 reply / join_channel / run_zchat_cli |
| 3 | routing.toml schema | ChannelRoute 加 entry_agent / bot_id 字段；router 只 @ entry_agent；CLI 加 channel remove / set-entry |
| 4 | CS 动态 reload | routing_watcher.py 轮询 mtime 变化时 reload + JOIN/PART 差异 channel |
| 5 | __zchat_sys 通道 | router.emit_event 三路广播（WS + plugin + IRC sys）；agent_mcp 识别 sys 注入 |
| 6 | bridge 去跨层 + lazy create | feishu_bridge/routing_reader.py 用 tomllib 直读；bot_added → subprocess CLI 创 channel + agent |
| 7 | audit + activation 恢复 | plugins/audit/plugin.py 持久化 audit.json；plugins/activation/plugin.py 检测客户回访 |
| 8 | audit 仪表盘扩展 | 6 维度指标（首回复时长、CSAT 均值、升级转结案率、SLA 达成、接单等待、会话时长）+ zchat audit CLI |
| 9 | CSAT plugin | channel_resolved → emit csat_request；__csat_score:N → audit.record_csat |
| 10 | sla help timer | 检测 __side: 中 @operator/@人工/@admin → 启动 180s help timer；超时 emit help_timeout |
| 11 | admin-agent 命令完整 | soul.md 三命令：/status /review /dispatch 全部走 run_zchat_cli |

## 设计原则（硬约束 / 红线）

- 红线 1：agent-mcp 不 import CS / bridge 代码
- 红线 2：bridge 不 import CS 代码（只 import protocol + tomllib）
- 红线 3：CS / plugin 核心不含外部平台业务语义（admin/squad/customer/feishu 字样）
- 红线 4：routing.toml 是整个系统唯一的动态运行时持久化；CLI 是唯一写入方

## PRD 对齐校验

| PRD US | V5 覆盖 | 状态 |
|--------|--------|------|
| US-2.1 三秒问候 | Phase 6（懒创建）+ Phase 3（entry_agent） | ✓ 架构支持 |
| US-2.2 占位 + 编辑 | __msg + __edit（已有） | ✓ |
| US-2.3 客服群卡片 + thread | bridge 已实现（保留） | ✓ |
| US-2.4 草稿模式 | 不做 | × 范围外 |
| US-2.5 Agent 求助 + 180s timer | Phase 10 | ✓ |
| US-2.5 operator /hijack | mode plugin（已有）+ Phase 5 IRC sys 通知 | ✓ |
| US-3.1 双账本仪表盘 | Phase 7 + Phase 8 | ✓ |
| US-3.2 /status /dispatch /review | Phase 8 + Phase 11 | ✓ |
| US-3.3 5min 滚动平均 | 不做 | × 范围外 |
| CSAT 评分链路 | Phase 9 | ✓ |
| 老客户回访 | Phase 7 activation plugin | ✓ |
| US-4.x Dream Engine | 不做 | × 范围外 |

## 测试用例汇总（详见 test-plan-011）

11 个 phase 共定义 ~50 个 testcase，分布在：
- `tests/unit/`：21 文件（含 Phase 1-11 新增 5 文件 + 已有 16 文件改动）
- `tests/e2e/`：4 文件（test_bridge_lazy_create / test_csat_lifecycle / test_help_request_lifecycle / test_plugin_pipeline）

## Pre-release 测试覆盖（除人工真机以外的所有自动化场景）

参见 `docs/spec/channel-server-v5.md §10` 完整消息流转：
- 10.1 新飞书群 → 懒创建 → e2e: test_bridge_lazy_create
- 10.4 Agent 求助 operator → e2e: test_help_request_lifecycle
- 10.6 对话结束 + CSAT → e2e: test_csat_lifecycle
- 10.5 人工接管 → unit: test_router (mode + sys broadcast 路径)
- 10.7 管理命令 → unit: test_admin_commands_via_cli
- routing 动态 reload → unit: test_routing_watcher
- 飞书 SDK 6.3 真机部分仅人工，CI 无法跑

## 验收门槛

- [x] 全量 unit 测试通过零跳过零失败
- [x] e2e 测试无失败（不需要真实 ergo / 真实飞书 SDK 的部分）
- [x] 4 条红线 grep 检查全部 clean
- [x] 死代码 grep 检查全部 clean（is_operator_in_customer_chat / send_side_message / agent_nick_pattern / query_status() / query_review() / query_squad() / assign_agent() / reassign_agent()）
- [x] commands/ 4 文件存在且 settings whitelist 一致
- [x] 6 个 plugin 全部注册（mode / sla / resolve / audit / activation / csat）
- [x] 3 个 MCP tool 注册（reply / join_channel / run_zchat_cli）
- [x] dev-loop 证据链落盘（本 eval-doc + test-plan + 11 code-diff + 11 test-diff + 1 e2e-report）

## 链接

- spec：docs/spec/channel-server-v5.md
- plan：docs/discuss/plan/v5-refactor-plan.md
- test-plan：.artifacts/test-plans/plan-v5-refactor-011.md
- code-diff（每 phase 一份）：.artifacts/code-diffs/diff-v5-phase{1..11}.md
- test-diff（每 phase 一份）：.artifacts/test-diffs/test-diff-v5-phase{1..11}.md
- e2e-report：.artifacts/e2e-reports/report-v5-final-001/
