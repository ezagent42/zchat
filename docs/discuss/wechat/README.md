# WeCom Bridge 迁移方案

> **目标**：把 zchat 现有飞书 (Feishu/Lark) bridge 完整迁移到企业微信 (WeCom / 微信工作台)，**不改 channel_server / agent / plugin / 主仓 CLI 任一行核心代码**。

> **分支**：`feat/bridge-wechat`
> **worktree**：`/home/yaosh/projects/zchat-bridge-wechat`

## ⚠️ 关键发现（已查官方 API 文档验证）

WeCom 跟飞书架构差异**极大**，没有单一 1:1 替代品。必须根据角色用**三套不同 API**：

| zchat 角色 | 飞书实现 | WeCom 实现 | 官方文档 |
|---|---|---|---|
| **客户对话** (B2C 外部客户) | bot 在客户群，WSS 收消息 | **微信客服 (Kefu)** — 1-1 模式，HTTP callback + sync_msg pull | [path/96426](https://developer.work.weixin.qq.com/document/path/96426) |
| **管理 / 内部群** (admin / squad) | bot 在内部群，WSS | **智能机器人长连接** — WSS 到 `wss://openws.work.weixin.qq.com`，支持 @bot | [path/101463](https://developer.work.weixin.qq.com/document/path/101463) |
| **单向通知** (报警 / 公告) | bot 发卡片 | **群机器人 webhook** — HTTP push only，支持 markdown / template_card | [path/91770](https://developer.work.weixin.qq.com/document/path/91770) |

### 这意味着什么

1. 飞书的"客户群里 bot"模型在 WeCom 里**不存在** — 客户跟 bot 必须 1-1 (Kefu)
2. 飞书的"squad 里所有 conv 卡片"模型可以**部分还原**，靠"内部群 + 智能机器人长连接"
3. supervise UX 必须重设计 — 客户 1-1 + supervisor 内部群桥接
4. CSAT / mode 切换 / 多 agent 等业务 PRD 要求必须 case-by-case 验证 → 详见 [12-prd-feature-matrix.md](12-prd-feature-matrix.md)

## 文档清单（按编号顺序读）

| # | 文件 | 内容 | 状态 |
|---|---|---|---|
| 00 | [README.md](README.md) | 总览 + 三栈架构图 | ✅ |
| 01 | [01-arch-overview.md](01-arch-overview.md) | 模块映射 + 红线复审（**待重写以反映三栈**）| 🟡 v1 草稿，需重写 |
| 02 | [02-event-callback.md](02-event-callback.md) | 客户对话：Kefu callback + sync_msg | 🟡 v1 假设单栈，需补 WSS bot 部分 |
| 03 | [03-outbound-api.md](03-outbound-api.md) | 出站：Kefu send_msg / WSS bot send / webhook 三选 | 🟡 v1 同上 |
| 04 | [04-message-types.md](04-message-types.md) | 入站消息 type 映射 | 🟡 需按 Kefu 的 sync_msg 返回字段重写 |
| 05 | [05-card-renderer.md](05-card-renderer.md) | 卡片：Kefu 不支持 template_card / WSS bot 支持 | 🟡 需改 |
| 06 | [06-bot-membership.md](06-bot-membership.md) | Kefu 客户进群事件 vs WSS bot 群成员事件 | 🟡 需改 |
| 07 | [07-credentials.md](07-credentials.md) | 凭证：Kefu (corp+secret+open_kfid) / WSS bot (BotID+Secret) | 🟡 需补 BotID |
| 08 | [08-supervise-flow.md](08-supervise-flow.md) | supervise UX：客户 Kefu + 内部 squad 群桥接 | 🟡 草稿假设单栈 |
| 09 | [09-deployment.md](09-deployment.md) | Caddy 反代 / 公网 callback / WSS 出站 | 待写 |
| 10 | [10-testing.md](10-testing.md) | 测试方案 | 待写 |
| 11 | [11-migration-phases.md](11-migration-phases.md) | 实施 phase | 待写 |
| 12 | [12-prd-feature-matrix.md](12-prd-feature-matrix.md) | **每个 PRD US 在 WeCom 的实现验证** | 🟢 优先写（用户最关注）|
| 13 | [13-erp-integration.md](13-erp-integration.md) | 接入 ERP（百联 / 用友 / 金蝶等）的可行路线 | 待写（用户额外要求）|

## 现状 → 重写计划

v1 文档（02-08）最初假设 WeCom 跟飞书一样有"客户群 + 一种 API"，写完后查官方文档发现错了。**正在按以下顺序重做**：

1. ✅ README 加架构纠正（本文）
2. 🟢 **12-prd-feature-matrix.md** 优先写 — 每个 PRD US 列 WeCom 实现路径，每条带官方文档链接验证
3. 🟢 **01-arch-overview.md** v2 重写 — 三栈架构 + 模块表
4. 🟡 02-08 各自小幅修订（不大改，加 "Kefu 用 X / WSS bot 用 Y" 分支）
5. 🆕 09/10/11 按新架构写
6. 🆕 13 ERP 集成

## 不在范围

- 不改 `channel_server/` (协议总线)
- 不改 `src/plugins/*`
- 不改 agent_mcp / agent templates
- 不删 `feishu_bridge/`（飞书继续支持）

## 关联

- PRD: `../001-autoservice-prd.md`
- User Stories: `../002-autoservice-user-stories.md`
- 当前 feishu_bridge: `zchat-channel-server/src/feishu_bridge/`
- 路由约束: `docs/guide/006-routing-config.md`
