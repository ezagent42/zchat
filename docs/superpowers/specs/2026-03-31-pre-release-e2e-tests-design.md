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

原则：缺少必要参数时才进入交互式提示。

#### `project create` 参数化

当前 `cmd_project_create(name)` 仅接受 positional `name`，其余通过 `typer.prompt()` 交互获取。需添加以下 `typer.Option` 参数：

```python
@project_app.command("create")
def cmd_project_create(
    name: str,
    server: Optional[str] = typer.Option(None, help="IRC server address"),
    port: Optional[int] = typer.Option(None, help="IRC port"),
    tls: Optional[bool] = typer.Option(None, help="Enable TLS"),
    password: Optional[str] = typer.Option(None, help="IRC password"),
    channels: Optional[str] = typer.Option(None, help="Default channels"),
    agent_type: Optional[str] = typer.Option(None, "--agent-type", help="Agent template name (e.g. 'claude')"),
    proxy: Optional[str] = typer.Option(None, help="HTTP proxy (ip:port)"),
):
```

条件跳过逻辑：
- `--server` 提供时跳过 server 选择菜单；未提供 `--port`/`--tls` 时使用 server 对应的默认值（本地: 6667/notls，zchat.inside: 6697/tls）
- `--password` 未提供时默认空字符串
- `--channels` 提供时跳过 channels 提示（默认 `"#general"`）
- `--agent-type` 提供时直接按名称匹配模板（单个名称），跳过多选菜单；未找到模板则报错退出。注：当前交互式流程支持多选，但 `config.toml` 只存储 `default_type`（单个值），因此 CLI 参数只接受单个模板名即可
- `--proxy` 提供时跳过 Claude proxy 提示；空字符串表示不使用代理
- 所有参数都未提供时，行为与当前完全一致（交互式向导）

测试调用示例：
```bash
zchat project create e2e-test \
    --server 127.0.0.1 --port 16789 \
    --channels "#general" --agent-type claude
```

#### `project remove` 确认机制

当前 `cmd_project_remove` 无确认提示，直接删除。保持现状——不添加 `--yes` flag，因为无确认可跳过。

#### 其他命令

| 命令 | 状态 |
|------|------|
| `setup weechat` | 已有 `--force`，无需改动 |
| `auth login` | 已有 `--issuer`, `--client-id`，无需改动 |

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

闭包工厂函数（与现有 E2E `zchat_cli` 风格一致）：

```python
def make_cli_runner(cmd: list[str], project: str, env: dict) -> Callable:
    """创建 CLI 运行器闭包。
    
    cmd: ["zchat"] 或 ["uv", "run", "python", "-m", "zchat.cli"] 等
    project: 项目名
    env: ZCHAT_HOME, ZCHAT_TMUX_SESSION 等环境变量
    """
    def run(*args, check=True) -> CompletedProcess:
        full_cmd = [*cmd, "--project", project, *args]
        result = subprocess.run(full_cmd, env={**os.environ, **env},
                                capture_output=True, text=True)
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, full_cmd,
                output=result.stdout, stderr=result.stderr)
        return result
    return run
```

- 现有 E2E：`make_cli_runner(["uv", "run", ...], project, env)`
- Pre-release：`make_cli_runner([zchat_cmd], project, env)`

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
    """隔离的 ZCHAT_HOME 临时目录。"""

@pytest.fixture(scope="session")
def tmux_session():
    """创建 headless tmux session，测试结束后销毁。"""

@pytest.fixture(scope="session")
def project(cli, e2e_port):
    """通过 CLI 创建项目——所有需要项目的测试依赖此 fixture。
    
    zchat project create prerelease-test \
        --server 127.0.0.1 --port {e2e_port} \
        --channels "#general" --agent-type claude
    
    Yield 项目名，teardown 时 zchat project remove。
    """

@pytest.fixture(scope="session")
def cli(zchat_cmd, e2e_home, tmux_session):
    """返回 CliRunner 实例（闭包工厂函数，与现有 E2E 风格一致）。"""

@pytest.fixture(scope="session")
def ergo_server(cli, project):
    """通过 CLI 启动 ergo: zchat irc daemon start"""

@pytest.fixture(scope="session")
def irc_probe(ergo_server):
    """共享的 IRC 探针，连接 #general。"""
```

**Fixture 依赖链：** `zchat_cmd` → `cli` → `project` → `ergo_server` → `irc_probe`

关键设计决策：
- **项目创建是 fixture 而非 test case**——解决 chicken-and-egg 问题。`ergo_server`、`irc_probe` 等 session-scoped fixture 需要项目存在才能工作，而 pytest 在测试运行前就解析 fixtures。
- **项目名是常量**——`PROJECT_NAME = "prerelease-test"` 定义在 `conftest.py` 顶层，`cli` 和 `project` fixture 共享。`cli` fixture 在 `project` 创建之前就需要项目名来构造 `--project` 参数。注：`project create` 时 `--project` 指向尚不存在的项目不会报错——`app.py` 的 `main()` callback 对 `project` 子命令跳过 `load_project_config()`。
- `test_01_project.py` 中的 `test_project_create` 改为测试 **第二个项目** 的创建/管理，验证 CLI 参数化创建的完整流程。主项目由 `project` fixture 保证始终存在。
- `CliRunner` 使用闭包工厂函数（与现有 E2E 的 `zchat_cli` 风格一致），不引入类。
- 测试运行方式必须使用 `uv run pytest`，确保 editable install 的 `zchat` 在 PATH 上。
- **测试文件排序**——文件名数字前缀（`test_00_` ~ `test_08_`）利用 pytest 默认的字母序收集保证文件间执行顺序。文件内测试用 `@pytest.mark.order()` 显式指定顺序。

**目录级标记：** 通过 `conftest.py` 的 `pytest_collection_modifyitems` hook 为整个目录下的测试自动添加 `prerelease` 标记（`conftest.py` 的 `pytestmark` 不会自动传播到同目录的测试文件）：
```python
# tests/pre_release/conftest.py
def pytest_collection_modifyitems(items):
    for item in items:
        if "pre_release" in str(item.fspath):
            item.add_marker(pytest.mark.prerelease)
```

## 测试用例

### `test_00_doctor.py` — 环境检查（无外部依赖）

| 用例 | 说明 |
|------|------|
| `test_doctor_shows_status` | `zchat doctor` 正常输出，exit 0 |
| `test_doctor_checks_dependencies` | 输出包含 tmux、ergo、weechat 等检查项 |

### `test_01_project.py` — 项目生命周期

注：主项目由 `project` fixture 创建。此文件测试项目管理命令。

| 用例 | 说明 |
|------|------|
| `test_project_list` | 列表包含主项目 |
| `test_project_show` | 显示项目配置，字段与创建参数一致 |
| `test_project_set` | `zchat set irc.port 6668`，验证配置更新，然后恢复原值 |
| `test_project_create_second` | 用完整 CLI 参数创建第二个项目，验证 config.toml 生成 |
| `test_project_use` | 切换默认项目到第二个 |
| `test_project_remove_second` | 删除第二个项目，验证列表中消失 |

### `test_02_template.py` — 模板管理

| 用例 | 说明 |
|------|------|
| `test_template_list` | 列出可用模板，至少包含 "claude" |
| `test_template_show` | 显示 claude 模板详情 |
| `test_template_create` | 创建空模板脚手架，验证目录生成 |
| `test_template_set` | 设置模板 .env 变量，验证写入 |

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
| `test_irc_daemon_stop` | 停止 ergo daemon，验证端口释放 |
| `test_irc_daemon_restart` | 重新启动 ergo（为后续 agent 测试准备） |

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
| `test_auth_refresh` | `zchat auth refresh`，验证命令可执行 |
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
# pytest.ini 追加（项目使用 pytest.ini 而非 pyproject.toml 配置 pytest）
[pytest]
markers =
    integration: requires real IRC server connection
    e2e: end-to-end tests requiring ergo + tmux
    prerelease: pre-release acceptance tests
    manual: tests requiring external services, skipped by default
    order: test execution order (pytest-order)
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
2. `tests/shared/cli_runner.py` — CLI runner 闭包工厂函数
3. `tests/shared/tmux_helpers.py` — tmux 工具函数
4. `tests/shared/irc_probe.py` — 从 e2e 搬迁
5. `tests/pre_release/__init__.py` — 包初始化
6. `tests/pre_release/conftest.py` — fixtures
7. `tests/pre_release/test_00_doctor.py` ~ `test_08_shutdown.py` — 9 个测试文件

### 需要修改

1. `tests/e2e/irc_probe.py` — 改为兼容重导出：`from tests.shared.irc_probe import IrcProbe`（`conftest.py` 的 `from irc_probe import IrcProbe` 无需改动）
2. `zchat/cli/app.py` — `project create` 补充 CLI 参数（`--server`, `--port`, `--tls`, `--password`, `--channels`, `--agent-type`, `--proxy`）
3. `pytest.ini` — 追加 `prerelease` 和 `manual` markers（项目使用 `pytest.ini` 而非 `pyproject.toml` 配置 pytest）

### 不需要修改

- `tests/unit/` — 不受影响
- `zchat/cli/irc_manager.py` — `daemon start` 已有 `--port` 参数
- `zchat/cli/auth.py` — `auth login` 已有必要参数

## 约束

- pre-release 测试仅在本地手动触发，不纳入 CI
- 测试之间有顺序依赖，通过 `pytest-order` 保证
- `auth login` 和 `self-update` 标记 `@pytest.mark.manual`，默认跳过
- session-scoped fixtures 保证 ergo/tmux 等资源在整个套件生命周期内复用
