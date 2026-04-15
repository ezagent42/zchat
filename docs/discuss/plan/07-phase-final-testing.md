# Phase Final: Pre-release 验收测试

> **执行位置:** `~/projects/zchat/`（feat/channel-server-v1 分支）
> **仓库:** zchat-channel-server submodule
> **Spec 参考:** `spec/channel-server/05-user-journeys.md` + `09-feishu-bridge.md §7`
> **预估:** 3-4h
> **依赖:** Phase 4.5 (飞书 Bridge) 完成

---

## 工作环境

**你被启动在 zchat 项目根目录 (`~/projects/zchat/`)。**
所有 Phase 1-4.5 在 submodule 内已完成。

```bash
cd zchat-channel-server

# 确认所有模块可用
uv run python -c "
from protocol.gate import gate_message
from engine.conversation_manager import ConversationManager
from bridge_api.ws_server import BridgeAPIServer
from transport.irc_transport import IRCTransport
from feishu_bridge.message_parsers import parse_message
from feishu_bridge.test_client import FeishuTestClient
print('All v1.0 modules + feishu_bridge OK')
"

# 确认 unit + E2E 基线全部通过
uv run pytest tests/unit/ tests/e2e/ feishu_bridge/tests/ -v
```

**依赖:** Phase 4.5 (飞书 Bridge) 必须已完成。

### Phase Final 前置：命令 Handler 补全

Phase 4 中以下命令已有 parser 但缺少 handler，**必须在 Phase Final 前实现**：

| 命令 | handler 位置 | 逻辑 |
|------|-------------|------|
| `/resolve` | `_on_operator_command()` | → `conversation_manager.resolve()` → Bridge 发 `csat_request` |
| `/status` | `_on_admin_command()` | → `conversation_manager.list_active()` → 格式化返回 |
| `/dispatch` | `_on_admin_command()` | → 指定 agent JOIN conversation → 通知 agent MCP |

实现模式参考现有 `/hijack` handler（`server.py:412-443`）。
详见 `spec/channel-server/06-gap-fixes.md` "实现状态追踪" 章节。

---

## Dev-loop 闭环（6 步 — verify 模式）

**Artifact 命名约定:** 见 `ARTIFACT-CONVENTION.md`，所有 ID 用 `cs-` 前缀。

```bash
# Step 1: eval-doc (verify 模式)
/dev-loop-skills:skill-5-feature-eval verify
# 主题: "channel-server v1.0 端到端验收（含飞书真实环境）"

# Step 2: test-plan → .artifacts/test-plans/cs-plan-prerelease.md
/dev-loop-skills:skill-2-test-plan-generator

# Step 3: test-code → tests/pre_release/*.py
/dev-loop-skills:skill-3-test-code-writer

# Step 4: 执行验收测试

# Step 5: test-run → .artifacts/e2e-reports/cs-report-prerelease.md
/dev-loop-skills:skill-4-test-runner

# Step 6: artifact 注册
/dev-loop-skills:skill-6-artifact-registry register --type e2e-report --id cs-report-prerelease
```

**闭环完成标志:** `.artifacts/e2e-reports/cs-report-prerelease.md` 存在，0 FAIL 0 SKIP。

---

## 三层验收

### Layer 1: Unit 回归（所有 Phase 测试）

```bash
uv run pytest tests/unit/ feishu_bridge/tests/ -v
```

Expected: ~70+ tests PASS

### Layer 2: E2E — Bridge API（无需飞书凭证）

```bash
uv run pytest tests/e2e/ -v -m e2e --timeout=30
```

通过 WebSocket 模拟 Bridge，验证协议行为（conversation lifecycle, mode switching, gate enforcement）。

### Layer 3: Pre-release — 飞书真实环境（需要飞书凭证）

**前提：**
- `.feishu-credentials.json` 存在（app_id + app_secret）
- 3 个飞书测试群已创建，bot 已加入
- `feishu-e2e-config.yaml` 配置正确

---

## Full Stack 启动流程（Pre-release 前置）

Pre-release 测试需要完整的 zchat 运行栈。zchat 通过 Zellij session 管理所有进程——channel-server 不是独立进程，而是作为 MCP server 运行在 Claude Code session 内部。

### 启动链路

```
zchat agent create fast-agent
  → Zellij tab (fast-agent)
    → start.sh
      → .mcp.json (配置 zchat-channel 为 MCP server)
      → .claude/settings.local.json (SessionStart hook → .ready marker)
      → claude --permission-mode bypassPermissions
        → channel-server 作为 MCP server 启动
          ├── Bridge API WebSocket :9999（feishu_bridge 连这里）
          ├── IRC 连接 ergo（内部 transport）
          └── MCP stdio（Claude Code 调 reply/edit_message 等 tools）
```

### Step 1: 项目准备（一次性）

```bash
cd ~/projects/zchat

# 创建测试专用项目
zchat project create prerelease-test

# 配置开发模式 MCP server 命令（指向本地 submodule）
zchat config set agents.mcp_server_cmd \
  '["uv", "run", "--project", "zchat-channel-server", "zchat-channel"]'

# 配置 Bridge API 端口（默认 9999，如需自定义可在 .env 中覆盖）
# BRIDGE_PORT=9999 已是默认值
```

### Step 2: 启动 IRC + Agent

```bash
# 启动 ergo IRC server
zchat irc daemon start

# 创建 fast-agent
# 这一步会：
#   1. 创建 Zellij tab
#   2. 渲染 .env → 写入 workspace/.zchat-env
#   3. 运行 start.sh → 生成 .mcp.json + settings.json
#   4. 启动 Claude Code → 加载 channel-server MCP
#   5. channel-server 启动 Bridge API :9999 + 连接 IRC
#   6. SessionStart hook → touch .ready marker
#   7. agent manager 检测到 .ready → status=running
zchat agent create fast-agent
# 阻塞等待 .ready（最多 60s）

# 验证
zchat agent list
# fast-agent: running
```

### Step 3: 启动飞书 Bridge

```bash
cd ~/projects/zchat/zchat-channel-server

# feishu_bridge 作为独立进程，连接 channel-server 的 Bridge API
FEISHU_APP_ID=xxx FEISHU_APP_SECRET=xxx \
  uv run python -m feishu_bridge.bridge \
    --config tests/pre_release/feishu-e2e-config.yaml
```

feishu_bridge 连接 `ws://localhost:9999`（channel-server 在 Claude Code 内开放的 Bridge API）。

### Step 4: 运行 Pre-release 测试

```bash
cd ~/projects/zchat/zchat-channel-server

# Layer 1: Unit 回归
uv run pytest tests/unit/ feishu_bridge/tests/ -v

# Layer 2: E2E Bridge API（无需飞书凭证）
uv run pytest tests/e2e/ -v -m e2e --timeout=30

# Layer 3: 飞书真实环境（需要飞书凭证 + 真实 Claude 响应）
FEISHU_APP_ID=xxx FEISHU_APP_SECRET=xxx \
  uv run pytest tests/pre_release/test_feishu_e2e.py -v -m prerelease --timeout=120
```

### 自动化 fixture（test_feishu_e2e.py 的 full_stack）

`full_stack` fixture 通过 zchat CLI 自动化 Step 1-3：

```python
@pytest.fixture(scope="module")
def full_stack(feishu_config):
    """通过 zchat CLI 启动完整运行栈：ergo + agent(channel-server) + feishu_bridge

    前提：
    - 在 Zellij session 内运行（zchat 通过 Zellij 管理 agent tab）
    - Claude API key 已配置（agent 需要真实 Claude Code session）
    - feishu 凭证通过环境变量或 config 传入
    """
    import subprocess, time, os

    project_dir = os.environ.get("ZCHAT_PROJECT_DIR",
                                  os.path.expanduser("~/.zchat/projects/prerelease-test"))

    # 1. 确保项目存在
    subprocess.run(["zchat", "project", "create", "prerelease-test"],
                   capture_output=True)  # 幂等，已存在不报错
    subprocess.run(["zchat", "project", "use", "prerelease-test"], check=True)

    # 2. 启动 IRC daemon
    subprocess.run(["zchat", "irc", "daemon", "start"], check=True)
    time.sleep(2)

    # 3. 创建 agent（启动 Zellij tab → Claude Code → channel-server MCP）
    #    阻塞等待 .ready marker（最多 60s）
    result = subprocess.run(
        ["zchat", "agent", "create", "fast-agent"],
        timeout=90, check=True
    )

    # 4. 验证 Bridge API 可达
    import websockets, asyncio
    async def _check_bridge():
        bridge_url = feishu_config.get("channel_server", {}).get("url", "ws://localhost:9999")
        async with websockets.connect(bridge_url) as ws:
            await ws.send('{"type":"register","bridge_type":"test","instance_id":"test-probe","capabilities":["customer"]}')
            resp = await asyncio.wait_for(ws.recv(), timeout=5)
            assert "registered" in resp
            await ws.close()
    asyncio.get_event_loop().run_until_complete(_check_bridge())

    # 5. 启动 feishu_bridge
    bridge_proc = subprocess.Popen([
        "uv", "run", "python", "-m", "feishu_bridge.bridge",
        "--config", "tests/pre_release/feishu-e2e-config.yaml"
    ], cwd=str(Path(__file__).parent.parent.parent))  # zchat-channel-server/
    time.sleep(3)

    yield

    # 清理
    bridge_proc.terminate()
    bridge_proc.wait(timeout=10)
    subprocess.run(["zchat", "agent", "stop", "fast-agent"], check=False)
    subprocess.run(["zchat", "irc", "daemon", "stop"], check=False)
```

### 测试 timeout 说明

Pre-release 测试的 timeout 比 E2E 长（120s vs 30s），因为：
- 真实 Claude Code 响应需要 5-15s（取决于查询复杂度）
- edit_message 流程（占位 → 慢查询 → 编辑）需要 10-20s
- Timer 超时测试需要等待缩短后的 timer（10-12s）

### 无 Zellij 环境的降级方案

如果测试环境没有 Zellij（如 CI），可以降级为直接启动 channel-server：

```bash
# 直接启动 channel-server（无 Claude Code，无真实 agent 回复）
cd zchat-channel-server
AGENT_NAME=test-agent IRC_SERVER=127.0.0.1 IRC_PORT=6667 IRC_CHANNELS="#general" \
  uv run zchat-channel &

# 此模式下 channel-server 的 MCP stdio 无人读取，但 Bridge API 和 IRC 正常工作
# 测试只能验证协议行为（Gate/Mode/Routing），不能验证 agent 回复内容
```

---

## 飞书 E2E 测试群配置

### 需要的飞书群

| 群名 | chat_id 配置项 | 用途 | 成员 |
|------|--------------|------|------|
| `[测试]客户对话` | `customer_chat` | 模拟客户聊天 | bot |
| `[测试]小李分队` | `squad_chat` | 模拟人工客服工作区 | bot |
| `[测试]管理群` | `admin_chat` | 模拟管理员操作 | bot |

### 配置文件

```yaml
# tests/pre_release/feishu-e2e-config.yaml
feishu:
  app_id: ${FEISHU_APP_ID}
  app_secret: ${FEISHU_APP_SECRET}

groups:
  customer_chat: "oc_customer_test_xxx"
  squad_chat: "oc_squad_test_xxx"
  admin_chat: "oc_admin_test_xxx"

channel_server:
  bridge_port: 9999
  irc_port: 6667
  # 测试环境 timer 缩短（正式环境为 180s/300s/3600s）
  timers:
    takeover_wait: 10      # 正式 180s → 测试 10s
    idle_timeout: 12       # 正式 300s → 测试 12s
    close_timeout: 30      # 正式 3600s → 测试 30s
```

---

## 飞书 E2E 测试代码

```python
# tests/pre_release/test_feishu_e2e.py
"""全自动飞书 E2E 测试 — 6 步状态机完整走通"""

import time
import pytest
import yaml
from feishu_bridge.test_client import FeishuTestClient

@pytest.fixture(scope="module")
def feishu_config():
    with open("tests/pre_release/feishu-e2e-config.yaml") as f:
        return yaml.safe_load(f)

@pytest.fixture(scope="module")
def feishu(feishu_config):
    cfg = feishu_config["feishu"]
    return FeishuTestClient(cfg["app_id"], cfg["app_secret"])

@pytest.fixture(scope="module")
def groups(feishu_config):
    return feishu_config["groups"]

@pytest.fixture(scope="module")
def full_stack():
    """启动 ergo + channel-server + feishu_bridge"""
    # ... 启动进程 ...
    yield
    # ... 清理 ...


@pytest.mark.prerelease
class TestFeishuFullJourney:
    """PRD 6 步状态机端到端验证"""

    def test_step1_customer_onboard(self, feishu, groups, full_stack):
        """US-2.1: 客户接入 → agent 回复"""
        feishu.send_message(groups["customer_chat"], "B 套餐多少钱")
        msg = feishu.assert_message_appears(
            groups["customer_chat"],
            contains="套餐",
            timeout=15
        )
        assert msg is not None

    def test_step2_squad_notification(self, feishu, groups, full_stack):
        """US-2.3: 分队群收到对话通知"""
        feishu.assert_message_appears(
            groups["squad_chat"],
            contains="进行中",
            timeout=10
        )

    def test_step3_copilot_gate(self, feishu, groups, full_stack):
        """US-2.4: copilot 模式 — operator 消息不到客户群"""
        # operator 加入
        feishu.send_message(groups["squad_chat"], "进入对话")
        time.sleep(3)

        # operator 发建议
        test_text = f"建议强调优惠_{int(time.time())}"  # 唯一标识
        feishu.send_message(groups["squad_chat"], test_text)
        time.sleep(5)

        # 验证: 客户群没有这条消息
        feishu.assert_message_absent(
            groups["customer_chat"],
            contains=test_text,
            wait=8
        )

        # 验证: 分队群有这条消息
        feishu.assert_message_appears(
            groups["squad_chat"],
            contains=test_text,
            timeout=3
        )

    def test_step4_hijack(self, feishu, groups, full_stack):
        """US-2.5: /hijack → takeover"""
        feishu.send_message(groups["squad_chat"], "/hijack")
        feishu.assert_message_appears(
            groups["squad_chat"],
            contains="takeover",
            timeout=10
        )

    def test_step5_operator_message_reaches_customer(self, feishu, groups, full_stack):
        """US-2.6: takeover 下人工消息到客户"""
        operator_text = f"您好我是客服小李_{int(time.time())}"
        feishu.send_message(groups["squad_chat"], operator_text)

        # 验证: 客户群收到
        feishu.assert_message_appears(
            groups["customer_chat"],
            contains="客服小李",
            timeout=10
        )

    def test_step6_resolve_and_csat(self, feishu, groups, full_stack):
        """US-2.6: /resolve → CSAT"""
        feishu.send_message(groups["squad_chat"], "/resolve")

        # 验证: 客户群收到 CSAT 卡片
        feishu.assert_message_appears(
            groups["customer_chat"],
            contains="评分",
            timeout=10
        )


@pytest.mark.prerelease
class TestFeishuPlaceholderAndEdit:
    """US-2.2: 占位消息 + 续写替换 — 快慢双模型核心体验"""

    def test_placeholder_then_edit(self, feishu, groups, full_stack):
        """US-2.2: 复杂查询 → 占位 → edit_message 替换"""
        feishu.send_message(groups["customer_chat"], "A 和 B 套餐的详细对比？能不能自定义？")

        # 先出现占位消息
        placeholder = feishu.assert_message_appears(
            groups["customer_chat"],
            contains="稍等",
            timeout=5
        )
        assert placeholder is not None

        # 占位消息被编辑替换为完整回答
        feishu.assert_message_edited(
            groups["customer_chat"],
            message_id=placeholder.id,
            contains="套餐",
            timeout=20
        )

    def test_edit_visible_in_squad(self, feishu, groups, full_stack):
        """编辑后的消息在分队群也能看到更新"""
        # 验证 squad 群中的消息也被更新
        feishu.assert_message_appears(
            groups["squad_chat"],
            contains="套餐",
            timeout=10
        )


@pytest.mark.prerelease
class TestFeishuTimerAndEscalation:
    """US-2.5: Agent @operator 求助 + 180s 超时退回"""

    def test_agent_escalation_notifies_squad(self, feishu, groups, full_stack):
        """Agent 判断超出能力 → 在分队群 @operator"""
        feishu.send_message(groups["customer_chat"], "我要退货，你们客服经理在吗")

        # Agent 在分队群发求助
        feishu.assert_message_appears(
            groups["squad_chat"],
            contains="接管",
            timeout=15
        )

        # 客户看到"正在转接"
        feishu.assert_message_appears(
            groups["customer_chat"],
            contains="转接",
            timeout=10
        )

    def test_timeout_reverts_to_auto(self, feishu, groups, full_stack):
        """180s 无人接管 → mode 退回 auto + 安抚消息

        注意: 测试环境中 timer 缩短为 10s
        """
        # 触发 agent 求助（不做 /hijack）
        feishu.send_message(groups["customer_chat"], "我要找经理投诉")
        time.sleep(3)

        # 不执行 /hijack，等待 timer 超时
        # （测试配置中 takeover_wait = 10s）

        # 客户应收到安抚消息
        feishu.assert_message_appears(
            groups["customer_chat"],
            contains="抱歉",
            timeout=15
        )

        # 分队群应显示退回通知
        feishu.assert_message_appears(
            groups["squad_chat"],
            contains="退回",
            timeout=5
        )


@pytest.mark.prerelease
class TestFeishuCSATFlow:
    """US-2.6 补充: CSAT 评分提交完整闭环"""

    def test_csat_score_submission(self, feishu, groups, full_stack):
        """客户点击评分 → csat_response → set_csat 闭环"""
        # 前置: 建立 takeover 并 /resolve
        feishu.send_message(groups["customer_chat"], "你好")
        time.sleep(5)
        feishu.send_message(groups["squad_chat"], "/hijack")
        time.sleep(3)
        feishu.send_message(groups["squad_chat"], "/resolve")

        # 客户看到评分卡片
        feishu.assert_message_appears(
            groups["customer_chat"],
            contains="评分",
            timeout=10
        )

        # 模拟客户点击评分（通过 card action callback）
        feishu.click_card_action(
            groups["customer_chat"],
            action_value="5"
        )

        # 管理群应收到 CSAT 记录确认
        feishu.assert_message_appears(
            groups["admin_chat"],
            contains="CSAT",
            timeout=10
        )


@pytest.mark.prerelease
class TestFeishuConversationReactivation:
    """US-2.1 补充: 老客户重新进入 → 加载历史上下文"""

    def test_reactivation_loads_history(self, feishu, groups, full_stack):
        """闲置对话重新激活，客户看到有上下文的回复"""
        # 第一轮对话
        feishu.send_message(groups["customer_chat"], "B 套餐多少钱")
        feishu.assert_message_appears(
            groups["customer_chat"], contains="套餐", timeout=15)

        # 等待对话进入 idle（测试环境 idle_timeout 缩短）
        time.sleep(15)

        # 第二轮对话（同一个 customer_chat → 同一个 conversation_id）
        feishu.send_message(groups["customer_chat"], "我之前问的那个套餐，能打折吗")

        # Agent 应基于历史上下文回答（提到 B 套餐）
        msg = feishu.assert_message_appears(
            groups["customer_chat"], timeout=15)
        assert msg is not None  # 有回复说明 conversation 被 reactivate


@pytest.mark.prerelease
class TestFeishuGateIsolation:
    """Gate 强制执行验证 — 最关键的安全测试"""

    def test_takeover_agent_side_not_in_customer(self, feishu, groups, full_stack):
        """takeover 下 agent 消息降为 side，客户看不到"""
        # 需要先建立 takeover 状态
        feishu.send_message(groups["customer_chat"], "需要帮助")
        time.sleep(5)
        feishu.send_message(groups["squad_chat"], "/hijack")
        time.sleep(3)

        # agent 自动发 side 建议（soul.md 行为）
        # 验证: 分队群看到 [侧栏] 标签
        feishu.assert_message_appears(
            groups["squad_chat"],
            contains="侧栏",
            timeout=10
        )

        # 验证: 客户群没有侧栏消息
        feishu.assert_message_absent(
            groups["customer_chat"],
            contains="侧栏",
            wait=5
        )

    def test_copilot_operator_not_in_customer(self, feishu, groups, full_stack):
        """copilot 下 operator 消息降为 side，客户看不到"""
        feishu.send_message(groups["customer_chat"], "你好")
        time.sleep(5)
        # operator 加入 → copilot
        feishu.send_message(groups["squad_chat"], "进入对话")
        time.sleep(3)

        test_text = f"内部建议_{int(time.time())}"
        feishu.send_message(groups["squad_chat"], test_text)
        time.sleep(5)

        # 客户群不应看到
        feishu.assert_message_absent(
            groups["customer_chat"], contains=test_text, wait=5)

        # 分队群应看到
        feishu.assert_message_appears(
            groups["squad_chat"], contains=test_text, timeout=3)


@pytest.mark.prerelease
class TestFeishuAdminCommands:
    """管理群命令测试 — US-3.2"""

    def test_status_command(self, feishu, groups, full_stack):
        """US-3.2: /status 返回当前 active 对话列表"""
        # 先触发一个 active 对话
        feishu.send_message(groups["customer_chat"], "你好")
        time.sleep(5)

        feishu.send_message(groups["admin_chat"], "/status")
        msg = feishu.assert_message_appears(
            groups["admin_chat"],
            contains="active",
            timeout=10
        )
        # 应包含对话数量和状态信息
        assert msg is not None

    def test_dispatch_command(self, feishu, groups, full_stack):
        """US-3.2: /dispatch 将指定 agent 派发到对话"""
        # 先触发一个对话
        feishu.send_message(groups["customer_chat"], "需要深度分析")
        time.sleep(5)

        # admin 派发 deep-agent
        feishu.send_message(groups["admin_chat"], "/dispatch conv_id deep-agent")
        feishu.assert_message_appears(
            groups["admin_chat"],
            contains="已加入",
            timeout=10
        )


@pytest.mark.prerelease
class TestFeishuAuthorizationModel:
    """授权模型验证 — 群成员资格 = 使用权限

    验证三种角色的群成员授权：
    - customer: bot 被拉入群 → 自动注册
    - operator: 配置的 squad 群成员 → operator 权限
    - admin: 配置的 admin 群成员 → admin 权限
    """

    def test_customer_group_auto_registered_on_bot_added(self, feishu, groups, full_stack):
        """bot 被拉入新群 → 自动注册为 customer conversation"""
        # 前提：groups["customer_chat"] 是 bot 已加入的群
        # 发消息后应创建 conversation
        feishu.send_message(groups["customer_chat"], "你好")
        feishu.assert_message_appears(
            groups["customer_chat"],
            contains="",  # 有任意回复即说明 conversation 已建立
            timeout=15
        )

    def test_operator_in_squad_group_can_use_operator_commands(self, feishu, groups, full_stack):
        """squad 群成员可使用 /hijack 等 operator 命令"""
        # 先建立一个 active conversation
        feishu.send_message(groups["customer_chat"], "需要帮助")
        time.sleep(5)
        # squad 群成员发送 operator 命令
        feishu.send_message(groups["squad_chat"], "/hijack")
        feishu.assert_message_appears(
            groups["squad_chat"],
            contains="takeover",
            timeout=10
        )

    def test_admin_in_admin_group_can_use_admin_commands(self, feishu, groups, full_stack):
        """admin 群成员可使用 /status 等 admin 命令"""
        feishu.send_message(groups["admin_chat"], "/status")
        feishu.assert_message_appears(
            groups["admin_chat"],
            contains="active",
            timeout=10
        )

    def test_customer_cannot_use_operator_commands(self, feishu, groups, full_stack):
        """customer 群发 operator 命令 → 被忽略或返回错误"""
        feishu.send_message(groups["customer_chat"], "/hijack")
        # customer 群不应出现 takeover 确认（命令无效）
        feishu.assert_message_absent(
            groups["customer_chat"],
            contains="takeover",
            wait=5
        )

    def test_group_disbanded_archives_conversation(self, feishu, groups, full_stack):
        """群解散 → conversation 归档（此测试为手动验证，标记 skip）"""
        pytest.skip("群解散需要手动操作，在 evidence/ 目录保存截图验证")
```

### FeishuTestClient 新增方法

Phase 4.5 的 `test_client.py` 需要额外支持以下方法（在 Phase Final 中使用）：

| 方法 | 用途 | 测试类 |
|------|------|--------|
| `assert_message_edited(chat_id, message_id, contains, timeout)` | 验证飞书消息被编辑（edit_message → sender.update_message_sync） | TestFeishuPlaceholderAndEdit |
| `click_card_action(chat_id, action_value)` | 模拟点击 interactive card 按钮（CSAT 评分） | TestFeishuCSATFlow |

如果 `click_card_action` 依赖飞书 card action callback 无法自动化，该测试标记为 `pytest.skip("card action 需手动验证")`，在 evidence/ 保存截图。

### 运行命令

```bash
# 需要飞书凭证
FEISHU_APP_ID=xxx FEISHU_APP_SECRET=xxx \
  uv run pytest tests/pre_release/test_feishu_e2e.py -v -m prerelease --timeout=120
```

---

## Walkthrough 录制

```bash
# asciinema 录制完整流程
asciinema rec tests/pre_release/evidence/feishu-e2e.cast -c \
  "uv run pytest tests/pre_release/ -v -m prerelease --timeout=120"
```

---

## 证据保存

```
tests/pre_release/evidence/
├── feishu-e2e.cast              # asciinema 录制
├── unit-regression.log          # unit 测试输出
├── e2e-bridge-api.log           # Bridge API E2E 输出
├── feishu-e2e.log               # 飞书 E2E 输出
└── gate-isolation.log           # Gate 隔离验证输出
```

---

## PRD 覆盖对照表

| PRD User Story | 测试类 | 覆盖状态 |
|---|---|---|
| US-2.1 客户接入 + 3s 问候 | TestFeishuFullJourney.test_step1 + TestFeishuConversationReactivation | ✅ |
| US-2.2 占位 + 续写替换 | TestFeishuPlaceholderAndEdit | ✅ |
| US-2.3 分队卡片通知 | TestFeishuFullJourney.test_step2 | ✅ |
| US-2.4 Copilot 模式 | TestFeishuFullJourney.test_step3 + TestFeishuGateIsolation.copilot | ✅ |
| US-2.5 两种触发 (/hijack + @operator timeout) | TestFeishuFullJourney.test_step4 + TestFeishuTimerAndEscalation | ✅ |
| US-2.6 角色翻转 + /resolve + CSAT | TestFeishuFullJourney.test_step5/6 + TestFeishuCSATFlow | ✅ |
| US-3.2 管理命令 (/status + /dispatch) | TestFeishuAdminCommands | ✅ |
| 授权模型 (3 角色 + 群成员资格) | TestFeishuAuthorizationModel | ✅ |
| Gate 安全隔离 | TestFeishuGateIsolation | ✅ |

## 完成标准

- [ ] **前置: 命令 handler 补全** — /resolve + /status + /dispatch handler 已实现并有 unit test
- [ ] Unit 回归: 全部 PASS (~130+ tests，含 Phase 4.5 feishu_bridge)
- [ ] E2E Bridge API: 全部 PASS (7+ scenarios，含 mode switching + gate enforcement)
- [ ] 飞书 E2E 6 步状态机: 全部 PASS
- [ ] 飞书 占位+续写 (edit_message): 全部 PASS
- [ ] 飞书 Timer+超时退回: 全部 PASS
- [ ] 飞书 CSAT 评分提交闭环: 全部 PASS
- [ ] 飞书 老客户 reactivation: 全部 PASS
- [ ] 飞书 Gate 隔离验证: 全部 PASS
- [ ] 飞书管理命令验证 (/status + /dispatch): 全部 PASS
- [ ] 飞书授权模型验证: 全部 PASS
- [ ] `.artifacts/e2e-reports/cs-report-prerelease.md` 存在，0 FAIL 0 SKIP
- [ ] evidence/ 目录有完整录制
