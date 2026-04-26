# 01 · 架构总览（v2 — 已对照官方 API 重写）

## 0. 重大订正

v1 文档假设 WeCom 跟飞书一样有"客户群 + 一种 API"。**经查官方 API 文档**（developer.work.weixin.qq.com），WeCom 没有让第三方应用接收**外部客户群**消息的能力。架构必须是 **3 套 API 共栈**。

## 1. 飞书 → WeCom 三栈映射

```
zchat 端到端架构（飞书路径）:
─────────────────────────────────────────────
  飞书客户群 (oc_xxx)        飞书 admin 群       飞书 squad 群
        │                         │                  │
        │ WSS               WSS  │            WSS   │
        ▼                         ▼                  ▼
       feishu_bridge customer / admin / squad
        │                         │                  │
        └─────────┬───────────────┴──────────────────┘
                  │ ws_messages
                  ▼
           channel_server (CS)              ← 不动
                  │ IRC
                  ▼
                ergo                        ← 不动
                  │
                  ▼
              agents (Claude)               ← 不动


zchat 端到端架构（WeCom 路径）:
─────────────────────────────────────────────
  客户 (微信用户/外部)      内部 admin 群       内部 squad 群
        │                         │                  │
   ┌────┴────┐                    │                  │
   │ Kefu    │                    │                  │
   │ HTTP    │              智能机器人长连接 (WSS to wss://openws.work.weixin.qq.com)
   │ callback│                    │                  │
   │+sync_msg│                    │                  │
   └────┬────┘                    │                  │
        ▼                         ▼                  ▼
       wecom_bridge customer / admin / squad
        │                         │                  │
        └─────────┬───────────────┴──────────────────┘
                  │ ws_messages
                  ▼
           channel_server (CS)              ← 不动
                  │ IRC
                  ▼
                ergo                        ← 不动
                  │
                  ▼
              agents (Claude)               ← 不动
```

## 2. 三套 API 详细对照

| 维度 | Kefu (客户对话) | 智能机器人长连接 (内部群) | 群机器人 webhook |
|---|---|---|---|
| 适用对象 | B2C 外部客户 | 企业员工内部群 | 任意已添加机器人的群 |
| 入站协议 | HTTP callback (notify) → POST sync_msg pull | WSS frame | ❌ 无 |
| 出站协议 | HTTP POST send_msg | WSS send / send_to_group | HTTP POST |
| 加密 | callback 走 MsgCrypt (token + EncodingAESKey) | 长连接已加密，**无需自己 MsgCrypt** | 无（key 在 URL）|
| 凭证 | corp_id + corp_secret + open_kfid | BotID + Secret | webhook key (URL) |
| 支持消息类型 | text/image/voice/video/file/link/miniprogram/msgmenu/location/ca_link | text/image/markdown/markdown_v2/template_card/news/file/voice | text/markdown/markdown_v2/image/news/file/voice/template_card |
| 不支持 | template_card, markdown | （都支持）| ❌ 不能接收 |
| 频率限制 | 严格（通过 Token 解放）| 较宽 | 20/min/group |
| 客户身份 | external_userid | userid (企业 member) | — |
| 群标识 | open_kfid + external_userid (1-1) | chatid (内部群) | webhook key 绑死群 |
| 文档 | [path/96426](https://developer.work.weixin.qq.com/document/path/96426) | [path/101463](https://developer.work.weixin.qq.com/document/path/101463) | [path/91770](https://developer.work.weixin.qq.com/document/path/91770) |

## 3. wecom_bridge 内部模块结构（v2）

```
src/wecom_bridge/
├── __init__.py
├── __main__.py                  入口：python -m wecom_bridge --bot <name>
│
├── config.py                    BotConfig：根据 type 字段决定走哪个栈
├── routing_reader.py            读 routing.toml [bots.<name>]
├── credentials.py               解析 credentials/*.json
│
├── bridge.py                    主类，根据 BotConfig.platform_role 选 driver
│
├── drivers/                     ← 三栈实现
│   ├── kefu/                    客户对话栈
│   │   ├── callback.py          HTTP server: /wecom/callback (验签 + 解密)
│   │   ├── sync_msg.py          POST sync_msg + cursor 管理
│   │   ├── send_msg.py          POST send_msg
│   │   └── kefu_handler.py      把 sync_msg 拉到的消息转 ws_messages
│   ├── botlink/                 智能机器人长连接栈
│   │   ├── ws_client.py         WSS to openws.work.weixin.qq.com + 心跳
│   │   ├── send.py              WSS send (text/markdown/template_card)
│   │   └── botlink_handler.py
│   └── webhook/                 群机器人 webhook 栈（仅 push）
│       └── send.py              HTTP POST 到 webhook URL
│
├── shared/                      ← 跨 driver 复用
│   ├── token_manager.py         access_token cache + 文件锁
│   ├── crypto.py                MsgCrypt (Kefu callback 解密)
│   ├── media.py                 图片/语音/文件 download via media_id
│   ├── markdown_renderer.py     conv 卡 / supervise 行 / CSAT 菜单 的渲染
│   └── message_parsers.py       Kefu sync_msg 返回的各 msgtype 解析
│
├── outbound.py                  CS event → driver 路由
│   - 客户消息 → kefu driver
│   - admin/squad 群推送 → botlink or webhook
│
├── group_manager.py             chat_id ↔ channel 双向映射
│                                Kefu 是 (open_kfid, external_userid) → channel
│                                botlink 是 chatid → channel
│
├── bridge_api_client.py         共享：CS WS 通信（跟 feishu_bridge 同）
└── test_client.py               E2E 测试 client
```

## 4. routing.toml 加 platform_role

每个 bot 必须明确角色 + 平台栈：

```toml
[bots.customer-wecom]
type = "wecom"                      # zchat bot type
platform_role = "kefu"              # 走 Kefu API
credential_file = "credentials/customer-wecom.json"
default_agent_template = "fast-agent"
lazy_create_enabled = true
callback_public_url = "https://wecom-customer.inside.h2os.cloud/wecom/callback"

[bots.admin-wecom]
type = "wecom"
platform_role = "botlink"           # 走智能机器人长连接
credential_file = "credentials/admin-wecom.json"
default_agent_template = "admin-agent"
internal_chat_ids = ["wm_admin_xxxxx"]   # 长连接 bot 在哪些内部群

[bots.squad-wecom]
type = "wecom"
platform_role = "botlink"
credential_file = "credentials/squad-wecom.json"
default_agent_template = "squad-agent"
supervises = ["customer-wecom"]
internal_chat_ids = ["wm_squad_xxxxx"]
```

`platform_role` 的合法值：`kefu` | `botlink` | `webhook`

## 5. 一个 wecom_bridge 进程一个 platform_role

跟 feishu 一 bot 一进程模型一致：

```bash
# 三个进程
python -m wecom_bridge --bot customer-wecom --routing routing.toml   # 起 HTTP server :8788
python -m wecom_bridge --bot admin-wecom    --routing routing.toml   # 起 WSS client
python -m wecom_bridge --bot squad-wecom    --routing routing.toml   # 起 WSS client
```

`zchat up` 遍历 `[bots.*]`，对每个 type=wecom 的起一个 wecom_bridge 进程。

## 6. credentials 文件 schema

### Kefu 角色
```json
{
  "type": "wecom",
  "platform_role": "kefu",
  "corp_id": "ww123abc",
  "corp_secret": "xxx",
  "agent_id": 1000002,
  "open_kfid": "wkXXXXXX",
  "callback_token": "openssl-rand-hex-16",
  "encoding_aes_key": "43-char-from-WeCom-console"
}
```

### Botlink 角色
```json
{
  "type": "wecom",
  "platform_role": "botlink",
  "bot_id": "B0000001",
  "bot_secret": "xxx"
}
```

不需要 corp_id（智能机器人独立身份）。

### Webhook 角色（push only，少用）
```json
{
  "type": "wecom",
  "platform_role": "webhook",
  "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=XXX"
}
```

## 7. 模块 / driver 行为表

| 行为 | Kefu driver | Botlink driver | Webhook driver |
|---|---|---|---|
| 接收消息 | callback notify → sync_msg pull → ws_messages.build_message → CS | WSS frame → 解析 → ws_messages | ❌ |
| 发送文本 | send_msg type=text | WSS send | webhook POST |
| 发送图片 | send_msg type=image (media_id) | WSS send 或 markdown image | webhook POST |
| 发送 markdown | ❌ 退化为 text | ✅ | ✅ |
| 发送模板卡片 | ❌ 改用 msgmenu (CSAT) | ✅ | ✅ |
| 卡片更新 | ❌ 发新 + 旧留着 | ❌ 同 | ❌ 同 |
| 接收按钮点击 | sync_msg msgmenu click_id | template_card_event WSS frame | ❌ |
| 群成员事件 | enter_session / change_external_chat callback | WSS event frame | ❌ |
| 群信息查询 | external_user/get | (自己维护 chatid) | ❌ |

## 8. 跟 feishu_bridge 共享的部分

| 模块 | 共享方式 |
|---|---|
| `bridge_api_client.py` | 抽到 `src/_im_bridge_shared/` 共用，feishu/wecom 都 import |
| `routing_reader.py` | 同上 |
| `outbound.py` 的 CS event 路由骨架 | 一致（CS event → driver 转换 → IM API），可以 share base class |

## 9. 红线复审（v2）

| 红线 | 检查 |
|---|---|
| `channel_server/` 不知业务名 | ✅ wecom_bridge 跟 feishu_bridge 平级，core 不变 |
| `zchat-protocol/` 标准库 only | ✅ 不动 |
| `agent_mcp.py` 不依赖 bridge 实现 | ✅ agent 不感知是 Kefu / Botlink / Webhook，所有差异在 bridge |
| `routing.toml` single-writer = CLI | ✅ 仍是 CLI 写 |
| plugin 不读 `credentials/` | ✅ bridge 自己读 |
| `cli/` 不绑业务 | ⚠️ `zchat bot add` 加 `--type wecom` + `--platform-role` 选项；`zchat doctor` 加 wecom 检查路径。最小化但确实碰 cli — 需 review |

## 10. 进程编排示例（带 voice + WeCom + 飞书共存）

```
zellij session: zchat-prod
├── tab: ctl
├── tab: chat (weechat)
├── tab: cs                          channel_server :9999
├── tab: bridge-customer-feishu      feishu_bridge customer
├── tab: bridge-admin-feishu         feishu_bridge admin
├── tab: bridge-squad-feishu         feishu_bridge squad
├── tab: bridge-customer-wecom       wecom_bridge customer (Kefu, :8788)
├── tab: bridge-admin-wecom          wecom_bridge admin (Botlink WSS)
├── tab: bridge-squad-wecom          wecom_bridge squad (Botlink WSS)
├── tab: voice                       voice_bridge (:8787)
├── tab: yaosh-fast-001              fast-agent
├── tab: yaosh-admin-0               admin-agent
└── tab: yaosh-squad-0               squad-agent
```

agents 完全不知道服务的客户来自飞书还是 WeCom — 只看 IRC channel name。

## 11. 验收（同 v1 + 加 WeCom 项）

1. ✅ feishu 正常运行（共存验证）
2. WeCom 客户用微信发消息给 Kefu → 进 IRC #channel → fast-agent 回 → 客户收到
3. 内部 admin 群 @admin-bot "list agents" → admin-agent 收到 → 调 run_zchat_cli → 群内回结果
4. 内部 squad 群有 conv 镜像 + 求助通知（详见 08）
5. CSAT msgmenu 客户点击 → audit 记录分数
6. lazy_create：新客户接入 Kefu → 自动新建 #channel + entry agent

## 12. 不在范围

- 不实现 v3 "客户群"（外部客户的多方群聊）— WeCom 不开放给第三方
- 不实现 v3 卡片动态 update — 平台限制
- 不实现 thread 嵌套 — 平台限制
