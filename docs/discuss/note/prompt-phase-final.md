# Phase Final: Pre-release 验收测试

> 复制以下 prompt 到新 session 中执行。

---

## Prompt

```
你被启动在 zchat 项目根目录 (`~/projects/zchat/`)。
zchat 在 `feat/channel-server-v1` 分支。
channel-server submodule 在 `zchat-channel-server/`，`refactor/channel-server` 分支。

## 目标

执行 Phase Final — 完整 pre-release 验收测试。
要求：所有测试必须执行（不允许 skip），报错当场修复，生成 PDF 报告（含截图）。
通过 dev-loop skill 保存完整证据链。

计划在 `docs/discuss/plan/07-phase-final-testing.md`。
缺失项 eval-doc: `zchat-channel-server/.artifacts/eval-docs/cs-eval-prerelease-infra.md`。
Artifact 空间: `zchat-channel-server/.artifacts/`（75 artifacts，registry.json）。

## 当前状态

- 代码完成: Phase 4.6 全部 + gate fix + card action + db consolidation + 架构审查修复
- MCP: agent 已切换到 zchat-agent-mcp（start.sh + defaults.toml）
- 基线: 226 unit + 23 E2E passed, 0 failed
- 飞书: app 已开、3 群 (cs-customer/cs-squad/cs-admin)、card.action.trigger 已订阅
- 项目: ~/.zchat/projects/prerelease-test/ 已创建
- 配置: tests/pre_release/routing.toml + feishu-e2e-config.yaml 已填 chat_id
- 工具: ergo 2.18.0 + zellij 0.44.1 + asciinema + claude CLI

## 工作环境

```bash
cd ~/projects/zchat/zchat-channel-server
git checkout refactor/channel-server

# 验证基线
uv run pytest tests/unit/ feishu_bridge/tests/ -q
# Expected: 226 passed

# 验证端口空闲
ss -tlnp | grep -E "6667|9999"
# Expected: 无输出

# 验证 zchat 项目
uv run zchat project use prerelease-test
```

## 关键约束（WSL2 环境）

- 所有网络地址使用 `127.0.0.1`（不用 localhost，WSL2 中 localhost → ::1 IPv6）
- zchat CLI 命令用 `uv run zchat ...`（确保用项目 venv）
- channel-server 启动: `uv run zchat-channel`（submodule venv 内）
- feishu_bridge 启动: `uv run python -m feishu_bridge --config path.yaml`
- 环境变量: CS_ROUTING_CONFIG（不是 ROUTING_CONFIG）

## 执行方式: 两个 Task，全部走 dev-loop 闭环

---

### Task F.1: 测试基础设施开发

Artifact ID: `cs-*-prerelease-infra`

读取 eval-doc `cs-eval-prerelease-infra` 了解完整缺失项。

#### Step 1: eval-doc（已存在）
`.artifacts/eval-docs/cs-eval-prerelease-infra.md` (status: open)

#### Step 2: test-plan
/dev-loop-skills:skill-2-test-plan-generator
# 产出: .artifacts/test-plans/cs-plan-prerelease-infra.md

#### Step 3-4: 实现 3 个部分

**3a. FeishuTestClient 扩展** (feishu_bridge/test_client.py)

新增 7 个方法:
- assert_message_edited(chat_id, message_id, contains, timeout) — 轮询 get_message 检测 content 变化
- assert_card_appears(chat_id, contains, timeout) — list_messages 过滤 msg_type="interactive"
- assert_card_updated(chat_id, contains, timeout) — get_message 检测 card content 变化
- send_thread_reply(chat_id, root_msg_id, text) — im.v1.message.reply
- assert_thread_message_appears(chat_id, root_msg_id, contains, timeout) — list + parent_id 过滤
- send_message_as_operator(chat_id, text) — 同 send_message（bot = operator）
- click_card_action(chat_id, action_value) — 构造 payload 调 bridge._on_card_action() 模拟

为每个新方法写 unit test: feishu_bridge/tests/test_client_extended.py

**3b. full_stack fixture** (tests/pre_release/conftest.py)

启动链路（所有地址用 127.0.0.1）:
1. uv run zchat project use prerelease-test
2. uv run zchat irc daemon start → 等 2s
3. uv run zchat-channel (BRIDGE_PORT=9999 IRC_SERVER=127.0.0.1 CS_ROUTING_CONFIG=tests/pre_release/routing.toml)
4. 验证 Bridge API ws://127.0.0.1:9999 可达（retry 5 次）
5. uv run zchat agent create fast-agent → 等 .ready marker
6. uv run zchat agent create deep-agent → 等 .ready
7. uv run python -m feishu_bridge --config tests/pre_release/feishu-e2e-config.yaml
清理逆序 teardown。scope="module"。

**3c. test_feishu_e2e.py** (tests/pre_release/test_feishu_e2e.py)

从 07-phase-final-testing.md Lines 397-872 落地，适配实际 API:
- TestFeishuFullJourney (6 tests) — 6 步状态机
- TestFeishuPlaceholderAndEdit (2 tests) — 占位 + edit
- TestFeishuTimerAndEscalation (2 tests) — escalation + timeout
- TestFeishuCSATFlow (1 test) — CSAT 评分
- TestFeishuConversationReactivation (1 test) — 老客户
- TestFeishuGateIsolation (2 tests) — side 不到客户
- TestFeishuAdminCommands (3 tests) — /status /dispatch /review
- TestFeishuSLABreach (1 test) — SLA breach alert
- TestFeishuAuthorizationModel (5 tests) — 角色权限

注册: /dev-loop-skills:skill-6-artifact-registry register --type code-diff --id cs-diff-prerelease-infra

#### Step 5: test-run
```bash
uv run pytest feishu_bridge/tests/test_client_extended.py -v  # 新方法 unit
uv run pytest tests/pre_release/test_feishu_e2e.py --collect-only  # 可 collect
uv run pytest tests/unit/ feishu_bridge/tests/ -q  # 回归
```
/dev-loop-skills:skill-4-test-runner

#### Step 6: artifact registry
/dev-loop-skills:skill-6-artifact-registry register --type e2e-report --id cs-report-prerelease-infra

闭环标志: cs-eval/plan/diff/report-prerelease-infra 全部 confirmed。

提交:
```bash
git add feishu_bridge/test_client.py feishu_bridge/tests/test_client_extended.py \
        tests/pre_release/ .artifacts/
git commit -m "feat: Phase Final Task F.1 — pre-release 测试基础设施"
```

---

### Task F.2: 三层验收测试 + ralph-loop 执行

**核心规则**: 不允许 skip。报错当场修复。ralph-loop 直到所有测试 PASS。

#### 准备: 飞书凭证
```bash
# 从 .feishu-credentials.json 读取
export FEISHU_APP_ID="$(jq -r .app_id ~/projects/zchat/.feishu-credentials.json)"
export FEISHU_APP_SECRET="$(jq -r .app_secret ~/projects/zchat/.feishu-credentials.json)"
```

#### Layer 1: Unit 回归

```bash
mkdir -p tests/pre_release/evidence
asciinema rec tests/pre_release/evidence/unit-regression.cast -c \
  "uv run pytest tests/unit/ feishu_bridge/tests/ -v 2>&1 | tee tests/pre_release/evidence/unit-regression.log"
```

**Expected**: 226+ passed, 0 failed, 0 skip。
**如果失败**: 当场修复 → 重跑 → 直到全绿。记录修复内容。

#### Layer 2: E2E Bridge API

```bash
asciinema rec tests/pre_release/evidence/e2e-bridge-api.cast -c \
  "uv run pytest tests/e2e/ -v --timeout=30 2>&1 | tee tests/pre_release/evidence/e2e-bridge-api.log"
```

**Expected**: 23+ passed, 0 failed, 0 skip, 0 error。
**WSL2 flaky 处理**: 如果有 ConnectionRefused error，重跑一次。第二次仍失败则修复。

#### Layer 3: 飞书 E2E（ralph-loop 驱动）

```bash
asciinema rec tests/pre_release/evidence/feishu-e2e.cast -c \
  "FEISHU_APP_ID=$FEISHU_APP_ID FEISHU_APP_SECRET=$FEISHU_APP_SECRET \
   uv run pytest tests/pre_release/test_feishu_e2e.py -v --timeout=120 \
   2>&1 | tee tests/pre_release/evidence/feishu-e2e.log"
```

**Ralph-loop 执行**: max-iteration 10
1. 运行所有 17 个 test case
2. 如果任何测试 FAIL 或 ERROR:
   - 读取 traceback，分析根因
   - 修复代码或测试
   - 重跑失败的测试 + 回归
3. 如果测试 SKIP:
   - 分析 skip 原因
   - 实现缺失功能或调整测试使其可执行
   - 不允许保留 skip（除非是硬件限制如"需要真人点卡片"，此时用截图替代）
4. 重复直到 17/17 PASS（或有明确文档说明的替代验证）
5. 每次修复后重新录制 asciinema

#### 截图证据

每个关键步骤在飞书 Web 端截图:
```bash
mkdir -p tests/pre_release/evidence/screenshots
```
- 01-customer-onboard.png — 客户进群 → agent 回复
- 02-squad-card.png — squad 群 interactive card
- 03-placeholder-edit.png — 占位 → edit 替换前后
- 04-auto-hijack.png — operator 发消息 → 卡片变 takeover
- 05-side-not-in-customer.png — 客户群无 side 消息
- 06-resolve-csat.png — /resolve → CSAT 卡片
- 07-admin-status.png — /status 返回
- 08-admin-review.png — /review 统计
- 09-sla-breach.png — SLA breach 告警

截图方式: 在测试运行的同时，打开飞书 Web 端，用浏览器截图工具（或 zellij dump-screen）。

#### PDF 报告生成

所有测试通过后，生成 PDF 报告:
```bash
# 安装工具（如果没有）
uv tool install md-to-pdf 2>/dev/null || pip install markdown-pdf 2>/dev/null

# 生成报告 markdown
cat > tests/pre_release/evidence/report.md << 'REPORT_EOF'
# channel-server v1.0 Pre-release 验收报告

## 测试概览
- 日期: $(date +%Y-%m-%d)
- 分支: refactor/channel-server
- 环境: WSL2 + ergo 2.18.0 + zellij 0.44.1

## Layer 1: Unit 回归
<!-- 嵌入 unit-regression.log 摘要 -->

## Layer 2: E2E Bridge API
<!-- 嵌入 e2e-bridge-api.log 摘要 -->

## Layer 3: 飞书 E2E
<!-- 嵌入 feishu-e2e.log 摘要 + 每个测试结果 -->

## 截图证据
<!-- 嵌入 screenshots/*.png -->

## 修复记录
<!-- 如果 ralph-loop 中有修复，记录每次修复 -->
REPORT_EOF

# 转 PDF（选择可用的工具）
```

在报告中嵌入:
1. 三层测试的 PASS/FAIL 汇总
2. 每个测试类的结果
3. 截图（作为证据）
4. ralph-loop 中的修复记录（如有）

#### Artifact 注册

```bash
/dev-loop-skills:skill-6-artifact-registry register --type e2e-report --id cs-report-prerelease
```

#### 提交

```bash
git add tests/pre_release/evidence/ .artifacts/
git commit -m "feat: Phase Final Task F.2 — 三层验收测试通过 + PDF 报告"
```

---

## 完成标准

### dev-loop 证据链
- [ ] cs-eval-prerelease-infra → confirmed
- [ ] cs-plan-prerelease-infra → executed
- [ ] cs-diff-prerelease-infra → confirmed
- [ ] cs-report-prerelease-infra → confirmed
- [ ] cs-report-prerelease → confirmed (最终测试报告)

### 测试结果
- [ ] Layer 1: 226+ unit PASS, 0 FAIL, 0 SKIP
- [ ] Layer 2: 23+ E2E PASS, 0 FAIL, 0 ERROR
- [ ] Layer 3: 17 飞书 E2E PASS, 0 FAIL, 0 SKIP
- [ ] 所有测试有 asciinema 录制 (.cast 文件)
- [ ] 关键步骤有飞书截图 (.png 文件)
- [ ] PDF 报告生成并包含截图

### 文件结构
```
tests/pre_release/
├── conftest.py                    # full_stack fixture
├── test_feishu_e2e.py             # 17 test cases
├── routing.toml                   # 路由配置
├── feishu-e2e-config.yaml         # 飞书配置
└── evidence/
    ├── unit-regression.cast + .log
    ├── e2e-bridge-api.cast + .log
    ├── feishu-e2e.cast + .log
    ├── report.md + report.pdf
    └── screenshots/
        ├── 01-customer-onboard.png
        ├── ...
        └── 09-sla-breach.png
```
```
