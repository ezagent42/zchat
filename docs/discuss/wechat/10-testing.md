# 10 · 测试方案

## 1. 三层测试模型

| 层 | 范围 | 手段 |
|---|---|---|
| Unit | 各 driver / sender / parser 单文件逻辑 | pytest + mock SDK / requests |
| Integration | wecom_bridge 跟 CS WS 端到端（不打真 WeCom） | pytest + 假 WeCom server (aiohttp) |
| Real-machine | 真 WeCom 后台 + 真客户消息 | 手工 + asciinema 记录 |

## 2. Unit tests 覆盖矩阵

```
tests/unit/
├── test_wecom_config.py                     credentials 解析 + routing
├── test_wecom_callback.py                   Kefu callback verify + decrypt + dispatch
├── test_wecom_sync_msg.py                   cursor 管理 + has_more 循环
├── test_wecom_send_msg.py                   text/image/menu 发送 + retry
├── test_wecom_botlink_ws.py                 WSS frame parse / 心跳
├── test_wecom_message_parsers.py            10 种 msgtype 入站解析
├── test_wecom_renderer.py                   conv_card / csat menu / supervise markdown
├── test_wecom_outbound.py                   CS event → driver 路由
├── test_wecom_membership.py                 enter_session / change_external_chat
├── test_wecom_supervise.py                  conv 镜像 + [conv-X] 前缀
└── test_wecom_token_manager.py              文件锁 / TTL
```

## 3. Mock 策略

WeChatPy SDK 用 `unittest.mock`：

```python
from unittest.mock import patch, MagicMock
from wecom_bridge.drivers.kefu.send_msg import KefuSender

def test_send_text():
    sender = KefuSender(corp_id="ww1", corp_secret="x", open_kfid="wk1")
    sender._client = MagicMock()
    sender._client.session = MagicMock()
    fake_resp = {"errcode": 0, "msgid": "MSG123"}
    with patch("wecom_bridge.drivers.kefu.send_msg.requests.post") as mock_post:
        mock_post.return_value.json.return_value = fake_resp
        msgid = sender.send_text("ext_user", "hi")
        assert msgid == "MSG123"
```

WSS botlink 用 `pytest-asyncio` + `aioresponses`：

```python
import pytest
from aioresponses import aioresponses

@pytest.mark.asyncio
async def test_botlink_handshake():
    # 用 echo wss server fixture 模拟 openws.work.weixin.qq.com
    ...
```

## 4. Integration tests

跑真 channel_server (assertion 9999) + 起 wecom_bridge 进程 + 模拟 WeCom 推 callback：

```python
# tests/e2e/test_wecom_kefu_e2e.py
import pytest
import requests
from xml.sax.saxutils import escape

@pytest.mark.e2e
async def test_kefu_msg_round_trip(channel_server, wecom_bridge_kefu):
    """模拟 WeCom 推 callback → bridge sync_msg → 进 IRC → fast-agent 回复 → bridge send_msg"""
    # 1. 假装 WeCom 推 kf_msg_or_event callback
    callback_xml = encrypt_callback({
        "ToUserName": "ww1",
        "MsgType": "event",
        "Event": "kf_msg_or_event",
        "Token": "FAKE_TOKEN",
        "OpenKfId": "wk1",
    })
    resp = requests.post(
        "http://localhost:8788/wecom/callback",
        params={"msg_signature": ..., "timestamp": ..., "nonce": ...},
        data=callback_xml,
    )
    assert resp.text == "success"

    # 2. wecom_bridge 应该立刻调 sync_msg → 我们的 fake server 返回一条 text 消息
    fake_wecom.next_sync_msg_response = {
        "errcode": 0,
        "next_cursor": "C2",
        "has_more": 0,
        "msg_list": [
            {"msgtype": "text", "text": {"content": "你好"},
             "external_userid": "external_user_1", "send_time": 1672531200,
             "msgid": "M001"},
        ],
    }

    # 3. 等 IRC 收到 PRIVMSG #conv-XXX :__msg:<uuid>:你好
    msg = await irc_listen("#wecom-test", timeout=5)
    assert "你好" in msg

    # 4. 模拟 fast-agent 回复
    irc_send("#wecom-test", "__msg:reply-1:您好，请问有什么可以帮您？")

    # 5. wecom_bridge 应该 POST 到 fake_wecom send_msg
    sent = fake_wecom.last_send
    assert sent["msgtype"] == "text"
    assert sent["text"]["content"] == "您好，请问有什么可以帮您？"
    assert sent["touser"] == "external_user_1"
```

## 5. 真机 (real WeCom) 测试

需要：
- 真 WeCom 企业（已注册）
- 真客服账号 + 真智能机器人
- 公网可达 wecom_bridge

完整 checklist：

### 5.1 Kefu 链路

- [ ] WeCom 后台 → 客户联系 → 微信客服 → 开发配置 → 填 callback URL → 保存（GET 验证 200）
- [ ] log: `[wecom-bridge.callback] URL verified ok`
- [ ] 用个人微信扫客服二维码 → 看到 "您好，请问有什么可以帮您？" 自动欢迎
- [ ] log: `[wecom-bridge.kefu] enter_session for external_user_1, sent welcome msg`
- [ ] 客户发"我要查订单 ABC123"
- [ ] log: `[wecom-bridge.kefu] sync_msg pulled 1 message: text`
- [ ] IRC #conv-xxxxx 看到 PRIVMSG :__msg:<uuid>:我要查订单 ABC123
- [ ] fast-agent 回复 → 客户在微信收到回复（< 3s 满足 SLA）
- [ ] 客户发图片 → 同样链路 → IRC 看到 [图片]，agent 回 "收到您的图片"

### 5.2 Botlink admin

- [ ] WeCom 后台 → 智能机器人创建
- [ ] 内部 admin 群 @ 此机器人入群
- [ ] 在 admin 群 @机器人 "list agents"
- [ ] log: `[wecom-bridge.botlink] received message from group wm_admin_xxx`
- [ ] IRC #admin 收到对应 PRIVMSG
- [ ] admin-agent 调 run_zchat_cli → 群内 markdown 输出 agent 列表

### 5.3 Squad supervise

- [ ] 在 customer-wecom 客服收到客户消息
- [ ] 同时 squad-wecom 内部群里看到 `[conv-xxxxx] 👤 ext_user: 你好` markdown 行
- [ ] fast-agent 回复也镜像 `[conv-xxxxx] 🤖 yaosh-fast-001: ...`
- [ ] 客户发"我要退货" 触发 escalate
- [ ] squad 群看到 `## 🚨 求助 [conv-xxxxx]\n> 退货纠纷\n@operator-xxx`
- [ ] operator 在 squad 群回 `[conv-xxxxx] 不退不换`
- [ ] log: `[squad-bridge] parsed [conv-xxxxx] prefix → side msg to #conv-xxxxx`
- [ ] fast-agent 收到 __side: 不退不换 → side 回 + 客户后续问 → 答（按新 soul 逻辑）

### 5.4 CSAT

- [ ] customer 在客服里发 "/resolve"（或客服按规则）
- [ ] csat plugin emit csat_request → wecom_bridge.kefu 发 msgmenu (5 项评分)
- [ ] 客户在微信看到菜单 → 点 "⭐⭐⭐⭐⭐ 很满意"
- [ ] sync_msg 拉到 click event → bridge 解析 click_id="csat_5"
- [ ] CS emit csat_score event → audit plugin 记录 5 分

### 5.5 lazy_create

- [ ] 全新外部用户首次进 customer-wecom 客服
- [ ] log: `[wecom-bridge.kefu] enter_session for new external_user_X`
- [ ] log: `[wecom-bridge] _lazy_create_channel_and_agent ext_user_X → conv-<hash8>`
- [ ] routing.toml 多 `[channels."#conv-<hash8>"]`
- [ ] state.json 多 entry agent
- [ ] 该客户接下来的消息走对应 channel

## 6. Pre-release walkthrough（仿 zchat 现有）

仿 `tests/pre_release/walkthrough.sh`，写 `tests/pre_release/wecom-walkthrough.sh`：
- 录 asciinema
- 跑全套：bot add wecom / 配置 callback / 客户测 / supervise 测 / CSAT 测
- 产出 .cast 文件供人审

## 7. 性能 / 压力

- Kefu sync_msg 每秒最多多少条？官方未明示，实测：
  - 单 customer-wecom 进程 ~ 30 条/s 拉取吞吐（瓶颈在 send_msg 限频 60/min）
- Botlink WSS 心跳 30s，能撑多少并发 frame？SDK 单进程实测 100+ msg/s 没问题
- 同时 Kefu + Botlink + voice 三 wecom_bridge + voice_bridge 进程，单 Mac mini 跑 < 200MB RAM

## 8. CI 上跑哪些

CI（macOS / Ubuntu）：
- ✅ 全部 unit tests
- ⚠️ Integration tests 不跑（需 fake WeCom server，复杂）
- ❌ Real WeCom tests 不跑（需企业账号）

加到 .github/workflows/test.yml：
```yaml
- run: uv run pytest tests/unit/ -v
```

不加 wecom 相关 e2e 到 CI 默认。开发分支手动跑 e2e。
