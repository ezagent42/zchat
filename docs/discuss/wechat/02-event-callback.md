# 02 · 入站事件 — HTTP 回调 + 加密验签

## 1. 飞书 vs WeCom 入站机制对比

| 维度 | 飞书 | 企业微信 |
|---|---|---|
| 协议 | WSS 长连接（lark_oapi.ws.client）| HTTPS POST 回调（自家公网 URL）|
| 身份 | SDK 内嵌 access_token | URL 需提供 token + EncodingAESKey 加密 |
| 顺序 | SDK 保证顺序 | 自管 — 同 chat 短时间内可乱序，需自己处理 |
| Reliability | SDK 内自动重连 | 我们的 server 必须 24×7 可达，否则 WeCom 端不重试（事件丢）|
| 方向 | 单向（服务端 → 我们）| 单向（WeCom → 我们）|

**因此：wecom_bridge 必须起 HTTPS server**。入端口建议 `127.0.0.1:8788`（参考 voice_bridge 8787 模式），通过 caddy 反代到公网 `https://wecom-customer.inside.h2os.cloud/wecom/callback`。

## 2. WeCom 回调消息结构

### 2.1 GET（URL verification — 一次性）

WeCom 后台配置 callback URL 时会先 GET 验证：

```
GET /wecom/callback?msg_signature=XXX&timestamp=1234567890&nonce=ABC&echostr=<encrypted_random>
```

服务端必须：
1. 用 `Token + timestamp + nonce + echostr` 算 SHA1 → 跟 `msg_signature` 比对
2. 用 `EncodingAESKey` AES-CBC 解密 `echostr`
3. 返回明文 echostr（无任何 wrap，不要 JSON）

**回错就接入失败**。我们写一遍 verify endpoint 完事。

### 2.2 POST（事件 + 消息）

```
POST /wecom/callback?msg_signature=XXX&timestamp=1234567890&nonce=ABC
Content-Type: text/xml

<xml>
  <ToUserName><![CDATA[ww123abc]]></ToUserName>
  <Encrypt><![CDATA[<base64-encrypted-payload>]]></Encrypt>
</xml>
```

解密后明文 XML（举例消息）:
```xml
<xml>
  <ToUserName><![CDATA[ww123abc]]></ToUserName>
  <FromUserName><![CDATA[user_open_id]]></FromUserName>
  <CreateTime>1672531200</CreateTime>
  <MsgType><![CDATA[text]]></MsgType>
  <Content><![CDATA[您好]]></Content>
  <MsgId>123456789</MsgId>
  <AgentID>1000002</AgentID>
  <ChatId><![CDATA[wm_xxxxxxxx]]></ChatId>   <!-- 群内消息独有 -->
</xml>
```

服务端必须 **5 秒内**回 `success`（裸字符串）或会被 WeCom 视为失败重试。

## 3. 加密协议（必须实现）

WeCom 用 **MsgCrypt** 协议。直接复用 `wechatpy.crypto`：

```python
from wechatpy.work.crypto import WeChatCrypto

crypto = WeChatCrypto(
    token="your_token",            # WeCom 后台设置
    encoding_aes_key="43-char-key", # WeCom 后台生成
    corp_id="ww123abc",
)

# 验签 + 解密 GET echostr
echo_plain = crypto.check_signature(
    msg_signature=q["msg_signature"],
    timestamp=q["timestamp"],
    nonce=q["nonce"],
    echo_str=q["echostr"],
)

# 验签 + 解密 POST body
xml_plain = crypto.decrypt_message(
    raw_msg=request_body_text,
    msg_signature=q["msg_signature"],
    timestamp=q["timestamp"],
    nonce=q["nonce"],
)
```

**自建方案**（不引 wechatpy）：
- AES-CBC: `cryptography.hazmat.primitives.ciphers`
- SHA1: `hashlib`
- 完整算法文档：[企业微信 - 加解密说明](https://developer.work.weixin.qq.com/document/path/90968)
- 实测 ~100 行代码

推荐先用 `wechatpy`，验证通过再决定要不要替掉。

## 4. wecom_callback_handler.py 设计

```python
"""WeCom 回调入口：起 aiohttp HTTPS server 接收 + 解密 + 分发到 bridge handler。

跟 feishu_bridge.ws_client.py 同位置但实现完全不同（HTTP vs WSS）。
"""
from __future__ import annotations

import logging
from typing import Callable
import xml.etree.ElementTree as ET

from aiohttp import web
from wechatpy.work.crypto import WeChatCrypto

log = logging.getLogger("wecom-bridge.callback")


class WeComCallbackServer:
    """aiohttp server, single endpoint: POST/GET /wecom/callback.

    bridge.py 注入 4 个 handler，对应 4 大事件类：
      on_message(msg_dict)        — 消息（text/image/voice/video/file/link）
      on_event(event_dict)        — 事件（subscribe/unsubscribe/...）
      on_chat_member(event_dict)  — 群成员变更
      on_card_action(action_dict) — 模板卡片点击
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        token: str,
        encoding_aes_key: str,
        corp_id: str,
        on_message: Callable,
        on_event: Callable,
        on_chat_member: Callable,
        on_card_action: Callable,
    ) -> None:
        self._host = host
        self._port = port
        self._crypto = WeChatCrypto(token, encoding_aes_key, corp_id)
        self._on_message = on_message
        self._on_event = on_event
        self._on_chat_member = on_chat_member
        self._on_card_action = on_card_action
        self._app = web.Application()
        self._app.router.add_get("/wecom/callback", self._verify_url)
        self._app.router.add_post("/wecom/callback", self._receive)
        self._app.router.add_get("/health", lambda _r: web.Response(text="ok"))

    async def _verify_url(self, request: web.Request) -> web.Response:
        q = request.query
        try:
            echo_plain = self._crypto.check_signature(
                msg_signature=q["msg_signature"],
                timestamp=q["timestamp"],
                nonce=q["nonce"],
                echo_str=q["echostr"],
            )
            return web.Response(text=echo_plain)
        except Exception as e:
            log.error("URL verify failed: %s", e)
            return web.Response(status=400, text="invalid signature")

    async def _receive(self, request: web.Request) -> web.Response:
        q = request.query
        body = await request.text()
        try:
            xml_plain = self._crypto.decrypt_message(
                raw_msg=body,
                msg_signature=q["msg_signature"],
                timestamp=q["timestamp"],
                nonce=q["nonce"],
            )
        except Exception as e:
            log.error("decrypt failed: %s", e)
            return web.Response(status=400, text="bad encryption")

        msg = self._parse_xml(xml_plain)
        msg_type = msg.get("MsgType", "")
        event = msg.get("Event", "")

        # 路由
        try:
            if msg_type == "event":
                if event in ("subscribe", "unsubscribe"):
                    await self._on_event(msg)
                elif event in ("change_external_contact", "change_external_chat"):
                    await self._on_chat_member(msg)
                elif event == "template_card_event":
                    await self._on_card_action(msg)
                else:
                    log.debug("unhandled event=%s", event)
            else:
                # 普通消息: text/image/voice/video/file/link/location
                await self._on_message(msg)
        except Exception:
            log.exception("handler raised; returning success anyway to avoid WeCom retry")

        return web.Response(text="success")

    @staticmethod
    def _parse_xml(s: str) -> dict:
        root = ET.fromstring(s)
        return {child.tag: (child.text or "") for child in root}

    async def start(self) -> None:
        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, self._host, self._port)
        await site.start()
        log.info("wecom_bridge callback listening on %s:%d", self._host, self._port)
```

## 5. bridge.py 改造

替换原来的 lark.EventDispatcherHandler builder：

```python
# wecom_bridge/bridge.py
class WeComBridge:
    def __init__(self, config, routing_path):
        ...
        self._callback = WeComCallbackServer(
            host=config.callback_host,
            port=config.callback_port,
            token=config.wecom.callback_token,
            encoding_aes_key=config.wecom.encoding_aes_key,
            corp_id=config.wecom.corp_id,
            on_message=self._on_message,
            on_event=self._on_event,
            on_chat_member=self._on_chat_member,
            on_card_action=self._on_card_action,
        )

    async def start(self):
        await self._cs_client.connect()       # 复用 bridge_api_client
        await self._callback.start()          # 启 HTTPS server
        # 不再 .start() 一个 lark client；改成 asyncio loop forever
```

`__main__.py` 用 `asyncio.run(bridge.start())` + signal-driven shutdown。

## 6. 端口规划

| 端口 | 服务 | 暴露 |
|---|---|---|
| 8787 | voice_bridge | caddy 反代 voice.inside.h2os.cloud |
| 8788 | wecom_bridge customer | caddy 反代 wecom-customer.inside.h2os.cloud |
| 8789 | wecom_bridge admin | caddy 反代 wecom-admin.inside.h2os.cloud |
| 8790 | wecom_bridge squad | caddy 反代 wecom-squad.inside.h2os.cloud |

每个 bot 一个端口。等价飞书每个 bot 一个 WSS（飞书是 outbound 不占端口；wecom inbound 占）。

详细 caddy 配置见 09。

## 7. 安全约束

1. **callback URL 必须 HTTPS** — WeCom 不接受 http
2. **MsgCrypt token / aes_key 不可共享** — 不同 bot 不同 token，否则别 bot 的事件可能误投
3. **5s 内 return success** — 慢路径（跟 CS 的 WS 通信）必须 fire-and-forget，不等 ack
4. **重放窗口** — 同一 msg_signature 如果在 X 秒内再来要去重（WeCom 可能因网络问题重发）。可以 cache 最近 1000 条 msg_id。

## 8. 错误处理矩阵

| 场景 | 行为 |
|---|---|
| 验签失败 | 400 + log error，**不**回 success |
| 解密失败 | 同上 |
| handler 内部异常 | log.exception + 仍 return success，避免 WeCom 重试堆积 |
| WeCom 5s 内没收到 success | WeCom 重试 3 次；我们要保证 5s 内 ack |
| 单条消息 handler 慢（如调 CS WS）| 用 `asyncio.create_task` 后台跑，立刻 return success |
| Server 进程挂 | 客户消息丢失（WeCom 重试 3 次失败放弃）— 必须 systemd / supervisor 拉起 |

## 9. 单元测试

```python
# tests/unit/test_wecom_callback.py
import pytest
from aiohttp.test_utils import AioHTTPTestCase

class TestWeComCallback(AioHTTPTestCase):
    async def get_application(self):
        from wecom_bridge.wecom_callback_handler import WeComCallbackServer
        # mock crypto / handlers
        ...

    async def test_url_verify_success(self):
        resp = await self.client.get("/wecom/callback?msg_signature=...&...&echostr=encrypted")
        assert await resp.text() == "decrypted_echo"

    async def test_message_text_dispatched(self):
        body = "<xml>...</xml>"
        resp = await self.client.post("/wecom/callback?...", data=body)
        assert await resp.text() == "success"
        # mocked on_message called once with parsed dict
```

## 10. 实测 checklist

- [ ] WeCom 后台 → 应用管理 → 自建应用 → 接收消息 → 设置 URL + Token + EncodingAESKey
- [ ] 点保存 → WeCom 立即 GET 验证 → 看 wecom_bridge log 是否打印 `URL verified ok`
- [ ] 在 WeCom 客户端给 bot 发条 "ping"
- [ ] log 应有：`receive POST → decrypt → MsgType=text Content=ping`
- [ ] 客户端 5s 内不应看到 "未送达" 红圈
