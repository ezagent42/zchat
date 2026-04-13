# 01-待提交修改整理

> zchat 当前所有未提交修改的分类和处理计划。

## 修改清单

### Commit 1: fix: ergo TLS config removal (bug fix)

**文件**：`zchat/cli/irc_manager.py`

**内容**：修复 `daemon_start()` 中 TLS 配置删除不彻底的问题。ergo `defaultconfig` 包含 `:6697` TLS 监听和 `fullchain.pem`/`privkey.pem` 引用，原正则只删除了 `:6697` 行到 `min-tls-version`，但没有删除 `tls:` cert/key 配置块，导致 ergo 启动失败。

**修复**：用两个正则分别删除 `:6697` 监听行和 `tls:` cert/key 配置块。

**影响**：E2E 测试从 9 ERROR → 0 ERROR。

**优先级**：P0（阻断 E2E 测试执行）

### Commit 2: feat: WSL2 proxy auto-rewrite in claude.sh

**文件**：`claude.sh`、`claude.local.env.example`

**内容**：
- `claude.sh` 增加 WSL2 检测：自动将 `127.0.0.1` 代理地址替换为 Windows 宿主 IP（通过 `ip route show default` 获取）
- `claude.local.env.example` 增加注释说明代理配置方式

**影响**：WSL2 环境下 Claude Code 可以正常通过 Windows 代理访问 API。

**优先级**：P1（WSL2 开发体验）

### Commit 3: chore: update ezagent42-marketplace submodule

**文件**：`ezagent42-marketplace`（submodule pointer）

**内容**：marketplace.json 新增 `dev-loop-skills` plugin 注册。

**优先级**：P2

### Commit 4: docs: add dev-loop skill development docs + E2E test plan

**文件**（新增）：
- `docs/discuss/skill-dev/01-development-pipeline.md`
- `docs/discuss/skill-dev/02-skill-definitions.md`
- `docs/discuss/skill-dev/03-skill-dev-standards.md`
- `docs/discuss/skill-dev/04-user-journeys.md`
- `docs/discuss/skill-dev/05-e2e-test-plan.md`
- `docs/discuss/skill-dev/06-colleague-quickstart.md`
- `docs/discuss/skill-dev/verify-skill-output.sh`
- `docs/discuss/introduce/` 系列（8 个文件 + README）
- `docs/discuss/qa/001-2026-04-03-architecture-qa.md`
- `docs/discuss/e2e-log/2026-04-08-quickstart-test.md`
- `docs/discuss/zellij-zchat/` 系列

**优先级**：P2

### Commit 5: feat: E2E test for agent DM + .artifacts test data

**文件**（新增）：
- `tests/e2e/test_agent_dm.py` — agent 间 DM 私聊 E2E 测试
- `.artifacts/` — E2E 测试产出的 artifact 数据

**处理**：`test_agent_dm.py` 保留（有价值的 E2E 代码）。`.artifacts/` 中的测试数据可以保留（作为 bootstrap 基线和 E2E 循环产物）。

**优先级**：P2

### Commit 6: fix: chunk_message byte-based splitting for CJK (channel-server submodule)

**文件**：`zchat-channel-server/message.py`、`zchat-channel-server/tests/test_channel_server.py`

**内容**：
- `chunk_message()` 从字符计数改为 UTF-8 字节计数（IRC RFC 2812 限制 512 字节/消息）
- `MAX_MESSAGE_LENGTH = 4000` → `MAX_MESSAGE_BYTES = 390`（预留 ~120 字节 IRC header）
- 新增 `_sanitize_for_irc()` 替换换行符为空格
- 新增测试覆盖 CJK 字符的字节长度分割

**影响**：修复中文/日文消息在 IRC 中被截断的问题。

**优先级**：P1（多语言客服场景必需）

**注意**：这是 submodule 内的修改，需要先在 `zchat-channel-server/` 中 commit，再在主仓库更新 submodule 指针。

```bash
cd zchat-channel-server
git add message.py tests/test_channel_server.py
git commit -m "fix: chunk_message uses byte length for IRC RFC 2812 compliance"
cd ..
git add zchat-channel-server
git commit -m "chore: update zchat-channel-server (byte-based chunking)"
```

### 丢弃

| 文件 | 理由 |
|------|------|
| `zchat/_version.py` | 自动生成，`git checkout` 恢复 |
| `zchat-channel-server` submodule 指针 | submodule 状态变更（dirty），需确认是否有意修改 |
| `.claude/skills/references/module-details.md` | 已移到 skill-1 本地目录 |
| `.claude/skills/zellij/` | plugin 管理，项目内不需要 |
| `.claude/ralph-loop.local.md` | ralph-loop 临时文件，忽略 |
| `docs/discuss/skill-dev/e2e-report/` | E2E 测试报告（4 个），可选保留 |
| `scripts/` | 如有，检查内容后决定 |

## 执行顺序

```bash
# 1. 恢复自动生成的文件
git checkout zchat/_version.py

# 2. 删除不需要的项目级 skill 文件
rm -rf .claude/skills/references .claude/skills/zellij

# 3. 按顺序 commit
git add zchat/cli/irc_manager.py
git commit -m "fix: ergo TLS config removal — unblock E2E tests"

git add claude.sh claude.local.env.example
git commit -m "feat: WSL2 proxy auto-rewrite in claude.sh"

git add ezagent42-marketplace
git commit -m "chore: update ezagent42-marketplace (add dev-loop-skills)"

git add docs/discuss/
git commit -m "docs: dev-loop skill specs, E2E test plan, architecture QA"

git add tests/e2e/test_agent_dm.py .artifacts/
git commit -m "feat: agent DM E2E test + bootstrap artifacts"
```
