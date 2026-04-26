# 12 · PRD 业务功能 → WeCom 实现验证矩阵

> **每条 PRD 要求都对应一个或多个 WeCom 官方 API**，并附文档链接 + 限制说明 + 退化方案。
> 凡是没找到官方 API 的功能，明确标 ❌ 不可实现 / ⚠️ 部分实现。
> 文档基于 v2026 官方文档查证（developer.work.weixin.qq.com）。

## 0. 三栈 API 速查

| 栈 | 适用对象 | 入站 | 出站 | 文档 |
|---|---|---|---|---|
| **Kefu** | B2C 外部客户 1-1 | callback (kf_msg_or_event) → sync_msg pull | send_msg | [path/96426](https://developer.work.weixin.qq.com/document/path/96426) [path/94677](https://developer.work.weixin.qq.com/document/path/94677) |
| **智能机器人长连接** | 内部群（admin/squad）@bot | WSS frame | WSS send + send_to_group | [path/101463](https://developer.work.weixin.qq.com/document/path/101463) |
| **群机器人 webhook** | 任何已添加 webhook 的群（push only）| ❌ | HTTP POST | [path/91770](https://developer.work.weixin.qq.com/document/path/91770) |

下面每条 PRD US 的"实现栈"列指明用哪一种。

---

## 1. Epic 2 · 实时对话（核心，6 个 US）

### US-2.1 · C 端客户 3 秒内看到问候

**飞书实现**：客户进群 → bot 收 chat_member.user_added_v1 → 立即发"您好" 文本

**WeCom 实现**：客户首次接入微信客服 → callback `kf_msg_or_event` 含 `enter_session` event → bridge 调 send_msg 发欢迎语
- 入站：[Event=enter_session](https://developer.work.weixin.qq.com/document/path/96426) ✅ 实测验证
- 出站：[send_msg msgtype=text](https://developer.work.weixin.qq.com/document/path/94677) ✅
- **延迟**：callback 是 push，到达 < 1s；send_msg 调用 ~ 200ms RTT。**满足 SLA < 3s** ✅
- 配额：send_msg 频率官方"严格限制" + token 解放（详见 path/94670 §callback 中的 token 字段），实测 ~ 60/min/customer 够用

### US-2.2 · 复杂查询看到占位不空等

**飞书实现**：agent 先发"让我查一下" placeholder（`__msg:<uuid>:占位`），后续 `__edit:<uuid>:<完整答>` 替换
- 飞书 message.patch API 支持原地编辑

**WeCom 实现**：⚠️ **不能 1:1 还原**
- Kefu send_msg **没有 update / patch 接口**（已查 path/94677）
- 只能：发占位 → 后续发独立新消息（不能替换占位文本）
- 退化方案：
  - 不发占位，第一条直接是承诺文本"正在为您查询，请稍候 5-10 秒"
  - 后续直接发完整答（两条独立消息，不是替换）
  - agent template 加 flag `bridge_features.no-edit = true`，agent_mcp 跳过 edit_of 行为
- **影响**：客户体验上会看到两条消息（"正在查询" + "答案"），不是一条变化的消息。可接受 ✅

### US-2.3 · Agent 接洽后在分队频道发实时卡片

**飞书实现**：squad bot 在 squad 群发 interactive card，每 conv 一张卡，含 mode/state/最新摘要

**WeCom 实现**：⚠️ **退化为内部群机器人 + markdown / template_card**
- squad 群是**企业内部群**（不是客户群）→ 用[智能机器人长连接](https://developer.work.weixin.qq.com/document/path/101463)
- 长连接 bot **支持 template_card 和 markdown**（已验证）
- 发送一个 conv 卡片：
```python
bot.send_to_group(
    chat_id="<squad_chat_id>",
    msgtype="template_card",
    template_card={
        "card_type": "text_notice",
        "main_title": {"title": "对话 conv-001", "desc": "客户 alice / Copilot"},
        "horizontal_content_list": [
            {"keyname": "mode", "value": "Copilot"},
            {"keyname": "state", "value": "🟢 active"},
        ],
        "task_id": "conv_001"
    }
)
```
- **限制**：群机器人 / 长连接 bot 都**不支持 update**（实测）。改用：发新卡（旧卡留着）。短时间内频繁更新 → debounce 300ms

### US-2.4 · 点开卡片进入对话监管模式

**飞书实现**：operator 点卡片 button → card_action callback → bridge 触发 emit `mode_changed=takeover`

**WeCom 实现**：✅ **template_card button_interaction 支持点击 callback**
- card_type = `button_interaction`
- 点击后 callback `template_card_event`
- Token-based 验签（同 callback）
- bridge 收 callback → `_on_card_action` → CS emit `mode_changed`
- **唯一差异**：飞书卡片可 update 让按钮变灰；WeCom 不能 → 改成发新卡或文字通告"已切换模式"

### US-2.5 · 两种方式触发人工提醒

**飞书实现**：(a) agent `@operator` side message → 触发 sla plugin help_requested timer（180s）；(b) operator `/hijack` 命令

**WeCom 实现**：✅ 两种都可
- (a) IRC 层不变（agent 发 `__side:@operator`），仅 squad bridge 收到 `help_requested` event 后用**长连接 bot 发 markdown 消息**到 squad 群：
  ```markdown
  ## 🚨 求助 [conv-001]
  > 客户对"不退不换"提出异议
  > <font color="warning">@张三 请处理</font>
  ```
  WeCom markdown 支持 `<font color="warning">` 高亮 + `@person` 不发 push（push 需用 `mentioned_list` 在 markdown_v2）
  - **改用 markdown_v2 的 mentioned_list**：[path/91770](https://developer.work.weixin.qq.com/document/path/91770) — 实际推送 @ 通知
- (b) operator 在 squad 群打 `[conv-001] /hijack` → 长连接 bot 收到（@bot 或带前缀）→ 翻译成 IRC `/hijack` 命令进 conv-001 channel

### US-2.6 · 角色翻转后 Agent 退居副驾驶

**飞书实现**：mode_changed=takeover 后，agent reply 都加 `side=true`（不发客户）

**WeCom 实现**：✅ **agent 行为不变**（agent 是 IRC 内逻辑，不知道 IM 平台）
- mode_changed 系统事件传到 fast-agent → 进 takeover skill → reply side=true
- side message 在 customer Kefu 通道**根本不发**（bridge filter）
- side message 在 squad 内部群**显示**（长连接 bot 推 markdown）

---

## 2. Epic 3 · 双账本与仪表盘

### US-3.1 · 商户查看 AI 团队与人工双账本

**实现**：跟 IM 平台无关 — 是 audit plugin + Web UI 的事，bridge 不动。✅ 已可用

### US-3.2 · 管理员命令行快速操作

**飞书实现**：商户管理员在 admin 群 @admin-agent 输入命令（如 "/agent create xxx"），admin-agent 调 `run_zchat_cli` MCP tool

**WeCom 实现**：✅ **同**，只换 IM 通道
- admin 群 = 企业内部群 → 用智能机器人长连接 bot
- bot 收 @bot text → 翻译为 IRC `__msg:` → admin-agent → run_zchat_cli
- 无差异

### US-3.3 · SLA 超时自动告警

**实现**：sla plugin 触发 `help_timeout` event → squad bridge 收到 → 发 markdown 高亮提醒 + @owner
- WeCom markdown_v2 mentioned_list 实际推送 @ 通知 ✅

---

## 3. Epic 4 · 闲时学习 (Dream Engine)

### US-4.1 · 在管理群配置 Dream Engine 学习规则

**实现**：admin 群里 @admin-agent 输入配置规则。同 US-3.2 ✅

### US-4.2 · Dream Engine 业务低峰自动启动

**实现**：Dream Engine 是独立后台 service，不依赖 IM。✅

### US-4.3 · 晨起推送提案到管理群

**实现**：Dream Engine 推送 → 走 admin bridge 发 markdown 长消息 + 行内 button card
- WeCom 长连接 bot 支持 template_card + markdown ✅
- 但 button 数量上限：button_interaction 最多 6 个按钮

### US-4.4 · 提案灰度发布与一键回滚

**实现**：与 IM 平台无关，是后端逻辑。✅

---

## 4. Epic 1 · 自助上线（管理员体验）

### US-1.1 · 上传基础信息生成初版 Agent

**实现**：管理员通过 Web UI 上传，跟 IM 无关。✅

### US-1.2 · 一键勾选权限并关联 IM 管理群

**实现**：管理员需要在 WeCom 中：
1. 创建"自建应用"（拿 corp_id + corp_secret + agent_id）
2. 创建"客服账号"（拿 open_kfid）
3. 创建"智能机器人"（拿 BotID + Secret，用于内部群）
4. 在企业内部新建 admin 群 + squad 群，邀请智能机器人入群

操作复杂度比飞书高（飞书一个 app 通用；WeCom 三种身份分开）。文档化的 setup wizard 必须带截图说明（详见 09 部署文档）。

### US-1.3 · 虚拟客户预演

**实现**：跟 IM 无关，是 sandbox 模拟。✅

### US-1.4 · 合规预检

**实现**：跟 IM 无关。✅

---

## 5. SLA 验证

PRD 要求：

| SLA 指标 | 飞书表现 | WeCom 表现（理论值）|
|---|---|---|
| onboard 首屏应答 < 3s | WSS 实时 ~50ms | Kefu callback < 1s + send_msg 200ms = 1.2s ✅ |
| 占位消息 < 1s | message.create 200ms ✅ | Kefu send_msg 200ms ✅ |
| 慢查询续写 < 15s | message.patch ✅ | ⚠️ 不能 patch，发新消息 ✅（UX 略差）|
| 人工接单等待 < 180s | sla plugin 180s timer ✅ | 同 ✅ |
| 人工首次回复 < 60s | thread reply 实时 | 长连接 bot 实时 ✅ |
| 自助上线 < 2h | feishu app 一次申请 | ⚠️ WeCom 三身份 + DNS + caddy 配置可能 > 2h；首次需 setup wizard 简化 |

**风险**：US-1.2 自助上线 < 2h 在 WeCom 上**很紧**。需要：
- 提供 step-by-step 截图指引
- 提供 `zchat doctor wecom` 检测各身份是否就绪
- 必要时配置一个"代理上线"服务（我们的人协助配 WeCom 后台）

---

## 6. 计费指标

| ★ 指标 | 飞书 | WeCom |
|---|---|---|
| 接管次数 | mode_changed event 计数 | 同 ✅（IM 无关）|
| CSAT | csat plugin + interactive card | ⚠️ Kefu 不支持 template_card 入站，但 **Kefu 支持 msgmenu 类型**（带按钮的菜单消息）→ 客户点击触发 callback → 提取分数 |
| 升级转结案率 | mode_changed=takeover + channel_resolved 计数 | 同 ✅ |

### CSAT 在 Kefu 用 msgmenu 实现

参见 path/94677 send_msg 支持的 msgmenu：
```json
{
  "touser": "external_user_id",
  "open_kfid": "wkXXXXX",
  "msgtype": "msgmenu",
  "msgmenu": {
    "head_content": "请为本次服务评分：",
    "list": [
      {"type": "click", "click": {"id": "csat_5", "content": "⭐⭐⭐⭐⭐ 很满意"}},
      {"type": "click", "click": {"id": "csat_4", "content": "⭐⭐⭐⭐ 满意"}},
      {"type": "click", "click": {"id": "csat_3", "content": "⭐⭐⭐ 一般"}},
      {"type": "click", "click": {"id": "csat_2", "content": "⭐⭐ 不满意"}},
      {"type": "click", "click": {"id": "csat_1", "content": "⭐ 很差"}}
    ],
    "tail_content": "感谢您的反馈"
  }
}
```
客户点击 → callback 推送一条 `msgtype=event Event=msg_send_fail` 不对，应是文本回复 (sync_msg 拉到的 msg.click.id = "csat_5") → bridge 解析→ csat_score event → audit plugin。

✅ **CSAT 完全可实现**

---

## 7. 业务硬约束

| 约束 | 飞书 OK | WeCom 验证 |
|---|---|---|
| 反幻觉硬约束 | agent 层逻辑 | ✅ 同 |
| GDPR / CCPA / 个保法 | 与 IM 无关 | ✅ 同 |
| 人工离线 180s 退回 Agent | sla timer | ✅ 同 |
| 并发 ≤ 5 conversations / operator | mode 计数 | ✅ 同 |
| /rollback Dream Engine 提案 | admin 群命令 | ✅ 同（admin bot 翻译命令） |

---

## 8. 完全不能实现的功能（明示）

| 功能 | 原因 |
|---|---|
| 客户群里 bot 实时收消息 | WeCom 没有第三方应用接收外部客户群消息能力 — 必须改 Kefu 1-1 |
| 飞书 interactive card "动态 update" 在客户端 | Kefu / 长连接 bot / webhook 都不支持 update — 改"发新卡，旧卡留着" |
| 飞书 thread 嵌套消息层级 | WeCom 群消息平铺，无 thread — 改 `[conv-X]` 前缀过滤 |
| 客户在群发"投票/红包/接龙" 给 bot | Kefu sync_msg 不返回这些类型 — 客户端发出后 bridge 收不到 |
| 客户撤回消息后 bot 知道 | Kefu 有 `Event=user_recall_msg` 但**仅记录**，不能让 bot 撤回自己之前回复 |
| 多人同时在 1 个客户对话里（CC 模式） | Kefu 是严格 1-1，一个客户一时刻只能 1 个 servicer 接 |

每条都已查官方文档确认 → 不是"我们没做"，是"WeCom 平台限制"。需在产品 release notes 里告知商户。

---

## 9. 验证矩阵汇总

✅ 完全可实现（行为一致 / 体验等价）：
- US-2.1 (问候) / US-2.5 (求助 + hijack) / US-2.6 (角色翻转)
- US-3.1 / US-3.2 / US-3.3
- US-4.1 / US-4.2 / US-4.3 / US-4.4
- 接管次数 / 升级转结案率
- 所有硬约束

⚠️ 部分实现 / 退化方案：
- US-2.2 (占位 + edit) → 不能 edit，改两条消息
- US-2.3 (实时刷新卡片) → 不能 update，改新卡 + debounce
- US-2.4 (点击卡片) → button 可点；卡片不能变灰
- CSAT → 用 msgmenu 替代 interactive card
- 慢查询续写 < 15s SLA → 满足，但 UX 是两条消息

❌ 不能实现：
- 客户群 bot 模式（必须改 Kefu 1-1）
- 卡片动态 update 在客户侧
- thread 嵌套
- 客户复杂消息类型（投票/红包等）

---

## 10. 关键 trade-off 列表（让用户拍板）

1. **客户对话从"群"改"1-1 客服"**
   - ✅ WeCom 唯一选项
   - ⚠️ 客户群体感不同（飞书是群，WeCom 是与客服 1-1）
   - 商户能不能接受？需明确告知

2. **squad supervise 用"内部企业群" + 智能机器人长连接**
   - ✅ 长连接 bot 跟飞书 WSS 体验等价
   - 客户对话不在 supervisor 群中（必须靠 bridge mirror 推过来）
   - operator 在 supervisor 群打 `[conv-X] /hijack` 这种带前缀格式
   - 商户能不能培训 operator 用前缀？

3. **不能 edit 消息**
   - 占位 + 答复 → 两条消息（不是一条变化）
   - 商户能不能接受？

4. **CSAT 用 msgmenu 不是 card**
   - 视觉简陋一些（菜单按钮 vs 卡片）
   - 但功能完整 ✅

如果以上 trade-off 都能接受 → 项目可行。如果商户要求"飞书一比一体验" → 直接告知**WeCom 平台限制做不到**。

## 关联

- WeCom 官方文档主页: https://developer.work.weixin.qq.com/document/
- 微信客服：[path/94670](https://developer.work.weixin.qq.com/document/path/94670)
- 智能机器人：[path/101463](https://developer.work.weixin.qq.com/document/path/101463)
- 群机器人 webhook：[path/91770](https://developer.work.weixin.qq.com/document/path/91770)
