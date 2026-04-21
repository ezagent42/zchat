# docs/discuss

按时间顺序编号的设计 / PRD / 测试计划 / sprint note。

| # | 文件 | 类型 | 状态 |
|---|---|---|---|
| 001 | [autoservice-prd](001-autoservice-prd.md) | PRD | v1.0 |
| 002 | [autoservice-user-stories](002-autoservice-user-stories.md) | User Stories | v1.0 |
| 003 | [autoservice-full-journey.html](003-autoservice-full-journey.html) | UI 原型 | — |
| 004 | [v5-refactor-plan](004-v5-refactor-plan.md) | 重构计划 | 已实施 |
| 005 | [v5-channel-server-spec/](005-v5-channel-server-spec/) | V5 spec（12 文档） | 已被 V6 吞入 |
| 006 | [v6-pre-release-test-plan](006-v6-pre-release-test-plan.md) | 真机验收计划 | 执行中 |
| 007 | [v6-prerelease-session2-note](007-v6-prerelease-session2-note.md) | sprint bug 记录 | 大部分已修 |
| 008 | [v6-finalize-plan](008-v6-finalize-plan.md) | V6 收尾方案 | ✅ 已实施 |
| 009 | [v6-help-request-notification-design](009-v6-help-request-notification-design.md) | help_requested 通知链 | ✅ 已实施 |
| 010 | [v6-placeholder-card-edit-design-SUPERSEDED](010-v6-placeholder-card-edit-design-SUPERSEDED.md) | 占位卡片方案 | ⚠️ 被 reply-to-placeholder 替代 |
| 011 | [v7-entry-as-coordinator](011-v7-entry-as-coordinator.md) | V7 entry-as-coordinator | 子集已实施（list_peers + NAMES 熔断） |
| 012 | [v7-roadmap-supervision](012-v7-roadmap-supervision.md) | V7 多实例监管扩展 | 设计期 |

## 编号规则

- 按**创建时间**递增，不按主题类型分桶
- 002-003 同属 PRD 套件（trilogy + journey）
- 005 是一个**目录**（12 份子 spec），整体保留
- 同时期同主题（V6 sprint）连续编号 007-010

## 历史归档

- 非本用户（upstream）提交的老设计 / plan → `../archive/`
- 用户本人的过期文档（V3/V4 Phase 0-8 / V5 老 design / 老 bug note）已**直接删除**，git history 可回溯

## 新增文档

下一份按 `013-<topic>.md` 续编号。
