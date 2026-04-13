---
type: test-plan
id: test-plan-003
status: draft
producer: skill-2
created_at: "2026-04-10"
trigger: "coverage-gap — 创建项目流程在 coverage-matrix-002 中标记为 ❌ not covered（E2E 缺口 #1）"
related:
  - coverage-matrix-002
---

# Test Plan: 创建项目 E2E 覆盖

## 触发原因

coverage-matrix-002 显示"创建项目"是 E2E 缺口清单的第 1 优先级（共 13 个缺口）。
Unit 测试 (test_project.py + test_project_create_params.py, 27 cases) 覆盖了 `create_project_config()` 函数逻辑和 Typer CliRunner 参数解析，但无任何 E2E 测试通过 subprocess 验证完整 CLI 流程。

缺口具体表现：
- 无 subprocess 级别的 `zchat project create` 测试
- 无全局 config.toml 自动创建/更新的端到端验证
- 无创建后与下游命令（list/use）集成的验证
- 无 claude.local.env proxy 文件生成的 E2E 验证

## 用例列表

### TC-001: 非交互式创建本地项目（happy path）

- **来源**：coverage-gap
- **优先级**：P0
- **前置条件**：干净的 ZCHAT_HOME 临时目录，无需 ergo/zellij
- **操作步骤**：
  1. 设置临时 ZCHAT_HOME
  2. 执行 `zchat project create test-local --server 127.0.0.1 --channels "#general" --agent-type claude --proxy ""`
  3. 检查 exit code
- **预期结果**：
  - exit code = 0
  - stdout 包含 "Project 'test-local' created"
  - `$ZCHAT_HOME/projects/test-local/` 目录存在
  - `$ZCHAT_HOME/projects/test-local/config.toml` 存在
- **涉及模块**：cli/app.py (cmd_project_create), cli/project.py, cli/paths.py

### TC-002: 创建后 config.toml 内容正确

- **来源**：coverage-gap
- **优先级**：P0
- **前置条件**：TC-001 创建的项目
- **操作步骤**：
  1. 读取 `$ZCHAT_HOME/projects/test-local/config.toml`
  2. 解析 TOML 内容
- **预期结果**：
  - `server` = "local"
  - `default_channels` 包含 "#general"
  - `default_runner` = "claude"（因为 --agent-type claude）
  - `zellij.session` = "zchat-test-local"
  - `mcp_server_cmd` = ["zchat-channel"]
  - 不含旧格式的 `[irc]` 或 `[tmux]` section
- **涉及模块**：cli/project.py (create_project_config), cli/defaults.py

### TC-003: 全局配置自动创建 server 条目

- **来源**：coverage-gap
- **优先级**：P0
- **前置条件**：TC-001 创建的项目
- **操作步骤**：
  1. 读取 `$ZCHAT_HOME/config.toml`
  2. 解析 TOML 内容
- **预期结果**：
  - `servers.local` 存在
  - `servers.local.host` = "127.0.0.1"
  - `servers.local.port` = 6667
  - `servers.local.tls` = false
- **涉及模块**：cli/config_cmd.py (ensure_server_in_global, save_global_config)

### TC-004: 重复创建项目报错

- **来源**：coverage-gap
- **优先级**：P0
- **前置条件**：TC-001 的项目已存在
- **操作步骤**：
  1. 再次执行 `zchat project create test-local --server 127.0.0.1 --channels "#general" --agent-type claude --proxy ""`
- **预期结果**：
  - exit code = 1
  - stdout 包含 "already exists"
  - 原有 config.toml 内容未被修改
- **涉及模块**：cli/app.py (cmd_project_create 的 exists 检查)

### TC-005: 创建带 proxy 的项目

- **来源**：coverage-gap
- **优先级**：P1
- **前置条件**：干净的 ZCHAT_HOME
- **操作步骤**：
  1. 执行 `zchat project create proxy-proj --server 127.0.0.1 --channels "#general" --agent-type claude --proxy "10.0.0.1:8080"`
  2. 检查 exit code
  3. 读取 `$ZCHAT_HOME/projects/proxy-proj/claude.local.env`
- **预期结果**：
  - exit code = 0
  - `claude.local.env` 文件存在
  - 包含 `HTTP_PROXY=http://10.0.0.1:8080`
  - 包含 `HTTPS_PROXY=http://10.0.0.1:8080`
  - config.toml 的 `env_file` 指向该 env 文件
- **涉及模块**：cli/app.py (proxy 处理逻辑)

### TC-006: 云端服务器项目自动 TLS

- **来源**：coverage-gap
- **优先级**：P1
- **前置条件**：干净的 ZCHAT_HOME
- **操作步骤**：
  1. 执行 `zchat project create cloud-proj --server zchat.inside.h2os.cloud --channels "#general" --agent-type claude --proxy ""`
  2. 读取全局配置
- **预期结果**：
  - exit code = 0
  - 全局配置中 server 条目的 host = "zchat.inside.h2os.cloud"
  - 全局配置中 server 条目的 tls = true
  - 全局配置中 server 条目的 port = 6697（preset 默认值）
- **涉及模块**：cli/app.py (preset 匹配), cli/defaults.py (server_presets), cli/config_cmd.py

### TC-007: 创建后可被 project list 列出

- **来源**：coverage-gap
- **优先级**：P1
- **前置条件**：TC-001 创建的项目
- **操作步骤**：
  1. 执行 `zchat project list`
- **预期结果**：
  - exit code = 0
  - stdout 包含 "test-local"
- **涉及模块**：cli/app.py (cmd_project_list), cli/project.py (list_projects)

### TC-008: 无效 agent-type 报错

- **来源**：coverage-gap
- **优先级**：P2
- **前置条件**：干净的 ZCHAT_HOME
- **操作步骤**：
  1. 执行 `zchat project create bad-proj --server 127.0.0.1 --channels "#general" --agent-type nonexistent-type`
- **预期结果**：
  - exit code = 1
  - stdout 包含 "not found" 或 "error"
  - 项目目录不存在（不应被部分创建）
- **涉及模块**：cli/app.py (agent_type 验证)

### TC-009: 自定义端口和 TLS 参数

- **来源**：coverage-gap
- **优先级**：P2
- **前置条件**：干净的 ZCHAT_HOME
- **操作步骤**：
  1. 执行 `zchat project create custom-proj --server 127.0.0.1 --port 7000 --tls --channels "#dev" --agent-type claude --proxy ""`
  2. 读取全局配置
- **预期结果**：
  - exit code = 0
  - 全局配置中 `servers.local.port` = 7000
  - 全局配置中 `servers.local.tls` = true
  - 项目配置中 `default_channels` 包含 "#dev"
- **涉及模块**：cli/app.py (cmd_project_create), cli/config_cmd.py (ensure_server_in_global)

## 统计

| 指标 | 值 |
|------|-----|
| 总用例数 | 9 |
| P0 | 4 |
| P1 | 3 |
| P2 | 2 |
| 来源：code-diff | 0 |
| 来源：eval-doc | 0 |
| 来源：coverage-gap | 9 |
| 来源：bug-feedback | 0 |

## 风险标注

- **高风险**：TC-001~TC-003 覆盖核心 happy path——当前完全无 E2E 覆盖，若 CLI 入口与内部逻辑存在集成问题，现有 unit 测试无法发现
- **回归风险**：无（此前无 E2E 用例，不存在回归基线）
- **覆盖未知**：coverage-matrix-002 状态为 draft（待确认），但缺口标注明确
- **实现注意**：所有用例不依赖 ergo/zellij/IRC，仅需 ZCHAT_HOME 隔离 + subprocess 调用，可独立于现有 E2E fixture 运行

## E2E 实现建议

- 新建 `tests/e2e/test_project_create.py`，使用独立的 `tmp_path` + `ZCHAT_HOME` fixture
- 不需要 `ergo_server`、`zellij_session` 等重量级 fixture
- 使用 `subprocess.run(["uv", "run", "python", "-m", "zchat.cli", ...])` 模式
- TC-001~TC-004 可共享同一个 ZCHAT_HOME（顺序执行）
- TC-005~TC-009 各自使用独立 ZCHAT_HOME
