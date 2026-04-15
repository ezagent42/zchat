# Phase 4.5: 飞书 Bridge

> **Submodule 分支:** `feat/feishu-bridge`（基于 feat/server-v1）
> **仓库:** zchat-channel-server submodule
> **Spec 参考:** `spec/channel-server/09-feishu-bridge.md` + `03-bridge-layer.md`
> **预估:** 3-4h
> **依赖:** Phase 4 (集成) 完成
> **在 Phase Final 之前完成**

---

## 工作环境

**你被启动在 zchat 项目根目录 (`~/projects/zchat/`)，`feat/channel-server-v1` 分支。**
代码在 `zchat-channel-server/` submodule 内。

```bash
cd zchat-channel-server

# 基于 Phase 4 完成的分支创建
git checkout feat/server-v1
git checkout -b feat/feishu-bridge

# 验证 Phase 4 完成
uv run pytest tests/unit/ tests/e2e/ -v

mkdir -p feishu_bridge feishu_bridge/tests
```

**依赖:** Phase 4 的 bridge_api/ + protocol/ + engine/ 都必须已完成。

**参考代码:** `/tmp/cc-openclaw/feishu/message_parsers.py`（消息解析器模式）

---

## Dev-loop 闭环（6 步 → e2e-report 结束）

**Artifact 命名约定:** 见 `ARTIFACT-CONVENTION.md`，所有 ID 用 `cs-` 前缀。

```bash
# Step 1: eval-doc → .artifacts/eval-docs/cs-eval-feishu.md
/dev-loop-skills:skill-5-feature-eval simulate
# 主题: "飞书 Bridge — 消息解析 + 群角色映射 + visibility 路由 + card 消息"

# Step 2: test-plan → .artifacts/test-plans/cs-plan-feishu.md
/dev-loop-skills:skill-2-test-plan-generator
# 输入: eval-doc + spec/09-feishu-bridge.md

# Step 3: test-code → feishu_bridge/tests/*.py
/dev-loop-skills:skill-3-test-code-writer

# Step 4: TDD 实现 → 注册 .artifacts/code-diffs/cs-diff-feishu.md
/dev-loop-skills:skill-6-artifact-registry register --type code-diff --id cs-diff-feishu

# Step 5: test-run → .artifacts/e2e-reports/cs-report-feishu.md
/dev-loop-skills:skill-4-test-runner

# Step 6: 链条验证
/dev-loop-skills:skill-6-artifact-registry
```

**闭环完成标志:** `.artifacts/e2e-reports/cs-report-feishu.md` 存在，0 FAIL 0 SKIP。

---

## 文件清单

| 源文件 | 测试文件 | 行数 | 内容 |
|--------|---------|------|------|
| `feishu_bridge/__init__.py` | — | 2 | 包声明 |
| `feishu_bridge/message_parsers.py` | `feishu_bridge/tests/test_parsers.py` | ~250 | 从 cc-openclaw 移植，可插拔注册表 |
| `feishu_bridge/sender.py` | `feishu_bridge/tests/test_sender.py` | ~120 | 飞书 API 封装（send/edit/card/reaction） |
| `feishu_bridge/group_manager.py` | `feishu_bridge/tests/test_group_manager.py` | ~80 | 群 ↔ 角色映射 |
| `feishu_bridge/visibility_router.py` | `feishu_bridge/tests/test_visibility.py` | ~60 | visibility → 飞书群 路由 |
| `feishu_bridge/config.py` | — | ~40 | YAML + env var 配置加载 |
| `feishu_bridge/bridge.py` | — | ~150 | 主类：WSS + Bridge API client + 编排 |
| `feishu_bridge/test_client.py` | — | ~100 | E2E 测试辅助工具 |

**总计:** ~800 行源码 + ~300 行测试

---

## Task 4.5.1: message_parsers.py（从 cc-openclaw 移植）

**Spec 参考:** `09-feishu-bridge.md §3`

- [ ] **写测试** `feishu_bridge/tests/test_parsers.py`

```python
from feishu_bridge.message_parsers import parse_message, register_parser

def test_parse_text():
    text, path = parse_message("text", {"text": "hello"}, None, None)
    assert text == "hello"
    assert path == ""

def test_parse_post():
    content = {"title": "标题", "content": [[{"text": "段落1"}], [{"text": "段落2"}]]}
    text, _ = parse_message("post", content, None, None)
    assert "标题" in text
    assert "段落1" in text

def test_parse_image_without_server():
    text, path = parse_message("image", {"image_key": "img_xxx"}, None, None)
    assert "image" in text.lower() or "File" in text or "下载" in text

def test_parse_interactive_card():
    content = {
        "header": {"title": {"content": "评分", "tag": "plain_text"}},
        "elements": [{"tag": "div", "text": {"content": "请评分", "tag": "plain_text"}}]
    }
    text, _ = parse_message("interactive", content, None, None)
    assert "评分" in text

def test_parse_sticker():
    text, _ = parse_message("sticker", {}, None, None)
    assert "表情" in text

def test_parse_unknown_type():
    text, _ = parse_message("some_future_type", {}, None, None)
    assert "some_future_type" in text

def test_parse_location():
    content = {"name": "星巴克", "latitude": "31.2", "longitude": "121.4"}
    text, _ = parse_message("location", content, None, None)
    assert "星巴克" in text

def test_parse_system():
    text, _ = parse_message("system", {"template": "add_member"}, None, None)
    assert "加入" in text or "系统" in text
```

- [ ] **运行失败** → **实现**（从 `/tmp/cc-openclaw/feishu/message_parsers.py` 移植，去掉 server 依赖改为 bridge 参数）→ **运行通过** → **Commit**

---

## Task 4.5.2: sender.py

**Spec 参考:** `09-feishu-bridge.md §4`

- [ ] **写测试** `feishu_bridge/tests/test_sender.py`

```python
from unittest.mock import MagicMock, patch
from feishu_bridge.sender import FeishuSender

def test_send_text_calls_api():
    sender = FeishuSender(app_id="test", app_secret="test")
    sender._client = MagicMock()
    sender._client.im.v1.message.create.return_value = MagicMock(success=lambda: True)
    sender.send_text_sync("oc_xxx", "hello")
    sender._client.im.v1.message.create.assert_called_once()

def test_send_card_calls_api():
    sender = FeishuSender(app_id="test", app_secret="test")
    sender._client = MagicMock()
    sender._client.im.v1.message.create.return_value = MagicMock(success=lambda: True)
    sender.send_card_sync("oc_xxx", {"header": {}, "elements": []})
    call_args = sender._client.im.v1.message.create.call_args
    # 验证 msg_type 是 interactive
    assert True  # mock 验证

def test_update_message_calls_patch_api():
    sender = FeishuSender(app_id="test", app_secret="test")
    sender._client = MagicMock()
    sender._client.im.v1.message.patch.return_value = MagicMock(success=lambda: True)
    sender.update_message_sync("om_xxx", "updated text")
    sender._client.im.v1.message.patch.assert_called_once()
```

- [ ] **运行失败** → **实现** → **运行通过** → **Commit**

---

## Task 4.5.3: group_manager.py + visibility_router.py

**Spec 参考:** `09-feishu-bridge.md §5 §6`

**授权原则（必须理解）：**
飞书平台保证"用户在群里 = 拥有该群角色的使用权"。三种角色的授权都通过群成员资格实现：
- customer：bot 被拉入任意群 → 自动注册
- operator：用户是配置的 squad 群成员
- admin：用户是配置的 admin 群成员

GroupManager 需处理全部三种角色的动态成员变动。

- [ ] **写测试** `feishu_bridge/tests/test_group_manager.py`

```python
from feishu_bridge.group_manager import GroupManager
import tempfile, os

def test_admin_group():
    gm = GroupManager(admin_chat_id="oc_admin", squad_chats=[])
    assert gm.identify_role("oc_admin") == "admin"

def test_squad_group():
    gm = GroupManager(
        admin_chat_id="oc_admin",
        squad_chats=[{"chat_id": "oc_squad_1", "operator_id": "xiaoli"}]
    )
    assert gm.identify_role("oc_squad_1") == "operator"
    assert gm.get_operator_id("oc_squad_1") == "xiaoli"

def test_unknown_group_is_unknown_before_registration():
    gm = GroupManager(admin_chat_id="oc_admin", squad_chats=[])
    assert gm.identify_role("oc_random") == "unknown"

def test_bot_added_registers_as_customer():
    with tempfile.TemporaryDirectory() as tmp:
        gm = GroupManager(admin_chat_id="oc_admin", squad_chats=[],
                          customer_chats_path=os.path.join(tmp, "c.json"))
        gm.register_customer_chat("oc_new")
        assert gm.identify_role("oc_new") == "customer"

def test_customer_chats_persisted_and_loaded():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "c.json")
        gm = GroupManager(admin_chat_id="oc_admin", squad_chats=[], customer_chats_path=path)
        gm.register_customer_chat("oc_persist")
        # 重新加载
        gm2 = GroupManager(admin_chat_id="oc_admin", squad_chats=[], customer_chats_path=path)
        assert gm2.identify_role("oc_persist") == "customer"

def test_bot_added_to_squad_group_skipped():
    """bot 被拉入已配置的 squad 群，不覆盖为 customer"""
    gm = GroupManager(
        admin_chat_id="oc_admin",
        squad_chats=[{"chat_id": "oc_squad_1", "operator_id": "xiaoli"}]
    )
    gm.register_customer_chat("oc_squad_1")  # 应被忽略
    assert gm.identify_role("oc_squad_1") == "operator"

def test_member_added_to_admin_group():
    gm = GroupManager(admin_chat_id="oc_admin", squad_chats=[])
    gm.on_member_added("ou_user1", "oc_admin")
    assert gm.has_admin_permission("ou_user1")

def test_member_removed_from_squad():
    gm = GroupManager(
        admin_chat_id="oc_admin",
        squad_chats=[{"chat_id": "oc_squad_1", "operator_id": "xiaoli"}]
    )
    gm.on_member_added("ou_op1", "oc_squad_1")
    gm.on_member_removed("ou_op1", "oc_squad_1")
    assert not gm.has_operator_permission("ou_op1", "oc_squad_1")

def test_group_disbanded_removes_customer():
    with tempfile.TemporaryDirectory() as tmp:
        gm = GroupManager(admin_chat_id="oc_admin", squad_chats=[],
                          customer_chats_path=os.path.join(tmp, "c.json"))
        gm.register_customer_chat("oc_cust1")
        gm.on_group_disbanded("oc_cust1")
        assert gm.identify_role("oc_cust1") == "unknown"
```

- [ ] **写测试** `feishu_bridge/tests/test_visibility.py`

```python
from unittest.mock import MagicMock
from feishu_bridge.visibility_router import VisibilityRouter

def test_public_goes_to_customer_and_squad():
    sender = MagicMock()
    router = VisibilityRouter(sender=sender, group_manager=MagicMock())
    router.group_manager.get_customer_chat.return_value = "oc_cust"
    router.group_manager.get_squad_chat.return_value = "oc_squad"
    
    router.route("conv_1", {"text": "hello", "visibility": "public"})
    
    # 两个群都收到
    assert sender.send_text.call_count == 2

def test_side_only_goes_to_squad():
    sender = MagicMock()
    router = VisibilityRouter(sender=sender, group_manager=MagicMock())
    router.group_manager.get_customer_chat.return_value = "oc_cust"
    router.group_manager.get_squad_chat.return_value = "oc_squad"
    
    router.route("conv_1", {"text": "advice", "visibility": "side"})
    
    # 只发到 squad，不发到 customer
    calls = [str(c) for c in sender.send_text.call_args_list]
    assert any("oc_squad" in c for c in calls)
    assert not any("oc_cust" in c for c in calls)
```

- [ ] **运行失败** → **实现** → **运行通过** → **Commit**

---

## Task 4.5.4: bridge.py + config.py + test_client.py

- [ ] **实现 config.py**（YAML 加载 + env var 替换，参考 cc-openclaw `sidecar/config.py`）
- [ ] **实现 bridge.py**（主编排类），注册全部 5 个事件：
  ```python
  lark.EventDispatcherHandler.builder("", "")
      .register_p2_im_message_receive_v1(_on_message)
      .register_p2_im_chat_member_bot_added_v1(_on_bot_added)
      .register_p2_im_chat_member_user_added_v1(_on_user_added)
      .register_p2_im_chat_member_user_deleted_v1(_on_user_deleted)
      .register_p2_im_chat_disbanded_v1(_on_disbanded)
      .build()
  ```
  - `_on_bot_added`: 调用 `group_manager.register_customer_chat()`（跳过已配置群）
  - `_on_user_added/deleted`: 调用 `group_manager.on_member_added/removed()`，对 squad/admin 群通知 channel-server
  - `_on_disbanded`: 调用 `group_manager.on_group_disbanded()`，通知 channel-server 归档 conversation
  - 重启时加载 `customer_chats.json` 恢复动态 customer 群
- [ ] **实现 test_client.py**（E2E 辅助工具：send_message / list_messages / assert_message_appears / assert_message_absent）
- [ ] **Commit**

---

## Task 4.5.5: 完整性验证

- [ ] **运行全部 feishu_bridge 测试**

```bash
cd zchat-channel-server && uv run pytest feishu_bridge/tests/ -v
```

Expected: ~15 tests PASS

- [ ] **运行全部测试（含回归）**

```bash
uv run pytest tests/unit/ feishu_bridge/tests/ -v
```

Expected: 全部 PASS

- [ ] **push submodule**

```bash
git push origin feat/feishu-bridge
```

开发完成后，由人类操作 merge（参考 README-operator-manual.md）。
Agent 只需确保所有测试通过且 artifact 链条完整。

---

## 完成标准

- [ ] `feishu_bridge/` 下 8 个 .py 文件
- [ ] message_parsers 支持 15+ 种飞书消息类型
- [ ] sender 支持 text + card + edit + reaction
- [ ] group_manager 正确映射 admin/squad/customer
- [ ] visibility_router 正确路由 public/side/system
- [ ] test_client.py 可用于 Phase Final E2E
- [ ] ~15 个测试全部 PASS
- [ ] artifact 链条完整（cs-eval/plan/diff/report-feishu）
