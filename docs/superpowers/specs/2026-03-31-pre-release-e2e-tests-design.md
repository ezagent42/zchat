# Pre-release E2E Test Suite

**Date:** 2026-03-31
**Status:** Draft

## Goal

新增一套 pre-release 验收测试，通过实际安装的 `zchat` CLI 命令（而非 `uv run python -m zchat.cli`）驱动全部功能，覆盖用户从安装到日常使用的完整路径。现有 E2E 测试保留不变，两套共存。

## 动机

当前 E2E 测试通过 `uv run python -m zchat.cli` 调用 CLI，跳过了 Homebrew 安装、console_scripts entry point 解析、依赖打包等环节。此外，`project create`、`doctor`、`setup weechat`、`template` 等命令未被 E2E 覆盖。pre-release 测试填补这段"最后一公里"。

## 设计决策

### CLI 参数完备化（取代 `--non-interactive`）

不引入全局 `--non-interactive` flag。改为确保每个有交互提示的命令都能通过 CLI 参数提供全部必要输入——参数充足时直接执行，不进入交互。

| 命令 | 需补充的 CLI 参数 |
|------|------------------|
| `project create` | `--server`, `--port`, `--username`, `--agent-type`, `--channels` 等 |
| `project remove` | `--yes` / `-y`（跳过确认） |
| `setup weechat` | 已有 `--force` |
| `auth login` | `--issuer`, `--client-id` 已有 |

原则：缺少必要参数时才进入交互式提示。

### CLI 入口可配置

通过 `ZCHAT_CMD` 环境变量切换 CLI 入口：

| 场景 | ZCHAT_CMD 值 | 说明 |
|------|-------------|------|
| 开发迭代（默认） | `zchat`（editable install） | 测试当前代码，走 console_scripts entry point |
| 发布前验收 | `/opt/homebrew/bin/zchat` | 测试 Homebrew 安装的实际二进制 |

### 与现有 E2E 的关系

| 方面 | 现有 E2E | Pre-release |
|------|---------|-------------|
| CLI 入口 | `uv run python -m zchat.cli` | `zchat`（可配置） |
| 项目配置 | fixture 直接写 config.toml | `zchat project create` + CLI 参数 |
| IRC daemon | `IrcManager.daemon_start()` 直接调用 | `zchat irc daemon start` |
| WeeChat | 直接 tmux 命令启动 | `zchat irc start` |
| 覆盖范围 | agent 生命周期 + 消息 | 全命令覆盖 |
| 定位 | 开发迭代 | 发布前验收 |
| 运行环境 | 本地手动触发 | 本地手动触发 |

## 架构

### 目录结构

```
tests/
├── shared/                        # 公共测试工具
│   ├── __init__.py
│   ├── irc_probe.py               # 从 tests/e2e/irc_probe.py 搬迁
│   ├── tmux_helpers.py            # tmux send-keys、capture、wait 函数
│   └── cli_runner.py              # 统一的 CLI 调用封装
├── e2e/
│   ├── conftest.py                # 改为 import from tests.shared
│   ├── irc_probe.py               # 删除，改为从 shared 导入
│   └── test_e2e.py                # 不变
├── pre_release/
│   ├── conftest.py                # pre-release 专用 fixtures
│   ├── test_00_doctor.py
│   ├── test_01_project.py
│   ├── test_02_template.py
│   ├── test_03_irc.py
│   ├── test_04_agent.py
│   ├── test_05_setup.py
│   ├── test_06_auth.py            # @pytest.mark.manual
│   ├── test_07_self_update.py     # @pytest.mark.manual
│   └── test_08_shutdown.py
└── unit/
    └── ...                        # 不变
```

### `tests/shared/cli_runner.py`

```python
class CliRunner:
    def __init__(self, cmd: str, project: str, env: dict):
        """
        cmd: "zchat" 或 "/opt/homebrew/bin/zchat" 或 "uv run python -m zchat.cli"
        project: 项目名
        env: ZCHAT_HOME, ZCHAT_TMUX_SESSION 等环境变量
        """

    def run(self, *args, check=True) -> CompletedProcess:
        """执行: {cmd} --project {project} {args}"""

    def run_unchecked(self, *args) -> CompletedProcess:
        """同上但不检查 returncode，用于测试错误场景"""
```

- 现有 E2E 的 `zchat_cli` fixture 改为基于 `CliRunner`，cmd 固定为 `uv run python -m zchat.cli`
- Pre-release 的 fixture 基于 `CliRunner`，cmd 从 `ZCHAT_CMD` 环境变量读取（默认 `zchat`）

### `tests/shared/tmux_helpers.py`

```python
def send_keys(session_name: str, target: str, keys: str) -> None
def capture_pane(session_name: str, target: str) -> str
def wait_for_content(session_name: str, target: str, pattern: str, timeout: float) -> bool
```

从 `conftest.py` 中散落的 tmux 操作代码抽取而来。

### `tests/shared/irc_probe.py`

从 `tests/e2e/irc_probe.py` 直接搬迁，接口不变。

## Pre-release Fixtures（`tests/pre_release/conftest.py`）

```python
@pytest.fixture(scope="session")
def zchat_cmd():
    """从 ZCHAT_CMD 环境变量读取，默认 "zchat"。验证命令可执行。"""

@pytest.fixture(scope="session")
def e2e_port():
    """动态端口分配，避免与其他测试冲突。"""

@pytest.fixture(scope="session")
def e2e_home(tmp_path_factory):
    """隔离的 ZCHAT_HOME 临时目录。不预置 config.toml——由 project create 测试创建。"""

@pytest.fixture(scope="session")
def tmux_session():
    """创建 headless tmux session，测试结束后销毁。"""

@pytest.fixture(scope="session")
def cli(zchat_cmd, e2e_home, tmux_session):
    """返回 CliRunner 实例。"""

@pytest.fixture(scope="session")
def ergo_server(cli, e2e_port):
    """通过 CLI 启动 ergo: zchat irc daemon start --port {port}"""

@pytest.fixture(scope="session")
def irc_probe(ergo_server):
    """共享的 IRC 探针，连接 #general。"""
```

关键区别：`e2e_home` 不预置 config.toml，项目配置由 `test_01_project.py::test_project_create` 通过 CLI 创建。

## 测试用例

### `test_00_doctor.py` — 环境检查（无外部依赖）

| 用例 | 说明 |
|------|------|
| `test_doctor_shows_status` | `zchat doctor` 正常输出，exit 0 |
| `test_doctor_checks_dependencies` | 输出包含 tmux、ergo、weechat 等检查项 |

### `test_01_project.py` — 项目生命周期

| 用例 | 说明 |
|------|------|
| `test_project_create` | 完整参数创建项目，验证 config.toml 生成 |
| `test_project_list` | 列表包含刚创建的项目 |
| `test_project_show` | 显示项目配置，字段与创建参数一致 |
| `test_project_set` | `zchat set irc.port 6668`，验证配置更新 |
| `test_project_use` | 切换默认项目 |
| `test_project_create_second` | 创建第二个项目 |
| `test_project_remove_second` | `--yes` 删除，验证列表中消失 |

### `test_02_template.py` — 模板管理

| 用例 | 说明 |
|------|------|
| `test_template_list` | 列出可用模板，至少包含 "claude" |
| `test_template_show` | 显示 claude 模板详情 |

### `test_03_irc.py` — IRC 基础设施

| 用例 | 说明 |
|------|------|
| `test_irc_daemon_start` | 启动 ergo，验证端口监听 |
| `test_irc_status_daemon_running` | `zchat irc status` 显示 daemon running |
| `test_irc_start_weechat` | 启动 WeeChat，验证连接到 IRC |
| `test_irc_status_all_running` | status 显示 daemon + weechat 都 running |
| `test_irc_stop_weechat` | 停止 WeeChat |
| `test_irc_status_weechat_stopped` | status 确认 weechat stopped |
| `test_irc_start_weechat_again` | 重新启动 WeeChat（为后续 agent 测试准备） |

### `test_04_agent.py` — Agent 完整生命周期

| 用例 | 说明 |
|------|------|
| `test_agent_create` | 创建 agent0，irc_probe 验证 nick 上线 |
| `test_agent_list` | 列表包含 agent0，状态 running |
| `test_agent_status` | 显示 agent0 详细信息 |
| `test_agent_send` | 发送消息，irc_probe 验证收到 |
| `test_agent_create_second` | 创建 agent1 |
| `test_agent_restart` | 重启 agent1，验证重新上线 |
| `test_agent_stop` | 停止 agent1，irc_probe 验证下线 |
| `test_agent_list_after_stop` | agent1 状态变为 stopped |

### `test_05_setup.py` — WeeChat 插件安装

| 用例 | 说明 |
|------|------|
| `test_setup_weechat` | `zchat setup weechat --force`，验证插件文件存在 |

### `test_06_auth.py` — 认证（`@pytest.mark.manual`，默认跳过）

| 用例 | 说明 |
|------|------|
| `test_auth_status` | `zchat auth status`，验证输出格式 |
| `test_auth_logout` | `zchat auth logout`（如有已有 token） |

### `test_07_self_update.py` — 自更新（`@pytest.mark.manual`，默认跳过）

| 用例 | 说明 |
|------|------|
| `test_self_update_check` | 仅验证命令可执行，不实际更新 |

### `test_08_shutdown.py` — 全量停止

| 用例 | 说明 |
|------|------|
| `test_shutdown` | `zchat shutdown`，验证所有 agent 下线、ergo 停止 |
| `test_irc_status_after_shutdown` | 确认一切已清理 |

## pytest mark 与运行方式

```ini
# pyproject.toml 追加
[tool.pytest.ini_options]
markers = [
    "e2e: end-to-end tests requiring ergo + tmux",
    "prerelease: pre-release acceptance tests",
    "manual: tests requiring external services, skipped by default",
]
```

```bash
# 开发时（editable install）
uv run pytest tests/pre_release/ -v -m "prerelease and not manual"

# Homebrew 发布前验收
ZCHAT_CMD=zchat uv run pytest tests/pre_release/ -v -m "prerelease and not manual"

# 包含手动项
ZCHAT_CMD=zchat uv run pytest tests/pre_release/ -v -m prerelease
```

## 实现范围

### 需要新建

1. `tests/shared/__init__.py` — 包初始化
2. `tests/shared/cli_runner.py` — CliRunner 类
3. `tests/shared/tmux_helpers.py` — tmux 工具函数
4. `tests/shared/irc_probe.py` — 从 e2e 搬迁
5. `tests/pre_release/conftest.py` — fixtures
6. `tests/pre_release/test_00_doctor.py` ~ `test_08_shutdown.py` — 9 个测试文件

### 需要修改

1. `tests/e2e/conftest.py` — 改为导入 `tests.shared`
2. `tests/e2e/test_e2e.py` — 更新 irc_probe 导入路径
3. `zchat/cli/app.py` — `project create` 补充 CLI 参数
4. `zchat/cli/app.py` — `project remove` 添加 `--yes`
5. `pyproject.toml` — 追加 pytest markers

### 不需要修改

- `tests/unit/` — 不受影响
- `zchat/cli/irc_manager.py` — `daemon start` 已有 `--port` 参数
- `zchat/cli/auth.py` — `auth login` 已有必要参数

## 约束

- pre-release 测试仅在本地手动触发，不纳入 CI
- 测试之间有顺序依赖，通过 `pytest-order` 保证
- `auth login` 和 `self-update` 标记 `@pytest.mark.manual`，默认跳过
- session-scoped fixtures 保证 ergo/tmux 等资源在整个套件生命周期内复用
