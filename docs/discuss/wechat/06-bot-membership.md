# 06 · Bot 成员事件 + lazy_create

## 1. 飞书事件清单（当前已订阅）

`feishu_bridge/bridge.py`：

| event | 触发 | feishu_bridge 行为 |
|---|---|---|
| `im.message.receive_v1` | 群里有新消息 | 主消息流转（详见 04 parser）|
| `im.chat.member.bot_added_v1` | bot 被拉进新群 | 触发 lazy_create（如果 bot config enabled）|
| `im.chat.member.user_added_v1` | 群有新用户进 | 仅 log，不动 |
| `im.chat.member.user_deleted_v1` | 群里用户退 | 仅 log，不动 |
| `im.chat.disbanded_v1` | 群被解散 | _remove_channel_by_chat |

## 2. WeCom 等价事件

WeCom 群成员变更通过 `event` 类型的 callback：

| WeCom Event / ChangeType | 触发 | 飞书对应 |
|---|---|---|
| `change_external_chat` (`add_external_contact`) | bot 被拉进群 | bot_added_v1 |
| `change_external_chat` (`del_external_contact`) | bot 被移除 | disbanded_v1（部分场景）|
| `change_external_chat` (`add_member_external_chat`) | 群里加人 | user_added_v1 |
| `change_external_chat` (`del_member_external_chat`) | 群里有人退 | user_deleted_v1 |
| `change_external_chat` (`dismiss_external_chat`) | 群解散 | disbanded_v1 |
| `change_external_contact` 各种 ChangeType | 单聊客户事件（add_half_external_contact / 等）| (飞书无对应) |

callback XML 示例（bot 被加入群）:

```xml
<xml>
  <ToUserName>ww123abc</ToUserName>
  <FromUserName>sys</FromUserName>
  <CreateTime>1672531200</CreateTime>
  <MsgType>event</MsgType>
  <Event>change_external_chat</Event>
  <ChangeType>add_external_contact</ChangeType>
  <ChatId>wm_xxxxxx</ChatId>
  <UpdateDetail>add_member|wm_xxxxxx</UpdateDetail>
  <JoinScene>1</JoinScene>
  <FailReason></FailReason>
</xml>
```

## 3. wecom_bridge 事件路由

`wecom_callback_handler.WeComCallbackServer._receive` 已按 MsgType + Event 分发到不同 handler。bridge 注入：

```python
self._callback = WeComCallbackServer(
    on_message=self._on_message,
    on_event=self._on_event,
    on_chat_member=self._on_chat_member,   # change_external_chat / change_external_contact
    on_card_action=self._on_card_action,
)


async def _on_chat_member(self, msg: dict) -> None:
    change_type = msg.get("ChangeType", "")
    chat_id = msg.get("ChatId", "")

    if change_type == "add_external_contact" and msg.get("FromUserName") == "sys":
        # bot 被拉进群
        log.info("[event] bot added to chat %s", chat_id)
        await self._lazy_create_channel_and_agent(chat_id)
    elif change_type == "dismiss_external_chat":
        log.info("[event] chat %s dismissed", chat_id)
        await self._remove_channel_by_chat(chat_id)
    else:
        log.debug("ignore chat_member event %s", change_type)
```

判断"bot 被加入"的方式（飞书有 user_id，WeCom 用 `FromUserName=sys` + `add_external_contact`）。

## 4. lazy_create 流程对照

### 飞书

`feishu_bridge.bridge._lazy_create_channel_and_agent(chat_id)`：

1. 检查 routing.toml `[bots.<bot>] lazy_create_enabled = true`
2. 拉群信息：`get_chat_info(chat_id)` → 拿 chat_name
3. 生成 channel_id: `f"{prefix}-{hash8(chat_id)}"`（如 `conv-669ca17b`）
4. 调 zchat CLI: `zchat channel create <channel_id> --bot <bot> --external-chat <chat_id>`
5. 创 entry agent: `zchat agent create <short> --type <template> --channel <channel_id>`
6. 重新 load routing → mappings 更新
7. emit `chat_info` event 给 channel_server，让 supervisor bridge 知道有新 conv

### WeCom

完全相同逻辑！只需替换：
- `get_chat_info` 调用：`self.sender.get_chat_info_sync(chat_id)` → 内部调 `appchat/get`
- `zchat channel create` 命令保留
- `_run_cli` 不变

代码层面 `_lazy_create_channel_and_agent` 几乎可以原样从 feishu_bridge 拷贝过来，只需改：
1. log 字符串里的 "feishu" → "wecom"
2. `get_chat_info` 方法签名一致
3. channel_prefix 可保持 `conv-` 通用

## 5. WeCom 群拉 bot 操作流（部署阶段）

WeCom 自建应用想被加入群，需要：
1. 应用要勾选"接收会话内容"权限
2. 客户群 owner 添加 bot 用户作为 external_contact（外部联系人）— **WeCom 的 bot user 实际是 corp 的真实用户**
3. 群 owner 在群里 @bot 名字 → 群组事件触发 → callback 进 wecom_bridge

跟飞书 "在群里 @机器人 邀请" 流程类似，但 WeCom 操作步骤多。

## 6. 用户 add/del 事件处理（本期不做）

飞书的 `user_added/deleted_v1` 在当前 feishu_bridge 里只 log，不做实质动作。WeCom 同。
未来如果要：
- 客户进群 → 自动发欢迎语 → 用 `add_member_external_chat` event
- 客户退群 → 自动结束 conversation → 用 `del_member_external_chat`

## 7. 群解散（24h grace）

WeCom `dismiss_external_chat` 触发时调 `_remove_channel_by_chat(chat_id)`：

```python
async def _remove_channel_by_chat(self, chat_id: str) -> None:
    channel_id = self._reverse_mapping.get(chat_id)
    if not channel_id:
        return
    log.info("[event] removing channel %s (chat %s dismissed)", channel_id, chat_id)
    rc, _, _ = await self._run_cli("channel", "remove", channel_id, "--stop-agents")
    if rc == 0:
        await self._reload_mappings()
```

跟飞书完全一样。

## 8. 测试

```python
# tests/unit/test_wecom_membership.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from wecom_bridge.bridge import WeComBridge


@pytest.mark.asyncio
async def test_bot_added_triggers_lazy_create():
    config = MagicMock()
    config.lazy_create.enabled = True
    config.lazy_create.entry_agent_template = "fast-agent"
    bridge = WeComBridge(config, "/tmp/routing.toml")
    bridge._lazy_create_channel_and_agent = AsyncMock()

    msg = {
        "FromUserName": "sys",
        "MsgType": "event",
        "Event": "change_external_chat",
        "ChangeType": "add_external_contact",
        "ChatId": "wm_xxx",
    }
    await bridge._on_chat_member(msg)
    bridge._lazy_create_channel_and_agent.assert_awaited_with("wm_xxx")


@pytest.mark.asyncio
async def test_dismiss_calls_remove():
    config = MagicMock()
    bridge = WeComBridge(config, "/tmp/routing.toml")
    bridge._remove_channel_by_chat = AsyncMock()

    msg = {
        "MsgType": "event",
        "Event": "change_external_chat",
        "ChangeType": "dismiss_external_chat",
        "ChatId": "wm_xxx",
    }
    await bridge._on_chat_member(msg)
    bridge._remove_channel_by_chat.assert_awaited_with("wm_xxx")
```

## 9. 真机 checklist

- [ ] WeCom 后台 → 应用管理 → 我的应用 → 选 bot → "可调用接口" 勾"接收会话内容"
- [ ] 群 owner 拉 bot 进群 → wecom_bridge log 看到 `[event] bot added to chat wm_xxxxxx`
- [ ] 项目 routing.toml 自动多一条 `[channels."#conv-xxxxx"]`
- [ ] 项目 state.json 多一个 entry agent
- [ ] 客户在该群发"hi" → IRC 收到 → fast-agent 回复 → 客户在群看到
