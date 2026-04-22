# 004 · 迁移指南：把 AutoService 迁到 zchat

> 场景：你已有一个独立的 web 端客服机器人项目（如 AutoService），有自己的 web 前后端、用户/客户管理、数据库。现在要把**消息总线 + agent 模板调度**这两块替换成 zchat，但保留 web UI / DB / 业务逻辑。

## 0. 先弄清楚分界线

zchat 的核心抽象是 **"channel + 消息格式"**：
- channel = 一个聊天会话
- 消息格式 = `__msg:<id>:<text>` / `__side:` / `__edit:` / `__zchat_sys:` 4 种 IRC 前缀

迁移意味着：

| 你保留 | 移交 zchat |
|---|---|
| Web 前后端（客户登录、对话窗口、座席工作台） | agent ↔ agent 协同消息流 |
| 用户/客户/座席数据库 | 消息总线（IRC + WS） |
| 业务规则引擎（如有） | agent lifecycle 编排（启动/停止/重启） |
| API 层（已有 REST/GraphQL） | Claude Code agent 模板（fast/deep/admin/squad） |
| 平台账号体系 | 路由规则（routing.toml） |
| | 跨 agent 协同（list_peers / @mention） |

类比飞书：飞书自己也是 web/移动端 UI + 自己的 IM 协议，zchat 通过 `feishu_bridge` 适配它。AutoService 完全等同于"另一个 IM 平台"，需要写一个 `autoservice_bridge`。

## 1. 整体架构（迁移后）

```
┌──────────────────────────────────────────────────────────────┐
│            AutoService Web 前端                               │
│   客户聊天窗 / 座席工作台 / 管理面板 (React/Vue)              │
└──────────────────┬───────────────────────────────────────────┘
                   │ WebSocket / SSE
                   ▼
┌──────────────────────────────────────────────────────────────┐
│            AutoService 后端（你保留）                          │
│   - 用户/客户/座席 CRUD                                       │
│   - 对话存储 (PostgreSQL)                                    │
│   - REST/GraphQL API                                         │
│   - WebSocket gateway 推消息给前端                            │
│   - 新增：autoservice_bridge 模块                             │
└──────────────────┬───────────────────────────────────────────┘
                   │ WebSocket (zchat protocol)
                   ▼
┌──────────────────────────────────────────────────────────────┐
│              zchat channel-server + agents                    │
│   (按 001-architecture.md 完整跑)                             │
└──────────────────────────────────────────────────────────────┘
```

## 2. autoservice_bridge — 必写的部分

参考 `zchat-channel-server/src/feishu_bridge/` 的结构，写一个新 bridge：

```
zchat-channel-server/src/autoservice_bridge/
├── __init__.py
├── __main__.py            # 入口：python -m autoservice_bridge --bot xxx
├── config.py              # BridgeConfig：endpoints / credentials / lazy_create
├── bridge.py              # 主类：入站事件 + 出站消息分发
├── outbound.py            # WS msg/side/edit kind → AutoService API
├── api_client.py          # AutoService REST/GraphQL 调用封装
├── group_manager.py       # ChannelMapper: chat_id ↔ channel_id
├── routing_reader.py      # 独立解析 routing.toml（不依赖 CS）
└── autoservice_renderer.py # 卡片/格式化（如 AutoService 支持卡片；对应 feishu_bridge/feishu_renderer.py）
```

### 2.1 入站：AutoService 事件 → zchat WS

bridge 订阅 AutoService 的事件：
- 客户消息事件（每条客户输入）
- 座席行动事件（接管 / 释放 / 结案 / 评分）
- 对话生命周期（创建 / 关闭）

**关键映射**:

```python
# bridge.py 伪代码
class AutoServiceBridge:
    def on_customer_message(self, event):
        """收 AutoService 客户消息事件 → 发 zchat WS message。"""
        external_chat_id = event["session_id"]   # AutoService 的对话 ID
        channel_id = self._mapper.get_channel(external_chat_id)
        if channel_id is None:
            if self.config.lazy_create:
                channel_id = self._lazy_create_channel(external_chat_id)
            else:
                return  # 未注册的对话，忽略
        
        self._ws.send(ws_messages.build_message(
            channel=channel_id,
            source=event["user_id"],   # AutoService 用户 ID
            content=event["text"],
            message_id=event["message_id"],
        ))
    
    def on_agent_action(self, event):
        """座席点'接管' → 发 zchat WS '/hijack' 命令。"""
        if event["action"] == "takeover":
            self._ws.send(ws_messages.build_message(
                channel=self._mapper.get_channel(event["session_id"]),
                source="agent_action",
                content="/hijack",
            ))
        elif event["action"] == "csat_score":
            self._ws.send(ws_messages.build_event(
                channel=self._mapper.get_channel(event["session_id"]),
                event="csat_score",
                data={"score": event["score"], "source": "customer"},
            ))
```

### 2.2 出站：zchat WS → AutoService API

bridge 收 CS 的 WS message + event，调 AutoService API 把消息推给 web 前端：

```python
# outbound.py 伪代码
class OutboundRouter:
    def route(
        self,
        conversation_id: str,
        *,
        kind: str,
        text: str,
        cs_msg_id: str | None = None,
    ) -> str | None:
        """kw-only: kind/text/cs_msg_id 全部关键字参数（与 feishu_bridge/outbound.py 同签名）。
        返回外部平台的 msg_id（供后续 edit/reply 用）。"""
        external_id = self._mapper.get_external_chat(conversation_id)
        if kind in ("msg", "plain"):
            msg_id = self._api.post_message(external_id, text)
            if cs_msg_id:
                self._msg_id_map[cs_msg_id] = msg_id   # 给 edit 用
        elif kind == "side":
            # AutoService 座席侧栏（仅座席工作台可见）
            if thread := self._threads.get(conversation_id):
                self._api.post_to_supervisor_thread(thread.thread_id, text)
        elif kind == "edit":
            # V6+: edit 改成 reply-to 不可 patch；按你的 API 决定
            if mid := self._msg_id_map.get(cs_msg_id):
                self._api.post_reply(external_id, parent_id=mid, text=text)
```

### 2.3 lifecycle event 处理

```python
def _handle_sys_event(self, conv_id, msg):
    """处理 channel_resolved / mode_changed / help_requested / chat_info。"""
    event_name = msg.get("event")
    data = msg.get("data") or {}
    
    if event_name == "channel_resolved":
        self._api.close_session(self._mapper.get_external_chat(conv_id))
    elif event_name == "mode_changed":
        new_mode = data.get("to")
        self._api.update_session_mode(
            self._mapper.get_external_chat(conv_id),
            new_mode,   # "takeover" / "copilot" / "auto"
        )
    elif event_name == "csat_request":
        # 在 AutoService 客户端弹出评分卡 UI
        self._api.show_rating_widget(self._mapper.get_external_chat(conv_id))
    elif event_name == "help_requested":
        self._api.notify_supervisors(
            session_id=self._mapper.get_external_chat(conv_id),
            text=data.get("text", ""),
        )
```

### 2.4 ws_messages 协议参考

直接复用 `zchat-protocol`：

```python
from zchat_protocol import ws_messages, irc_encoding

# 发消息给 CS
ws_messages.build_message(channel, source, content, message_id=None)
ws_messages.build_event(channel, event, data)
ws_messages.build_register(bridge_type, instance_id, capabilities)

# 收 CS 消息
parsed = ws_messages.parse(raw_json)
parsed["type"]  # message / event
```

## 3. routing.toml 配置

routing.toml 的字段集见 `006-routing-config.md` 完整规范。AutoService bridge 这里
的最小可跑示例：

```toml
[bots.autoservice]
app_id = "autoservice-prod-1"                    # 必填，bridge 注册时的逻辑 ID
credential_file = "credentials/autoservice.json"  # schema 由 bridge 自己定义（见下方"注意"）
default_agent_template = "fast-agent"
lazy_create_enabled = true                        # 新对话自动 onboard channel + agent

[bots.supervisor]
# 如果 AutoService 有"督导"角色，单独 bot 监管所有客户对话
app_id = "autoservice-supervisor-1"
credential_file = "credentials/supervisor.json"
default_agent_template = "squad-agent"
supervises = ["autoservice"]                      # V6 仅支持 bot 名列表；V7 计划扩展 tag:/pattern:

[channels."#conv-001"]
bot = "autoservice"
external_chat_id = "session_xxx"                  # AutoService 的 session UUID（bridge 解释为外部对话 ID）
entry_agent = "yaosh-fast-001"
```

**注意 — credential 文件内容 schema**：
- routing.toml **没有** `api_endpoint` / `app_secret` / `host` 等字段
- credential 文件 schema 由**你的 bridge 自己决定**，routing 只引文件路径
- `feishu_bridge` 目前的 `credentials/<bot>.json` 实际只含 2 个字段：
  ```json
  {"app_id": "cli_xxx...", "app_secret": "yyy..."}
  ```
  lark_oapi SDK 自己知道飞书 endpoint，所以 credential 不用含 URL
- 你的 `autoservice_bridge` 若需要 endpoint / OAuth / CA cert 等，**自行**在 credential schema 里定义（例如 `{"api_base": "...", "token": "..."}`），bridge 读文件时解析即可
- routing.toml 里的 `app_id` 字段是**外部平台侧的应用/bridge 业务 ID**（如飞书 `cli_xxx`）。bridge 用它做自发回环过滤（`sender.app_id == self.config.app_id` 跳过）。如 credential 文件里也有 `app_id`，以 credential 为准（防止 routing 与 credential 不一致，见 `routing_reader.py` L149-151）

## 4. agent 模板配置

zchat 有 5 个内置 template (`templates/{claude,fast-agent,deep-agent,admin-agent,squad-agent}/`)，你可：

### 4.1 直接复用
fast/deep/admin/squad 的 soul + skills 都已优化过 V6 PRD，开箱即用。

### 4.2 写自定义 template（如果 AutoService 业务逻辑不同）

```
zchat/cli/templates/autoservice-agent/
├── template.toml          # type 定义 + hooks
├── start.sh               # 启动脚本（cp soul/CLAUDE.md/skills/）
├── soul.md                # 25-30 行人格 + 输入分类 + skills 索引
└── skills/                # 业务 workflow 拆出的 SKILL.md
    ├── handle-refund/SKILL.md
    ├── escalate-to-supervisor/SKILL.md
    └── lookup-order/SKILL.md
```

每个 SKILL.md 用 YAML frontmatter `description: "Use when ..."`，Claude Code 按关键词自动加载。详见 `zchat/cli/templates/fast-agent/` 现成例子。

### 4.3 启动 agent

```bash
zchat agent create cs-001 --type autoservice-agent --channel conv-001
```

agent 会自动 join `#conv-001`、收 CS 路由的消息、调 `reply` MCP tool 回 channel。

## 5. 消息映射对照表

| AutoService 概念 | zchat 概念 | 备注 |
|---|---|---|
| Customer session | channel (`#conv-xxx`) | 1:1 映射，bridge 维护 |
| Customer message | `__msg:<uuid>:<text>` IRC 编码 | uuid 是消息 ID 用于 edit |
| Agent reply | `__msg:<new_uuid>:<text>` | 双向 |
| Internal note (座席间) | `__side:<text>` | 仅 supervisor thread 可见 |
| Edit / 跟进答复 | `__edit:<uuid>:<text>` | bridge 解释为 reply-to-placeholder |
| 系统事件（接管/结案） | `__zchat_sys:<json>` | mode_changed / channel_resolved |
| Customer rating | `csat_score` event | 走 event 通道不走 message |
| Operator 求助 | `__side:@operator <text>` | sla plugin 自动 emit help_requested |

## 6. 数据库不需动

zchat 自己**不持久化对话内容**，仅持久化：
- routing.toml（CLI 写）
- audit.json（统计指标）
- agent state.json（lifecycle）

完整对话日志由你 AutoService 后端 DB 存（这本来就是它的事）。zchat agent 回的每条消息走 bridge 入 DB。

## 7. 渐进迁移路径

不必一步到位：

### 阶段 1 · agent 接入测试（1-2 周）
- 写 `autoservice_bridge` 最小可跑版（只支持 customer message 入站 + agent reply 出站）
- 起一个 agent 在测试对话上跑通完整流程
- 跑通 `001-architecture.md` 描述的"一条消息生命周期"

### 阶段 2 · 协同链路（2-3 周）
- 加 supervise 链：squad bridge / supervisor 角色
- 加 mode 切换：座席接管 / 释放
- 加 csat 评分

### 阶段 3 · 全量切流（视业务量）
- 灰度：10% 对话走 zchat agent，90% 老链路
- 监控 `zchat audit report` 的 CSAT / takeover rate / SLA breach
- 出问题随时切回老链路（bridge 是中介，AutoService 主链路不动）

### 阶段 4 · 老 agent 模块下线
- 全量切流后下线 AutoService 内嵌的 agent 调用代码
- 保留 web UI / DB / 业务规则

## 8. 关键检查清单

- [ ] bridge 的 ws_server URL 配置正确（`config.channel_server_url = "ws://127.0.0.1:9999"`）
- [ ] bridge 注册时声明唯一 `instance_id`（如 `autoservice-prod-1`）
- [ ] `routing.toml` 的 `external_chat_id` 和 AutoService session ID 一致
- [ ] AutoService API 调用幂等（避免 bridge 重连后重复发消息）
- [ ] 自发回环过滤：bridge 入站要忽略本 bot 自己发的消息（参考 feishu_bridge `_on_message` 里 `sender.app_id == self.config.app_id` 检查）
- [ ] 消息去重：用 deque + set LRU（feishu_bridge 现成实现）
- [ ] credential 安全：单独 `credentials/<bot_name>.json` 文件，**别**塞进 routing.toml

## 9. 不需要做的事

- ❌ 自己写 plugin —— 用现成的 mode/sla/resolve/audit/activation/csat 6 个
- ❌ 改 channel_server 内部逻辑 —— 红线禁
- ❌ 改 zchat-protocol —— bridge ↔ CS 协议是稳定 API
- ❌ 写 IRC 客户端 —— ergo + agent_mcp 已包办
- ❌ 自己管 agent lifecycle —— `zchat agent create/stop/restart` 全套

## 10. 参考 commit / 文件

| 你需要的 | 参考 zchat 里的 |
|---|---|
| bridge 主类骨架 | `zchat-channel-server/src/feishu_bridge/bridge.py` |
| routing 独立解析 | `zchat-channel-server/src/feishu_bridge/routing_reader.py` |
| chat_id 映射 | `zchat-channel-server/src/feishu_bridge/group_manager.py` |
| 出站路由 + edit 处理 | `zchat-channel-server/src/feishu_bridge/outbound.py` |
| supervisor 卡片+thread | `bridge.py` 里的 `_handle_supervised_message` + `_supervise_help_requested` |
| 自定义 agent 模板 | `zchat/cli/templates/fast-agent/` 全套 |

## 11. 常见困惑

**Q: AutoService 没有"群"概念，只有 1 对 1 客户对话，怎么映射？**  
A: channel 就是 1:1。`#conv-<session_id>` 一个 channel 一个客户。bridge 直接把 customer 的 input 作为消息发到对应 channel。

**Q: AutoService 已经有"接管"按钮，要把它接进 mode plugin 吗？**  
A: 是的。座席点接管 → bridge `on_agent_action` → 发 WS `/hijack` 命令 → mode plugin → agent 切副驾驶。这样 zchat 的 sla / audit 才能正确统计。

**Q: 客户用 markdown 输入怎么办？**  
A: zchat 协议层是纯文本。bridge 入站时如需保留格式可在 `__msg:` 的 text 段直接传 markdown，agent 模板层（soul.md）说明"客户用 markdown 时按 markdown 渲染"即可。出站同理。

**Q: 想接 OpenAI 而不是 Claude？**  
A: agent_mcp 当前只支持 Claude Code。要接其它需要改 `agent_manager.py` 起进程的命令 + 写新 MCP server。属于 zchat 框架级扩展，超出 bridge 范围。

## 关联

- 架构图: `001-architecture.md`
- 协议层 source: `zchat-protocol/zchat_protocol/{ws_messages,irc_encoding}.py`
- 红线 / 开发规范: `005-dev-guide.md`
