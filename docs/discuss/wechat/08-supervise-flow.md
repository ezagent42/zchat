# 08 · Supervise 模式 — squad 监管 customer 群

## 1. 飞书 supervise 的 UX 形态

`feishu_bridge` 的 squad supervisor 模式：当 squad bot 的 `supervises = ["customer"]`，意味着 squad bridge 也订阅 customer bot 的所有 channel 消息。

**飞书具体形态**：
- squad 群里为每个 customer conv 建一张**主对话卡片** (`build_conv_card`)，含 chat_name / mode / state
- 客户每条消息 → squad bridge 把消息**镜像到主卡片下的 thread**（`reply_in_thread_sync(card_msg_id, text)`）
- 求助通知 (`help_requested`) → `update_card` 把卡 mark 红 + thread 里 `@operator <求助文本>`
- mode 变化 (`mode_changed=takeover`) → update 卡片 mode 标
- conv 结束 → update 卡片 state="resolved"

依赖飞书三个能力：
- ✅ Interactive Card 可 update
- ✅ message reply API 可指定 thread parent
- ✅ thread 嵌套展示

## 2. WeCom 的限制

| 飞书能力 | WeCom 状态 |
|---|---|
| 卡片 update | ❌ 群卡不能 update（详见 05）|
| message reply 指定 parent | ❌ 无 thread 概念，所有消息平铺 |
| thread 嵌套 UI | ❌ 群消息 UI 是单一时间线 |

→ **完全 1:1 还原 thread 不可能**。需要退化方案。

## 3. 三种退化方案

### 方案 A · 平铺 + 标签前缀（推荐）

squad 群里每条镜像消息加 `[<conv_id>]` 前缀：

```
squad 群（WeCom）:
  09:23 [conv-001] 客户 alice: 你好
  09:23 [conv-001] 🤖 fast-001: 您好，请问有什么可以帮您？
  09:24 [conv-002] 客户 bob: 物流查询...
  09:24 [conv-001] 客户 alice: 我想退货
  09:25 [conv-001] 🚨 求助：客户提退货异议
```

优点：
- 实现简单（拷飞书的 reply_in_thread 改成 send_text 加前缀）
- WeCom 客户端搜索 `[conv-001]` 能筛选某个 conv 全部消息

缺点：
- 多 conv 并发时混杂（要靠 operator 用 search 过滤）
- 没有"卡片"的全局状态视图

### 方案 B · 一 conv 一群（重）

新建一个 conv → 自动新建一个 squad 子群，把所有 supervisor 拉进去 + bot 拉进去 → 该子群专属这个 conv。

优点：
- 完全隔离，operator UX 接近 thread
- 卡片 / 消息都能 update（在子群内）

缺点：
- WeCom 不允许程序自动建群（除"客户群"模式外）
- 即使能建，operator 同时被拉 N 个群很烦
- conv 结束后子群清理麻烦

→ **不推荐**

### 方案 C · 平铺 + 定期发"状态汇总"卡（中间）

平铺方式发消息（同 A），但每 5 分钟 / 每 10 条新消息发一张"汇总卡"列出活跃 conv 状态：

```
squad 群（WeCom）:
  ... (大量平铺消息)
  09:30 📊 活跃对话汇总
       conv-001 alice  🟢 mode=copilot
       conv-002 bob    🚨 求助中 5min
       conv-003 carol  ✅ 已解决
```

优点：
- 既有平铺细节又有概览
- 不依赖 update（每次发新卡，旧卡作废）

缺点：
- 实现稍复杂（需要 timer + 状态聚合）
- 发频率高刷屏，频率低看不到实时

### 选择：先做 A，根据 operator 反馈决定要不要加 C

A 是 MVP，C 是优化项。Phase A 落地（详见 11）。

## 4. 方案 A 实现要点

### 4.1 outbound.py 改造

`feishu_bridge/outbound.py` 的 supervise 路径调用 `sender.reply_in_thread_sync(card_msg_id, text)`。

wecom 把这条改成：
```python
def _supervise_message_to_squad(self, conv_id: str, sender: str, body: str) -> None:
    squad_chat_id = self.bridge_config.supervise_squad_chat_id  # routing.toml 配
    formatted = self._format_supervise_line(conv_id, sender, body)
    self.sender.send_text_sync(squad_chat_id, formatted)


def _format_supervise_line(self, conv_id: str, sender: str, body: str) -> str:
    """格式：[<conv_short>] <icon><sender>: <body>"""
    short = conv_id[:8]
    if sender.startswith("voice-"):
        icon = "📞"
        clean_sender = sender[6:]
    elif sender.startswith("ww") or "@" in sender:
        icon = "👤"
        clean_sender = sender
    else:
        icon = "🤖"
        clean_sender = sender
    return f"[{short}] {icon} {clean_sender}: {body}"
```

### 4.2 conv_card 改成"开场卡"

每个新 conv 第一次出现时发一张开场卡（不再 update）：

```python
def on_new_conversation(self, conv_id: str, metadata: dict) -> None:
    """新 conv → squad 群发开场卡 + 起 thread tracking。"""
    card = wecom_renderer.build_conv_card(conv_id, metadata,
                                          mode="fast", state="active")
    msg_id = self.sender.send_card_sync(self.squad_chat_id, card)
    # 不存 card_msg_id 给后续 update（WeCom 群卡不能 update）
    # 仅作为视觉 marker 让 operator 知道有新 conv 进来
```

### 4.3 mode_changed 处理

```python
def on_mode_changed(self, conv_id: str, mode: str, **_kw) -> bool:
    line = f"[{conv_id[:8]}] ⚙️ 模式切换 → {mode}"
    self.sender.send_text_sync(self.squad_chat_id, line)
    return True
```

简单一条文本通告，不再 update 卡片。

### 4.4 help_requested

```python
def _supervise_help_requested(self, conv_id: str, data: dict) -> None:
    text = data.get("text") or "客户求助"
    line = f"[{conv_id[:8]}] 🚨 求助 @operator\n{text}"
    self.sender.send_text_sync(self.squad_chat_id, line)
```

跟飞书相比少了：
- 卡片 mark 红
- thread 嵌套展示

补偿：
- 表情符号 🚨 在 WeCom 客户端能引起 operator 注意
- text 带 @operator 字符（WeCom 群里 @ 仅 visual，无 push 通知；但 operator 习惯看 🚨）

如果 operator 反馈通知不够强 → 后续可以加 `markdown` 类型消息（WeCom 支持），加颜色和加粗。

### 4.5 客户消息镜像

```python
def _handle_supervised_message(self, conv_id: str, msg: dict) -> None:
    sender_source = msg.get("source", "")
    content = msg.get("content", "")
    # 客户消息（飞书 chat_id 形如 ou_xxxx）vs agent 回复（nick 形如 yaosh-fast-001）
    line = self._format_supervise_line(conv_id, sender_source, content)
    self.sender.send_text_sync(self.squad_chat_id, line)
```

## 5. squad_chat_id 配置

routing.toml 加 `supervise_squad_chat_id`：

```toml
[bots.squad-wecom]
type = "wecom"
credential_file = "credentials/squad-wecom.json"
default_agent_template = "squad-agent"
supervises = ["customer-wecom"]
supervise_squad_chat_id = "wm_squad_xxxx"   # ← 新字段，squad operator 群 chat_id
```

读取在 `routing_reader.read_bot_config`。

## 6. operator 反向操作 (squad → customer 镜像)

operator 在 squad 群里发 `__side:` 类指令需要走回 IRC。但因 squad 群是平铺，operator 怎么指定哪个 conv？

**约定**：operator 在 squad 群里发消息必须 `[<conv_short>] <text>` 前缀，否则消息忽略。

squad bridge 的 _on_message：
```python
async def _on_message(self, msg: dict) -> None:
    chat_id = msg.get("ChatId")
    if chat_id != self.config.supervise_squad_chat_id:
        # 客户群消息照常走（详见 03）
        await self._handle_customer_msg(msg)
        return

    # squad 群消息 — 必须 [conv_short] 前缀
    content = msg.get("Content", "").strip()
    m = re.match(r"^\[([a-f0-9]{8})\]\s+(.+)", content, re.DOTALL)
    if not m:
        log.debug("squad msg without [conv_short] prefix; ignored")
        return
    conv_short = m.group(1)
    body = m.group(2)
    conv_id = self._lookup_conv_by_short(conv_short)
    if not conv_id:
        log.warning("unknown conv_short=%s in squad msg", conv_short)
        return

    # 把 body 当作 __side: 内容（按 fast-agent soul 设计这是 operator 给 agent 的私密协商）
    side_msg = ws_messages.build_message(
        channel=conv_id,
        source=msg.get("FromUserName", "operator"),
        content=f"__side:{body}",
    )
    self._cs_client.send(side_msg)
```

operator 在 WeCom squad 群打 `[abcd1234] 不退不换` → squad bridge 翻译成 IRC `__side:不退不换` → 进 conv-abcd1234 channel → fast-agent 收到，按新 soul.md 逻辑回 side 不主动转客户 (详见之前 #82 fix)。

## 7. _lookup_conv_by_short

```python
def _lookup_conv_by_short(self, short: str) -> str | None:
    """根据 conv_id 前 8 字符 反查完整 channel 名 (含 #)。"""
    for full in self._mappings.values():    # full 形如 "conv-669ca17b"
        if full[:len("conv-") + 8].endswith(short):
            return f"#{full}"
    return None
```

可能冲突（前 8 字符撞）→ log warning 拒处理，operator 必须用更长前缀。
实操：8 字符 hex 撞概率 1/2^32，超低。

## 8. UX 妥协说明（部署文档化）

operator 切换到 WeCom supervise 时的体验差异：

| 飞书 | WeCom |
|---|---|
| 主卡片实时 update mode/state | 开场卡固定，状态变更走平铺 message 通告 |
| thread 嵌套清晰看每个 conv | 平铺，需要 `[conv_short]` 视觉过滤 |
| 卡片有按钮可点 | 卡仅展示，按钮交互在客户群 csat 卡支持 |
| @operator 高亮 + 推送 | 表情 🚨 + 文字提示，无 push |
| operator 直接 thread 内 reply | 必须显式 `[conv_short]` 前缀 |

文档要给 operator 培训说明这些差异。**不是 bug 是平台限制**。

## 9. 真机 checklist

- [ ] customer-wecom 群里客户发"hi" → squad-wecom 群收到 `[abc12345] 👤 ww_xxxxx: hi`
- [ ] fast-agent 回复 → squad-wecom 群收到 `[abc12345] 🤖 yaosh-fast-001: ...`
- [ ] customer 触发求助 → squad 群收到 `[abc12345] 🚨 求助 @operator <text>`
- [ ] operator 在 squad 群打 `[abc12345] 不退不换` → fast-agent 收到 `__side:不退不换` → 按 side 私密协商规则处理
- [ ] /hijack 在 squad 群打 `[abc12345] /hijack` → mode_changed event → squad 群有 `[abc12345] ⚙️ 模式切换 → takeover` 通告
