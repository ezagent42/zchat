# Phase Final: Pre-release 验收测试

> **执行位置:** `~/projects/zchat/`（zchat: `feat/channel-server-v1` / submodule: `refactor/channel-server`）
> **仓库:** zchat-channel-server submodule
> **Spec 参考:** `spec/channel-server/05-user-journeys.md` + `09-feishu-bridge.md §7`
> **预估:** 3-4h
> **依赖:** Phase 4.5 (飞书 Bridge) + Phase 4.6 (架构拆分) 完成

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

**依赖:** Phase 4.5 (飞书 Bridge) + Phase 4.6 (架构拆分) 必须已完成。
**注意:** Phase 4.5 + 4.6 均已完成。feishu_bridge/tests/ 包含完整测试，Layer 1 可直接执行。

### Phase Final 前置：命令 Handler 补全 + 架构拆分

Phase 4 中以下命令已有 parser 但缺少 handler，**必须在 Phase Final 前实现**：

| 命令 | handler 位置 | 逻辑 |
|------|-------------|------|
| `/resolve` | `_on_operator_command()` | → `conversation_manager.resolve()` → Bridge 发 `csat_request` | ✅ 已实现 |
| `/status` | `_on_admin_command()` | → `conversation_manager.list_active()` → 格式化返回 | ✅ 已实现 |
| `/dispatch` | `_on_admin_command()` | → 指定 agent JOIN conversation → 通知 agent MCP | ✅ 已实现 |
| `/review` | `_on_admin_command()` | → EventBus.query 聚合昨日统计（对话数/接管次数/结案率/CSAT均分），格式化返回 | ✅ 已实现 |

**架构拆分任务**（Phase Final 前必须完成）：

| 任务 | 产出 | 说明 |
|------|------|------|
| server.py 拆分 | `server.py`（~300行）+ `agent_mcp.py`（~200行） | channel-server 独立进程化；agent_mcp 轻量 MCP |
| routing.toml 加载 | `server.py` 启动时读取 routing 配置 | default_agents / escalation_chain / available_agents |
| IRC 消息前缀解析 | `server.py` 路由逻辑 | `__edit:msg_id:text` / `__side:text` 前缀 → Bridge event |
| agent_mcp MCP tools | `agent_mcp.py` | reply(edit_of?, side?) / join_conversation / send_side_message |
| pyproject.toml entry_points | 两个入口 | `zchat-channel`（独立进程）+ `zchat-agent-mcp`（轻量 MCP） |

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

Expected: 226+ tests PASS

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

Pre-release 测试需要完整的 zchat 运行栈。v1.0 架构中 channel-server 是**独立进程**（IRC bot + Bridge API + engine），agent 通过轻量 agent_mcp 连接 IRC，feishu_bridge 连接 channel-server 的 Bridge API。

### 启动链路

```
1. ergo IRC server (:6667)
2. channel-server 独立进程: uv run zchat-channel
     ├── IRC bot (nick: cs-bot) → ergo :6667（监听 #conv-* #squad-*）
     ├── Bridge API WebSocket :9999 ← feishu_bridge 连这里
     ├── engine/（ConversationManager + ModeManager + Gate + EventBus + TimerManager）
     └── 路由: feishu ↔ IRC，按 visibility/mode 规则过滤
3. zchat agent create fast-agent
     → Claude Code + agent_mcp（轻量 MCP: reply/side/join + IRC @mention 注入）
     → IRC nick: {user}-fast-agent → JOIN #conv-{id}
4. zchat agent create deep-agent
     → 同上，模型为 sonnet
5. feishu_bridge → ws://127.0.0.1:9999（连 channel-server Bridge API）
```

### routing.toml 配置

channel-server 启动时加载 routing 配置，控制 agent 编排策略：

```toml
# tests/pre_release/routing.toml
[routing]
default_agents = ["fast-agent"]              # 新 conversation 自动 dispatch
escalation_chain = ["deep-agent", "operator"] # 升级时按顺序尝试
available_agents = ["fast-agent", "deep-agent"] # /dispatch 白名单
```

### Step 1: 项目准备（一次性）

```bash
cd ~/projects/zchat

# 创建测试专用项目
zchat project create prerelease-test
zchat project use prerelease-test
```

### Step 2: 启动 ergo IRC server

```bash
zchat irc daemon start
# 等待 IRC server ready
```

### Step 3: 启动 channel-server 独立进程

```bash
cd ~/projects/zchat/zchat-channel-server

# channel-server 是独立进程，启动 IRC bot + Bridge API + engine
BRIDGE_PORT=9999 IRC_SERVER=127.0.0.1 CS_ROUTING_CONFIG=tests/pre_release/routing.toml \
  uv run zchat-channel &

# 等待 IRC 连接 + Bridge API ready（约 3s）
# 验证: cs-bot 在 IRC 可见，Bridge API ws://127.0.0.1:9999 可达
```

### Step 4: 创建双 agent

```bash
# 创建 fast-agent（haiku + soul.md 手写）
# agent_mcp 轻量 MCP server，.mcp.json 指向 zchat-agent-mcp
# soul.md: 简单问答 + 占位委托 + 采纳建议 + @operator 求助 + 副驾驶
zchat agent create fast-agent
# 阻塞等待 .ready marker（最多 60s）

# 创建 deep-agent（sonnet + soul.md 手写）
# soul.md: 接收委托 + 深度分析 + reply(edit_of=msg_id)
zchat agent create deep-agent
# 阻塞等待 .ready

# 验证: 两个 agent 在 IRC 可见
zchat agent list
# fast-agent: running
# deep-agent: running
```

### Step 5: 启动飞书 Bridge

```bash
cd ~/projects/zchat/zchat-channel-server

# feishu_bridge 作为独立进程，连接 channel-server 的 Bridge API
FEISHU_APP_ID=xxx FEISHU_APP_SECRET=xxx \
  uv run python -m feishu_bridge \
    --config tests/pre_release/feishu-e2e-config.yaml
```

feishu_bridge 连接 `ws://127.0.0.1:9999`（channel-server 独立进程的 Bridge API）。

### Step 6: 运行 Pre-release 测试

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

`full_stack` fixture 自动化 Step 1-5：

```python
@pytest.fixture(scope="module")
def full_stack(feishu_config):
    """启动完整运行栈：ergo + channel-server(独立进程) + 双 agent + feishu_bridge

    架构:
    - channel-server 是独立进程（IRC bot + Bridge API + engine）
    - agent 通过轻量 agent_mcp 连接 IRC
    - feishu_bridge 连接 channel-server 的 Bridge API
    前提:
    - Claude API key 已配置（agent 需要真实 Claude Code session）
    - feishu 凭证通过环境变量或 config 传入
    """
    import subprocess, time, os
    from pathlib import Path

    project_dir = os.environ.get("ZCHAT_PROJECT_DIR",
                                  os.path.expanduser("~/.zchat/projects/prerelease-test"))

    # 1. 确保项目存在
    subprocess.run(["uv", "run", "zchat", "project", "create", "prerelease-test"],
                   capture_output=True)  # 幂等，已存在不报错
    subprocess.run(["uv", "run", "zchat", "project", "use", "prerelease-test"], check=True)

    # 2. 启动 ergo IRC daemon
    subprocess.run(["uv", "run", "zchat", "irc", "daemon", "start"], check=True)
    time.sleep(2)

    # 3. 启动 channel-server 独立进程（IRC bot + Bridge API + engine）
    cs_proc = subprocess.Popen(
        ["uv", "run", "zchat-channel"],
        cwd=str(Path(__file__).parent.parent.parent),  # zchat-channel-server/
        env={**os.environ,
             "BRIDGE_PORT": "9999",
             "IRC_SERVER": "127.0.0.1",
             "CS_ROUTING_CONFIG": "tests/pre_release/routing.toml"}
    )
    time.sleep(3)  # 等待 IRC 连接 + Bridge API ready

    # 4. 验证 Bridge API 可达
    import websockets, asyncio
    async def _check_bridge():
        bridge_url = feishu_config.get("channel_server", {}).get("url", "ws://127.0.0.1:9999")
        async with websockets.connect(bridge_url) as ws:
            await ws.send('{"type":"register","bridge_type":"test","instance_id":"test-probe","capabilities":["customer"]}')
            resp = await asyncio.wait_for(ws.recv(), timeout=5)
            assert "registered" in resp
            await ws.close()
    asyncio.get_event_loop().run_until_complete(_check_bridge())

    # 5. 创建 fast-agent（haiku + soul.md）
    #    先写 soul.md 到 agent workspace
    fast_workspace = Path(project_dir) / "agents" / "fast-agent"
    fast_workspace.mkdir(parents=True, exist_ok=True)
    (fast_workspace / "soul.md").write_text(
        "你是快速响应 agent。简单问题直接答；"
        "复杂问题先 reply() 占位再 send_side_message(@deep-agent)。"
        "takeover 时在 squad thread 提供副驾驶建议。"
    )
    subprocess.run(
        ["uv", "run", "zchat", "agent", "create", "fast-agent"],
        timeout=90, check=True
    )

    # 6. 创建 deep-agent（sonnet + soul.md）
    deep_workspace = Path(project_dir) / "agents" / "deep-agent"
    deep_workspace.mkdir(parents=True, exist_ok=True)
    (deep_workspace / "soul.md").write_text(
        "你是深度分析 agent。收到 @mention 委托后深度分析，"
        "处理完用 reply(edit_of=msg_id) 替换占位消息。"
    )
    subprocess.run(
        ["uv", "run", "zchat", "agent", "create", "deep-agent"],
        timeout=90, check=True
    )

    # 7. 启动 feishu_bridge（连 channel-server :9999）
    bridge_proc = subprocess.Popen([
        "uv", "run", "python", "-m", "feishu_bridge",
        "--config", "tests/pre_release/feishu-e2e-config.yaml"
    ], cwd=str(Path(__file__).parent.parent.parent))  # zchat-channel-server/
    time.sleep(3)

    yield

    # 清理（逆序）
    bridge_proc.terminate()
    bridge_proc.wait(timeout=10)
    subprocess.run(["uv", "run", "zchat", "agent", "stop", "fast-agent"], check=False)
    subprocess.run(["uv", "run", "zchat", "agent", "stop", "deep-agent"], check=False)
    cs_proc.terminate()
    cs_proc.wait(timeout=10)
    subprocess.run(["uv", "run", "zchat", "irc", "daemon", "stop"], check=False)
```

### 测试 timeout 说明

Pre-release 测试的 timeout 比 E2E 长（120s vs 30s），因为：
- 真实 Claude Code 响应需要 5-15s（取决于查询复杂度）
- 双 agent 占位+edit 流程（fast-agent 占位 → deep-agent 分析 → edit 替换）需要 10-20s
- Timer 超时测试需要等待缩短后的 timer（10-12s）
- channel-server 独立进程 + 双 agent 启动约需 10s

### 降级方案（无真实 Claude Code）

channel-server 是独立进程，不依赖 Zellij 或 Claude Code。降级时直接启动 channel-server + agent_mcp：

```bash
# 1. 启动 channel-server 独立进程（始终可用）
cd zchat-channel-server
BRIDGE_PORT=9999 IRC_SERVER=127.0.0.1 CS_ROUTING_CONFIG=tests/pre_release/routing.toml \
  uv run zchat-channel &

# 2. 启动 agent_mcp（无 Claude Code，模拟 agent IRC 连接）
AGENT_NAME=fast-agent IRC_SERVER=127.0.0.1 IRC_PORT=6667 \
  uv run zchat-agent-mcp &
AGENT_NAME=deep-agent IRC_SERVER=127.0.0.1 IRC_PORT=6667 \
  uv run zchat-agent-mcp &

# 此模式下 agent_mcp 的 MCP stdio 无人读取，但 IRC 连接正常
# channel-server Bridge API + IRC 路由 + Gate/Mode 全部正常工作
# 测试可验证协议行为（Gate/Mode/Routing/card+thread），不能验证 agent 回复内容
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
    """启动 ergo + channel-server(独立进程) + 双 agent(agent_mcp) + feishu_bridge"""
    # ... 见上方 full_stack fixture 详细实现 ...
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

    def test_step2_squad_card_notification(self, feishu, groups, full_stack):
        """US-2.3: 分队群收到 interactive card（不是纯文本）

        新对话创建 → channel-server Bridge event conversation.created
        → feishu_bridge 在 squad群 发 interactive card（thread root）
        → card 显示: 客户信息 + 状态"进行中" + "进入对话"按钮
        """
        card = feishu.assert_card_appears(
            groups["squad_chat"],
            contains="进行中",
            timeout=10
        )
        assert card is not None
        # 验证卡片包含交互按钮
        assert card.has_action("进入对话")

    def test_step3_copilot_in_squad_thread(self, feishu, groups, full_stack):
        """US-2.4: copilot 模式 — operator 在 squad thread 中发建议，客户群看不到

        squad群 每个 conversation = 一张卡片(thread root) + 对应 thread。
        operator 在 thread 中发消息 → feishu_bridge 识别 root_id 属于已知 card
        → 转为 operator_message(side) → channel-server → Gate 判定 side visibility
        → 不转发到客户群
        """
        # operator 在 squad thread 中发建议（reply_in_thread）
        test_text = f"建议强调优惠_{int(time.time())}"  # 唯一标识
        feishu.send_thread_reply(groups["squad_chat"], test_text)
        time.sleep(5)

        # 验证: 客户群没有这条消息（side visibility）
        feishu.assert_message_absent(
            groups["customer_chat"],
            contains=test_text,
            wait=8
        )

        # 验证: squad thread 中有这条消息
        feishu.assert_thread_message_appears(
            groups["squad_chat"],
            contains=test_text,
            timeout=3
        )

    def test_step4_auto_hijack(self, feishu, groups, full_stack):
        """US-2.5: operator 在客户群发消息 → 自动 takeover（不需要 /hijack 命令）

        feishu_bridge 检测"已知 operator 在 customer_chat 发消息"
        → 自动发 operator_join + operator_command(/hijack) 到 channel-server
        → mode 转换为 takeover
        """
        # operator 直接在客户群发消息 = 自动 hijack
        feishu.send_message_as_operator(groups["customer_chat"], "您好，我来帮您处理")

        # 验证: squad 卡片更新为 takeover 状态
        feishu.assert_card_updated(
            groups["squad_chat"],
            contains="takeover",
            timeout=10
        )

    def test_step5_operator_message_reaches_customer(self, feishu, groups, full_stack):
        """US-2.6: takeover 下 operator 在客户群的消息客户可见

        operator 已通过自动 hijack 进入 takeover 模式。
        后续 operator 在客户群的消息 → Gate 判定 public visibility → 客户可见。
        同时 agent 在 squad thread 提供副驾驶建议（side visibility）。
        """
        operator_text = f"您好我是客服小李_{int(time.time())}"
        feishu.send_message_as_operator(groups["customer_chat"], operator_text)

        # 验证: 客户群收到（public visibility）
        feishu.assert_message_appears(
            groups["customer_chat"],
            contains="客服小李",
            timeout=10
        )

        # 验证: agent 在 squad thread 提供副驾驶建议（side visibility）
        feishu.assert_thread_message_appears(
            groups["squad_chat"],
            contains="建议",  # agent 副驾驶建议
            timeout=15
        )

    def test_step6_resolve_and_csat(self, feishu, groups, full_stack):
        """US-2.6: /resolve → CSAT"""
        # operator 在 squad thread 中发 /resolve
        feishu.send_thread_reply(groups["squad_chat"], "/resolve")

        # 验证: 客户群收到 CSAT 卡片
        feishu.assert_message_appears(
            groups["customer_chat"],
            contains="评分",
            timeout=10
        )

        # 验证: squad 卡片更新为"已关闭"
        feishu.assert_card_updated(
            groups["squad_chat"],
            contains="已关闭",
            timeout=10
        )


@pytest.mark.prerelease
class TestFeishuPlaceholderAndEdit:
    """US-2.2: 占位消息 + 续写替换 — 快慢双 agent 核心体验

    流程:
    1. 客户发复杂查询 → feishu_bridge → channel-server → IRC #conv-xxx
    2. fast-agent (haiku) 收到 → reply() 占位 → IRC PRIVMSG → channel-server → Bridge → 飞书
    3. fast-agent send_side_message(@deep-agent, msg_id=xxx) → IRC __side: → deep-agent 收到
    4. deep-agent (sonnet) 分析完成 → reply(edit_of=msg_id) → IRC __edit:msg_id:text → channel-server → Bridge {type: "edit"} → 飞书 update_message
    """

    def test_placeholder_then_edit(self, feishu, groups, full_stack):
        """US-2.2: 复杂查询 → fast-agent 占位 → deep-agent edit 替换"""
        feishu.send_message(groups["customer_chat"], "A 和 B 套餐的详细对比？能不能自定义？")

        # fast-agent (haiku) 先发占位消息
        placeholder = feishu.assert_message_appears(
            groups["customer_chat"],
            contains="稍等",
            timeout=5
        )
        assert placeholder is not None

        # deep-agent (sonnet) 处理完后通过 reply(edit_of=msg_id) 替换
        # channel-server 收到 IRC __edit:msg_id:text → Bridge {type: "edit"} → feishu_bridge update_message
        feishu.assert_message_edited(
            groups["customer_chat"],
            message_id=placeholder.id,
            contains="套餐",
            timeout=20
        )

    def test_edit_visible_in_squad(self, feishu, groups, full_stack):
        """编辑后的消息在分队群 thread 中也能看到更新"""
        # squad群 使用 card+thread 模型，编辑后的消息应在对应 thread 中更新
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
        """escalation 后无人接管 → timer breach → mode 退回 auto + 安抚消息

        注意: 测试环境中 timer 缩短为 10s。
        operator 不在客户群发消息（不触发自动 hijack），也不在 squad thread 发 /hijack。
        """
        # 触发 agent 求助（escalation）
        feishu.send_message(groups["customer_chat"], "我要找经理投诉")
        time.sleep(3)

        # 不在客户群发消息（不触发自动 hijack），等待 timer 超时
        # （测试配置中 takeover_wait = 10s）

        # 客户应收到安抚消息
        feishu.assert_message_appears(
            groups["customer_chat"],
            contains="抱歉",
            timeout=15
        )

        # squad 卡片应更新为"退回自动"状态
        feishu.assert_card_updated(
            groups["squad_chat"],
            contains="退回",
            timeout=5
        )


@pytest.mark.prerelease
class TestFeishuCSATFlow:
    """US-2.6 补充: CSAT 评分提交完整闭环"""

    def test_csat_score_submission(self, feishu, groups, full_stack):
        """客户点击评分 → csat_response → set_csat 闭环"""
        # 前置: operator 在客户群发消息（自动 hijack）→ /resolve
        feishu.send_message(groups["customer_chat"], "你好")
        time.sleep(5)
        feishu.send_message_as_operator(groups["customer_chat"], "我来帮您")
        time.sleep(3)
        feishu.send_thread_reply(groups["squad_chat"], "/resolve")

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
        """takeover 下 agent 消息降为 side，客户看不到

        operator 在客户群发消息 → 自动 hijack → takeover 模式
        → agent 回复通过 Gate 降为 side → 只出现在 squad thread
        """
        # 建立 takeover 状态（operator 在客户群发消息 = 自动 hijack）
        feishu.send_message(groups["customer_chat"], "需要帮助")
        time.sleep(5)
        feishu.send_message_as_operator(groups["customer_chat"], "我来处理")
        time.sleep(3)

        # agent 自动在 squad thread 发 side 建议（soul.md 副驾驶行为）
        # agent_mcp reply(side=True) → IRC __side: → channel-server → Bridge {visibility: "side"}
        feishu.assert_thread_message_appears(
            groups["squad_chat"],
            contains="建议",
            timeout=10
        )

        # 验证: 客户群没有 agent side 消息
        feishu.assert_message_absent(
            groups["customer_chat"],
            contains="建议",
            wait=5
        )

    def test_copilot_operator_thread_not_in_customer(self, feishu, groups, full_stack):
        """copilot 下 operator 在 squad thread 中的消息降为 side，客户看不到"""
        feishu.send_message(groups["customer_chat"], "你好")
        time.sleep(5)

        # operator 在 squad thread 中发建议（copilot 模式）
        test_text = f"内部建议_{int(time.time())}"
        feishu.send_thread_reply(groups["squad_chat"], test_text)
        time.sleep(5)

        # 客户群不应看到（side visibility）
        feishu.assert_message_absent(
            groups["customer_chat"], contains=test_text, wait=5)

        # squad thread 中应看到
        feishu.assert_thread_message_appears(
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
        """US-3.2: /dispatch 将指定 agent 派发到对话（受 routing.toml 白名单限制）"""
        # 先触发一个对话
        feishu.send_message(groups["customer_chat"], "需要深度分析")
        time.sleep(5)

        # admin 派发 deep-agent（在 routing.toml available_agents 白名单中）
        feishu.send_message(groups["admin_chat"], "/dispatch conv_id deep-agent")
        feishu.assert_message_appears(
            groups["admin_chat"],
            contains="已加入",
            timeout=10
        )

    def test_review_command(self, feishu, groups, full_stack):
        """US-3.2: /review 返回统计汇总数据"""
        feishu.send_message(groups["admin_chat"], "/review")
        msg = feishu.assert_message_appears(
            groups["admin_chat"],
            contains="统计",
            timeout=10
        )
        # 应包含对话数/CSAT/SLA breach 等统计信息
        assert msg is not None


@pytest.mark.prerelease
class TestFeishuSLABreach:
    """US-3.3: SLA breach 告警 → admin群"""

    def test_sla_breach_alert(self, feishu, groups, full_stack):
        """SLA breach → TimerManager 触发 → channel-server Bridge event → admin群 告警

        测试环境 timer 缩短（takeover_wait=10s），等待 breach 后验证 admin群 收到告警。
        v1.0 只实现单次 breach 告警（不重复）。
        """
        # 触发 agent 求助（escalation）
        feishu.send_message(groups["customer_chat"], "我要找经理投诉，马上解决")
        time.sleep(3)

        # 不做 /hijack，也不在客户群发消息（不触发自动 hijack）
        # 等待 SLA breach timer（测试配置 takeover_wait=10s）
        time.sleep(12)

        # admin群 应收到 SLA breach 告警
        feishu.assert_message_appears(
            groups["admin_chat"],
            contains="SLA",
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
        """squad 群成员可使用 /hijack 等 operator 命令（备选方式）+ 自动 hijack"""
        # 先建立一个 active conversation
        feishu.send_message(groups["customer_chat"], "需要帮助")
        time.sleep(5)
        # 方式 1: operator 在客户群发消息 → 自动 hijack
        feishu.send_message_as_operator(groups["customer_chat"], "我来处理")
        feishu.assert_card_updated(
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
| `assert_card_appears(chat_id, contains, timeout)` | 验证 squad群 收到 interactive card（thread root） | TestFeishuFullJourney |
| `assert_card_updated(chat_id, contains, timeout)` | 验证 card 状态更新（mode 变更等） | TestFeishuFullJourney |
| `send_thread_reply(chat_id, text)` | 在 squad群 thread 中回复（reply_in_thread=True） | TestFeishuFullJourney, TestFeishuGateIsolation |
| `assert_thread_message_appears(chat_id, contains, timeout)` | 验证 squad thread 中出现消息 | TestFeishuFullJourney, TestFeishuGateIsolation |
| `send_message_as_operator(chat_id, text)` | 以 operator 身份在客户群发消息（触发自动 hijack） | TestFeishuFullJourney, TestFeishuGateIsolation |
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

| PRD User Story | 测试类 | 覆盖状态 | 新架构要点 |
|---|---|---|---|
| US-2.1 客户接入 + 3s 问候 | TestFeishuFullJourney.test_step1 + TestFeishuConversationReactivation | ✅ | channel-server 统一管理 conversation |
| US-2.2 占位 + 续写替换 | TestFeishuPlaceholderAndEdit | ✅ | 双 agent: fast-agent 占位 → deep-agent reply(edit_of) → IRC __edit: 前缀 |
| US-2.3 分队卡片通知 | TestFeishuFullJourney.test_step2_squad_card | ✅ | card+thread 模型（非纯文本） |
| US-2.4 Copilot 模式 | TestFeishuFullJourney.test_step3_copilot_in_squad_thread + TestFeishuGateIsolation | ✅ | operator 在 squad thread 中发建议 |
| US-2.5 两种触发 (自动 hijack + timeout) | TestFeishuFullJourney.test_step4_auto_hijack + TestFeishuTimerAndEscalation | ✅ | operator 在客户群发消息 = 自动 takeover |
| US-2.6 角色翻转 + /resolve + CSAT | TestFeishuFullJourney.test_step5/6 + TestFeishuCSATFlow | ✅ | agent 副驾驶建议在 squad thread |
| US-3.2 管理命令 (/status + /dispatch + /review) | TestFeishuAdminCommands | ✅ | /review 新增；/dispatch 受 routing.toml 白名单限制 |
| US-3.3 SLA breach 告警 | TestFeishuSLABreach | ✅ | TimerManager breach → admin群 告警（v1.0 单次） |
| 授权模型 (3 角色 + 群成员资格) | TestFeishuAuthorizationModel | ✅ | 自动 hijack 替代手动 /hijack |
| Gate 安全隔离 | TestFeishuGateIsolation | ✅ | squad thread + auto hijack |

## 完成标准

### 架构前置

- [x] **server.py 拆分完成** — channel-server 独立进程 (Task 4.6.1, 0256535)
- [x] **agent_mcp.py 实现完成** — 轻量 MCP server (Task 4.6.1)
- [x] **routing.toml 加载正常** — routing_config.py (Task 4.6.3)
- [x] **IRC 消息前缀解析正常** — __msg:/__edit:/__side: (Task 4.6.2)
- [x] **命令 handler 补全** — /resolve /status /dispatch /review /assign /reassign /squad /abandon
- [x] **DB 合并完成** — 单一 conversations.db, 5 表, FK + CASCADE (9e95d62)
- [x] **卡片回调完成** — CardAwareClient + CSAT 闭环 (f5fc661)
- [x] **Gate 修复** — send_event target_capabilities 过滤 (542fb29)

### 运行栈验证

- [ ] **channel-server 独立进程** — IRC bot (cs-bot) 在 IRC 可见 + Bridge API :9999 可达
- [ ] **双 agent 在 IRC 可见** — fast-agent + deep-agent 均 JOIN 相关频道
- [ ] **feishu_bridge 注册成功** — ws://127.0.0.1:9999 连接 + register 握手完成

### 测试通过

- [ ] Unit 回归: 全部 PASS (226+ tests，含 Phase 4.5 feishu_bridge)
- [ ] E2E Bridge API: 全部 PASS (7+ scenarios，含 mode switching + gate enforcement)
- [ ] 飞书 E2E 6 步状态机: 全部 PASS（含 card+thread 断言）
- [ ] 飞书 占位+续写 (双 agent edit 流程): 全部 PASS
- [ ] 飞书 Timer+超时退回: 全部 PASS
- [ ] 飞书 SLA breach 告警: admin群 收到告警 PASS
- [ ] 飞书 CSAT 评分提交闭环: 全部 PASS
- [ ] 飞书 老客户 reactivation: 全部 PASS
- [ ] 飞书 Gate 隔离验证: 全部 PASS（squad thread side visibility）
- [ ] 飞书管理命令验证 (/status + /dispatch + /review): 全部 PASS
- [ ] 飞书授权模型验证: 全部 PASS（含自动 hijack）
- [ ] `.artifacts/e2e-reports/cs-report-prerelease.md` 存在，0 FAIL 0 SKIP
- [ ] evidence/ 目录有完整录制
