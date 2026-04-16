# Phase Final: Pre-release 测试执行

> 复制以下 prompt 到新 session 中执行。
> 两个 Task（基础设施开发 + 测试执行），走 dev-loop 闭环。

---

## Prompt

```
你被启动在 zchat 项目根目录 (`~/projects/zchat/`)。
zchat 在 `feat/channel-server-v1` 分支。
channel-server submodule 在 `zchat-channel-server/`，`refactor/channel-server` 分支。

## 目标

执行 Phase Final — pre-release 验收测试。分两个 Task：
1. Task F.1: 开发测试基础设施（FeishuTestClient 扩展 + full_stack fixture + test_feishu_e2e.py）
2. Task F.2: 三层测试执行 + 录制证据

完整测试计划在 `docs/discuss/plan/07-phase-final-testing.md`。
缺失项评估在 `zchat-channel-server/.artifacts/eval-docs/cs-eval-prerelease-infra.md`。
阻塞记录在 `docs/discuss/note/prerelease-blockers.md`。

## 当前状态

- Phase 4.6 全部完成 + gate fix + card action + db consolidation
- MCP server 已切换到 zchat-agent-mcp（start.sh + .env.example + defaults.toml）
- 247 tests passed, 49 artifacts, 12 个 Task 证据链完整
- 服务入口点全部验证通过:
  - `uv run zchat-channel` — 独立进程（IRC bot + Bridge API :9999 + engine）
  - `uv run zchat-agent-mcp` — 轻量 MCP（reply/join/side + IRC @mention）
  - `python -m feishu_bridge --config path.yaml` — 飞书桥接
- 飞书平台: app 已开、3 群已建、权限已开、card.action.trigger 已订阅
- 项目: ~/.zchat/projects/prerelease-test/ 已创建
  - config.toml: mcp_server_cmd = ["uv", "run", "--project", ".../zchat-channel-server", "zchat-agent-mcp"]
  - zellij session: zchat-prerelease-test
- 配置文件:
  - tests/pre_release/routing.toml ✅
  - tests/pre_release/feishu-e2e-config.yaml ✅（chat_id 已填）

## 工作环境

```bash
cd zchat-channel-server
git checkout refactor/channel-server

# 验证基线
uv run pytest tests/unit/ feishu_bridge/tests/ -q
# Expected: 226 passed

# 验证端口空闲
ss -tlnp | grep -E "6667|9999"
# Expected: 无输出
```

## Task F.1: 测试基础设施开发

Artifact ID: `cs-*-prerelease-infra`
分支: 在 refactor/channel-server 上直接开发

### Step 1: eval-doc

已存在: `.artifacts/eval-docs/cs-eval-prerelease-infra.md` (status: open)
读取它了解完整的缺失项。

### Step 2: test-plan

/dev-loop-skills:skill-2-test-plan-generator
# 输入: cs-eval-prerelease-infra
# 产出: .artifacts/test-plans/cs-plan-prerelease-infra.md

### Step 3-4: 实现

需要开发 3 个部分:

#### 3a. FeishuTestClient 扩展 (feishu_bridge/test_client.py)

当前有 7 个方法。新增 7 个:

| 方法 | 实现要点 |
|------|---------|
| `assert_message_edited(chat_id, message_id, contains, timeout)` | 轮询 get_message，检测 content 变化 |
| `assert_card_appears(chat_id, contains, timeout)` | list_messages 过滤 msg_type="interactive" |
| `assert_card_updated(chat_id, contains, timeout)` | get_message 检测 card content 变化 |
| `send_thread_reply(chat_id, root_msg_id, text)` | im.v1.message.reply (需要知道 root_msg_id) |
| `assert_thread_message_appears(chat_id, root_msg_id, contains, timeout)` | list_messages + parent_id 过滤 |
| `send_message_as_operator(chat_id, text)` | 同 send_message（bot 就是 operator） |
| `click_card_action(chat_id, action_value)` | 直接调 bridge._on_card_action(payload) 模拟 |

**lark_oapi API 参考**:
- reply: im.v1.message.reply (需 ReplyMessageRequest)
- thread: reply 时设置 reply_in_thread=True 参数（如 SDK 支持），否则手动构造

**click_card_action 方案**: 构造 card action payload 直接传给 FeishuBridge._on_card_action()，
不走飞书平台。如果不可行则 pytest.skip("card action 需手动验证")。

#### 3b. full_stack fixture (tests/pre_release/conftest.py)

07-phase-final-testing.md 中有完整的 fixture 代码（Lines 234-327）。
核心启动链路（已验证的正确方式）:

```python
# 1. zchat project use prerelease-test
subprocess.run(["uv", "run", "zchat", "project", "use", "prerelease-test"], check=True)

# 2. 启动 ergo
subprocess.run(["uv", "run", "zchat", "irc", "daemon", "start"], check=True)
time.sleep(2)

# 3. 启动 channel-server 独立进程
cs_proc = subprocess.Popen(
    ["uv", "run", "--project", "/home/yaosh/projects/zchat/zchat-channel-server", "zchat-channel"],
    env={**os.environ,
         "BRIDGE_PORT": "9999",
         "IRC_SERVER": "127.0.0.1",
         "CS_ROUTING_CONFIG": "tests/pre_release/routing.toml"}
)
time.sleep(3)

# 4. 创建 agent（在 zellij tab 中启动 Claude Code + agent_mcp）
# agent 的 MCP server = zchat-agent-mcp（config.toml 已配置 uv run 方式）
subprocess.run(["uv", "run", "zchat", "agent", "create", "fast-agent"], timeout=90, check=True)
subprocess.run(["uv", "run", "zchat", "agent", "create", "deep-agent"], timeout=90, check=True)

# 5. 启动 feishu_bridge
bridge_proc = subprocess.Popen([
    "uv", "run", "--project", "/home/yaosh/projects/zchat/zchat-channel-server",
    "python", "-m", "feishu_bridge", "--config", "tests/pre_release/feishu-e2e-config.yaml"
])
time.sleep(3)
```

**注意**: 
- zchat CLI 命令用 `uv run zchat` 而非裸 `zchat`（确保用项目 venv）
- channel-server 和 feishu_bridge 用 `uv run --project` 指向 submodule
- agent 启动后等 .ready marker（agent_manager 的 SessionStart hook 写入）

#### 3c. test_feishu_e2e.py (tests/pre_release/test_feishu_e2e.py)

07-phase-final-testing.md Lines 397-872 有完整的测试代码，包含:
- TestFeishuFullJourney (6 tests) — 6 步状态机
- TestFeishuPlaceholderAndEdit (2 tests) — 占位 + edit
- TestFeishuTimerAndEscalation (2 tests) — escalation + timeout
- TestFeishuCSATFlow (1 test) — CSAT 评分
- TestFeishuConversationReactivation (1 test) — 老客户
- TestFeishuGateIsolation (2 tests) — side 不到客户
- TestFeishuAdminCommands (3 tests) — /status /dispatch /review
- TestFeishuSLABreach (1 test) — SLA breach alert
- TestFeishuAuthorizationModel (5 tests) — 角色权限

落地时注意:
- 从 07-phase-final 复制代码，但需要适配实际的 FeishuTestClient 方法签名
- 需要 root_msg_id 参数（send_thread_reply / assert_thread_message_appears）
- full_stack fixture 中记录 conversation 的 card_msg_id 用于 thread 操作

注册: /dev-loop-skills:skill-6-artifact-registry register --type code-diff --id cs-diff-prerelease-infra

### Step 5: test-run

```bash
# 先验证 FeishuTestClient 新方法的 unit tests
uv run pytest feishu_bridge/tests/test_client_extended.py -v

# 验证 test_feishu_e2e.py 可 collect（不实际执行飞书操作）
uv run pytest tests/pre_release/test_feishu_e2e.py --collect-only

# 回归
uv run pytest tests/unit/ feishu_bridge/tests/ -q
```

/dev-loop-skills:skill-4-test-runner

### Step 6: artifact registry

/dev-loop-skills:skill-6-artifact-registry register --type e2e-report --id cs-report-prerelease-infra

闭环标志: cs-eval/plan/diff/report-prerelease-infra 全部 confirmed。

---

## Task F.2: 三层测试执行

**依赖**: Task F.1 完成 + 飞书凭证环境变量设置

### Layer 1: Unit 回归

```bash
cd zchat-channel-server

# 录制
asciinema rec tests/pre_release/evidence/unit-regression.cast -c \
  "uv run pytest tests/unit/ feishu_bridge/tests/ -v 2>&1 | tee tests/pre_release/evidence/unit-regression.log"
```

Expected: 226+ passed, 0 failed

### Layer 2: E2E Bridge API

```bash
asciinema rec tests/pre_release/evidence/e2e-bridge-api.cast -c \
  "uv run pytest tests/e2e/ -v -m e2e --timeout=30 2>&1 | tee tests/pre_release/evidence/e2e-bridge-api.log"
```

Expected: 全部 PASS

### Layer 3: 飞书 E2E

**前置**: 设置飞书凭证
```bash
export FEISHU_APP_ID="从 .feishu-credentials.json 读取"
export FEISHU_APP_SECRET="从 .feishu-credentials.json 读取"
```

**启动完整栈**（如果不用 full_stack fixture 自动启动）:
```bash
# Terminal 1: ergo
uv run zchat irc daemon start

# Terminal 2: channel-server
cd zchat-channel-server
BRIDGE_PORT=9999 IRC_SERVER=127.0.0.1 CS_ROUTING_CONFIG=tests/pre_release/routing.toml \
  uv run zchat-channel

# Terminal 3: agents（通过 zchat CLI 在 zellij tab 中启动）
uv run zchat project use prerelease-test
uv run zchat agent create fast-agent
uv run zchat agent create deep-agent

# Terminal 4: feishu_bridge
cd zchat-channel-server
uv run python -m feishu_bridge --config tests/pre_release/feishu-e2e-config.yaml
```

**执行测试**:
```bash
asciinema rec tests/pre_release/evidence/feishu-e2e.cast -c \
  "FEISHU_APP_ID=xxx FEISHU_APP_SECRET=xxx \
   uv run pytest tests/pre_release/test_feishu_e2e.py -v -m prerelease --timeout=120 \
   2>&1 | tee tests/pre_release/evidence/feishu-e2e.log"
```

### 证据目录

```bash
mkdir -p tests/pre_release/evidence/screenshots
```

```
tests/pre_release/evidence/
├── unit-regression.cast + .log
├── e2e-bridge-api.cast + .log
├── feishu-e2e.cast + .log
└── screenshots/
    ├── 01-customer-onboard.png
    ├── 02-squad-card.png
    ├── 03-placeholder-edit.png
    ├── 04-auto-hijack.png
    ├── 05-resolve-csat.png
    └── ...
```

### Artifact 注册

```bash
/dev-loop-skills:skill-6-artifact-registry register --type e2e-report --id cs-report-prerelease
```

## 完成标准

- [ ] cs-report-prerelease-infra 存在 (Task F.1)
- [ ] Layer 1: Unit 全 PASS, evidence/unit-regression.log 存在
- [ ] Layer 2: E2E 全 PASS, evidence/e2e-bridge-api.log 存在
- [ ] Layer 3: 飞书 E2E 全 PASS (或已知 skip 有截图替代), evidence/feishu-e2e.log 存在
- [ ] cs-report-prerelease 存在, 0 FAIL 0 unexpected SKIP
- [ ] evidence/ 目录有完整录制

## 提交

```bash
# Task F.1 完成后
cd zchat-channel-server
git add feishu_bridge/test_client.py feishu_bridge/tests/test_client_extended.py \
        tests/pre_release/conftest.py tests/pre_release/test_feishu_e2e.py \
        .artifacts/
git commit -m "feat: Phase Final Task F.1 — pre-release 测试基础设施"

# Task F.2 完成后
git add tests/pre_release/evidence/ .artifacts/
git commit -m "feat: Phase Final Task F.2 — 三层验收测试通过"
```
```
