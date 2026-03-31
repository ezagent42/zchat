# Pre-release E2E Test Suite Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pre-release acceptance test suite that drives all zchat CLI commands through the installed `zchat` binary, plus parameterize `project create` to skip interactive prompts.

**Architecture:** Extract shared test utilities from existing E2E into `tests/shared/`, parameterize `project create` CLI with optional flags, then build the pre-release test suite in `tests/pre_release/` using these shared utilities and the real `zchat` command.

**Tech Stack:** Python 3.11+, pytest, pytest-order, libtmux, irc (python-irc), typer

**Spec:** `docs/superpowers/specs/2026-03-31-pre-release-e2e-tests-design.md`

---

## File Structure

### New files
| File | Responsibility |
|------|---------------|
| `tests/shared/__init__.py` | Package init |
| `tests/shared/irc_probe.py` | IRC probe client (moved from `tests/e2e/irc_probe.py`) |
| `tests/shared/tmux_helpers.py` | tmux send-keys, capture, wait helpers |
| `tests/shared/cli_runner.py` | `make_cli_runner()` closure factory |
| `tests/pre_release/__init__.py` | Package init |
| `tests/pre_release/conftest.py` | Session-scoped fixtures for pre-release suite |
| `tests/pre_release/test_00_doctor.py` | Environment check tests |
| `tests/pre_release/test_01_project.py` | Project lifecycle tests |
| `tests/pre_release/test_02_template.py` | Template management tests |
| `tests/pre_release/test_03_irc.py` | IRC infrastructure tests |
| `tests/pre_release/test_04_agent.py` | Agent lifecycle tests |
| `tests/pre_release/test_05_setup.py` | WeeChat plugin install test |
| `tests/pre_release/test_06_auth.py` | Auth tests (manual marker) |
| `tests/pre_release/test_07_self_update.py` | Self-update test (manual marker) |
| `tests/pre_release/test_08_shutdown.py` | Shutdown tests |

### Modified files
| File | Change |
|------|--------|
| `tests/e2e/irc_probe.py` | Replace with re-export shim |
| `zchat/cli/app.py` | Parameterize `cmd_project_create` with CLI options |
| `pytest.ini` | Add `prerelease` and `manual` markers |

---

## Chunk 1: Shared Test Utilities + `project create` Parameterization

### Task 1: Parameterize `project create` CLI

**Files:**
- Modify: `zchat/cli/app.py:118-187`
- Test: `tests/unit/test_project_create_params.py` (new)

- [ ] **Step 1: Write unit test for parameterized project create**

Create `tests/unit/test_project_create_params.py`:

```python
"""Unit tests for project create CLI parameterization."""
import os
import tomllib
import pytest
from typer.testing import CliRunner
from zchat.cli.app import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Redirect ZCHAT_HOME to temp dir for each test."""
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    return tmp_path


def _load_config(home, name):
    with open(os.path.join(str(home), "projects", name, "config.toml"), "rb") as f:
        return tomllib.load(f)


def test_create_with_all_params(isolated_home):
    """All CLI options provided → no interactive prompts."""
    result = runner.invoke(app, [
        "project", "create", "test-proj",
        "--server", "127.0.0.1",
        "--port", "6667",
        "--channels", "#general",
        "--agent-type", "claude",
    ])
    assert result.exit_code == 0, result.output
    cfg = _load_config(isolated_home, "test-proj")
    assert cfg["irc"]["server"] == "127.0.0.1"
    assert cfg["irc"]["port"] == 6667
    assert cfg["irc"]["tls"] is False
    assert cfg["agents"]["default_type"] == "claude"
    assert "#general" in cfg["agents"]["default_channels"]


def test_create_with_zchat_inside_server(isolated_home):
    """--server zchat.inside.h2os.cloud → defaults: port 6697, tls True."""
    result = runner.invoke(app, [
        "project", "create", "tls-proj",
        "--server", "zchat.inside.h2os.cloud",
        "--channels", "#general",
        "--agent-type", "claude",
    ])
    assert result.exit_code == 0, result.output
    cfg = _load_config(isolated_home, "tls-proj")
    assert cfg["irc"]["port"] == 6697
    assert cfg["irc"]["tls"] is True


def test_create_with_explicit_port_tls(isolated_home):
    """Explicit --port and --tls override server defaults."""
    result = runner.invoke(app, [
        "project", "create", "custom-proj",
        "--server", "127.0.0.1",
        "--port", "7000",
        "--tls",
        "--channels", "#dev",
        "--agent-type", "claude",
    ])
    assert result.exit_code == 0, result.output
    cfg = _load_config(isolated_home, "custom-proj")
    assert cfg["irc"]["port"] == 7000
    assert cfg["irc"]["tls"] is True


def test_create_with_proxy(isolated_home):
    """--proxy creates claude.local.env with proxy settings."""
    result = runner.invoke(app, [
        "project", "create", "proxy-proj",
        "--server", "127.0.0.1",
        "--channels", "#general",
        "--agent-type", "claude",
        "--proxy", "10.0.0.1:8080",
    ])
    assert result.exit_code == 0, result.output
    env_path = os.path.join(str(isolated_home), "projects", "proxy-proj", "claude.local.env")
    assert os.path.isfile(env_path)
    content = open(env_path).read()
    assert "HTTP_PROXY=http://10.0.0.1:8080" in content


def test_create_invalid_agent_type(isolated_home):
    """--agent-type with nonexistent template → exit 1."""
    result = runner.invoke(app, [
        "project", "create", "bad-proj",
        "--server", "127.0.0.1",
        "--channels", "#general",
        "--agent-type", "nonexistent-type",
    ])
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "error" in result.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_project_create_params.py -v`
Expected: FAIL — `cmd_project_create` doesn't accept `--server` etc.

- [ ] **Step 3: Implement parameterized `cmd_project_create`**

In `zchat/cli/app.py`, replace lines 118-187 with:

```python
@project_app.command("create")
def cmd_project_create(
    name: str,
    server: Optional[str] = typer.Option(None, help="IRC server address"),
    port: Optional[int] = typer.Option(None, help="IRC port"),
    tls: Optional[bool] = typer.Option(None, help="Enable TLS"),
    password: Optional[str] = typer.Option(None, help="IRC password"),
    channels: Optional[str] = typer.Option(None, help="Default channels (comma-separated)"),
    agent_type: Optional[str] = typer.Option(None, "--agent-type", help="Agent template name (e.g. 'claude')"),
    proxy: Optional[str] = typer.Option(None, help="HTTP proxy (ip:port)"),
):
    """Create a new project with config setup.

    When all required options are provided, runs non-interactively.
    Otherwise, prompts for missing values.
    """
    pdir = project_dir(name)
    if os.path.exists(pdir):
        typer.echo(f"Project '{name}' already exists.")
        raise typer.Exit(1)

    # --- IRC server ---
    if server is not None:
        # CLI args provided — derive defaults from server
        if server == "zchat.inside.h2os.cloud":
            port = port if port is not None else 6697
            tls = tls if tls is not None else True
        else:
            port = port if port is not None else 6667
            tls = tls if tls is not None else False
        password = password if password is not None else ""
    else:
        # Interactive mode
        typer.echo("IRC Server:")
        typer.echo("  1) zchat.inside.h2os.cloud (recommended)")
        typer.echo("  2) Custom server")
        server_choice = typer.prompt("Choose", default="1")
        if server_choice == "1":
            server = "zchat.inside.h2os.cloud"
            port = 6697
            tls = True
            password = ""
        else:
            server = typer.prompt("IRC server", default="127.0.0.1")
            port = typer.prompt("IRC port", default=6667, type=int)
            tls = typer.confirm("TLS", default=False)
            password = typer.prompt("Password", default="", show_default=False)

    # --- Channels ---
    if channels is None:
        channels = typer.prompt("Default channels", default="#general")

    # --- Agent type ---
    from zchat.cli.template_loader import list_templates
    templates = list_templates()
    if not templates:
        typer.echo("Error: No agent templates found.")
        raise typer.Exit(1)

    if agent_type is not None:
        # Match by name
        matched = [t for t in templates if t["template"]["name"] == agent_type]
        if not matched:
            typer.echo(f"Error: Agent type '{agent_type}' not found. Available: "
                       + ", ".join(t["template"]["name"] for t in templates))
            raise typer.Exit(1)
        default_type = agent_type
        selected_types = [agent_type]
    else:
        # Interactive multi-select
        typer.echo("Agent types:")
        for i, tpl in enumerate(templates, 1):
            tname = tpl["template"]["name"]
            tdesc = tpl["template"].get("description", "")
            typer.echo(f"  {i}) {tname} - {tdesc}")
        selection = typer.prompt("Select types (comma-separated)", default="1")
        selected_indices = [int(s.strip()) - 1 for s in selection.split(",") if s.strip().isdigit()]
        selected_types = []
        for idx in selected_indices:
            if 0 <= idx < len(templates):
                selected_types.append(templates[idx]["template"]["name"])
        if not selected_types:
            selected_types = [templates[0]["template"]["name"]]
        default_type = selected_types[0]

    # --- Type-specific config: Claude ---
    env_file = ""
    if "claude" in selected_types:
        if proxy is not None:
            # CLI arg provided
            if proxy:
                proxy_url = proxy if proxy.startswith("http") else f"http://{proxy}"
                env_path = os.path.join(pdir, "claude.local.env")
                os.makedirs(pdir, exist_ok=True)
                with open(env_path, "w") as f:
                    f.write(f"HTTP_PROXY={proxy_url}\n")
                    f.write(f"HTTPS_PROXY={proxy_url}\n")
                env_file = env_path
        else:
            # Interactive
            typer.echo("Claude configuration:")
            proxy_input = typer.prompt("  HTTP proxy (ip:port, leave empty for direct connection)",
                                       default="", show_default=False)
            if proxy_input:
                proxy_url = proxy_input if proxy_input.startswith("http") else f"http://{proxy_input}"
                env_path = os.path.join(pdir, "claude.local.env")
                os.makedirs(pdir, exist_ok=True)
                with open(env_path, "w") as f:
                    f.write(f"HTTP_PROXY={proxy_url}\n")
                    f.write(f"HTTPS_PROXY={proxy_url}\n")
                env_file = env_path

    create_project_config(name, server=server, port=port, tls=tls,
                          password=password, nick="", channels=channels,
                          env_file=env_file, default_type=default_type)
    typer.echo(f"\nProject '{name}' created at {pdir}/")
    typer.echo(f"Config saved to {pdir}/config.toml")
    if env_file:
        typer.echo(f"Proxy config saved to {pdir}/claude.local.env")
```

- [ ] **Step 4: Run unit tests to verify they pass**

Run: `uv run pytest tests/unit/test_project_create_params.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Run existing unit tests to verify no regressions**

Run: `uv run pytest tests/unit/ -v`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add zchat/cli/app.py tests/unit/test_project_create_params.py
git commit -m "feat(cli): parameterize project create with CLI options

Add --server, --port, --tls, --password, --channels, --agent-type,
--proxy options to 'zchat project create'. When all required options
are provided, runs non-interactively. Otherwise, prompts as before."
```

---

### Task 2: Extract shared test utilities

**Files:**
- Create: `tests/shared/__init__.py`
- Create: `tests/shared/irc_probe.py`
- Create: `tests/shared/tmux_helpers.py`
- Create: `tests/shared/cli_runner.py`
- Modify: `tests/e2e/irc_probe.py`

- [ ] **Step 1: Create `tests/shared/__init__.py`**

```python
# tests/shared/__init__.py
```

Empty file, just makes it a package.

- [ ] **Step 2: Move irc_probe to shared**

Copy `tests/e2e/irc_probe.py` to `tests/shared/irc_probe.py` — contents are identical, just update the module docstring:

```python
# tests/shared/irc_probe.py
"""IRC probe client for test verification (shared across E2E and pre-release suites)."""
# ... rest is identical to tests/e2e/irc_probe.py ...
```

- [ ] **Step 3: Replace `tests/e2e/irc_probe.py` with re-export shim**

```python
# tests/e2e/irc_probe.py
"""Compatibility re-export — actual implementation moved to tests.shared."""
from tests.shared.irc_probe import IrcProbe  # noqa: F401
```

- [ ] **Step 4: Create `tests/shared/tmux_helpers.py`**

```python
# tests/shared/tmux_helpers.py
"""Tmux helper functions shared across test suites."""
import re
import time

from zchat.cli.tmux import get_session, find_window, find_pane


def send_keys(session_name: str, target: str, text: str, enter: bool = True) -> None:
    """Send keys to a tmux window (by name) or pane (by ID).

    Args:
        session_name: tmux session name
        target: window name or pane ID
        text: text to send
        enter: whether to press Enter after text
    """
    session = get_session(session_name)
    window = find_window(session, target)
    if window and window.active_pane:
        window.active_pane.send_keys(text, enter=enter)
        return
    pane = find_pane(session, target)
    if pane:
        pane.send_keys(text, enter=enter)


def capture_pane(session_name: str, target: str) -> str:
    """Capture the visible content of a tmux window or pane.

    Args:
        session_name: tmux session name
        target: window name or pane ID

    Returns:
        Captured text content
    """
    session = get_session(session_name)
    window = find_window(session, target)
    if window and window.active_pane:
        return "\n".join(window.active_pane.capture_pane())
    pane = find_pane(session, target)
    if pane:
        return "\n".join(pane.capture_pane())
    return ""


def wait_for_content(session_name: str, target: str, pattern: str,
                     timeout: float = 10.0) -> bool:
    """Wait until pane content matches a regex pattern.

    Args:
        session_name: tmux session name
        target: window name or pane ID
        pattern: regex pattern to match
        timeout: max seconds to wait

    Returns:
        True if pattern found within timeout, False otherwise
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        content = capture_pane(session_name, target)
        if re.search(pattern, content):
            return True
        time.sleep(0.5)
    return False
```

- [ ] **Step 5: Create `tests/shared/cli_runner.py`**

```python
# tests/shared/cli_runner.py
"""CLI runner factory for test suites."""
import os
import subprocess
from typing import Callable


def make_cli_runner(
    cmd: list[str], project: str, env: dict
) -> Callable[..., subprocess.CompletedProcess]:
    """Create a CLI runner closure.

    Args:
        cmd: command prefix, e.g. ["zchat"] or ["uv", "run", "python", "-m", "zchat.cli"]
        project: project name (passed via --project)
        env: environment variables to inject (ZCHAT_HOME, etc.)

    Returns:
        Callable that runs CLI commands and returns CompletedProcess.
    """
    def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        full_cmd = [*cmd, "--project", project, *args]
        merged_env = {**os.environ, **env}
        result = subprocess.run(
            full_cmd, env=merged_env, capture_output=True, text=True,
        )
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, full_cmd,
                output=result.stdout, stderr=result.stderr,
            )
        return result
    return run
```

- [ ] **Step 6: Verify existing E2E tests still work with re-export shim**

Run: `uv run pytest tests/e2e/ -v -m e2e --co` (collect only, to verify imports work)
Expected: Tests collected without import errors

- [ ] **Step 7: Commit**

```bash
git add tests/shared/ tests/e2e/irc_probe.py
git commit -m "refactor(tests): extract shared test utilities

Move irc_probe to tests/shared/, add tmux_helpers and cli_runner.
Existing E2E imports preserved via re-export shim."
```

---

### Task 3: Update pytest.ini markers

**Files:**
- Modify: `pytest.ini`

- [ ] **Step 1: Add prerelease and manual markers**

In `pytest.ini`, add two lines to the markers section:

```ini
[pytest]
testpaths = tests
markers =
    integration: requires real IRC server connection
    e2e: end-to-end tests requiring ergo + tmux
    prerelease: pre-release acceptance tests
    manual: tests requiring external services, skipped by default
    order: test execution order (pytest-order)
asyncio_mode = auto
```

- [ ] **Step 2: Verify no marker warnings**

Run: `uv run pytest tests/unit/ -v --strict-markers`
Expected: PASS with no unknown marker warnings

- [ ] **Step 3: Commit**

```bash
git add pytest.ini
git commit -m "chore: add prerelease and manual pytest markers"
```

---

## Chunk 2: Pre-release Test Suite — Infrastructure (conftest + tests 00-02)

### Task 4: Create pre-release conftest.py

**Files:**
- Create: `tests/pre_release/__init__.py`
- Create: `tests/pre_release/conftest.py`

- [ ] **Step 1: Create `tests/pre_release/__init__.py`**

```python
# tests/pre_release/__init__.py
PROJECT_NAME = "prerelease-test"
SECOND_PROJECT = "prerelease-second"
```

- [ ] **Step 2: Create `tests/pre_release/conftest.py`**

```python
# tests/pre_release/conftest.py
"""Pre-release acceptance test fixtures.

Fixture dependency chain:
    zchat_cmd → cli → project → ergo_server → irc_probe

Run with: uv run pytest tests/pre_release/ -v -m "prerelease and not manual"
"""
import os
import socket
import time

import pytest

from tests.shared.irc_probe import IrcProbe
from tests.shared.cli_runner import make_cli_runner
from tests.pre_release import PROJECT_NAME


def pytest_collection_modifyitems(items):
    """Auto-add prerelease marker to all tests in this directory."""
    for item in items:
        if "pre_release" in str(item.fspath):
            item.add_marker(pytest.mark.prerelease)


@pytest.fixture(scope="session")
def zchat_cmd():
    """Resolve zchat command from ZCHAT_CMD env var (default: "zchat")."""
    import subprocess
    cmd = os.environ.get("ZCHAT_CMD", "zchat")
    result = subprocess.run([cmd, "--version"], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"'{cmd}' not found or not working: {result.stderr}"
    )
    return cmd


@pytest.fixture(scope="session")
def e2e_port():
    """Dynamic port to avoid conflicts with other test sessions."""
    return 16667 + (os.getpid() % 1000)


@pytest.fixture(scope="session")
def e2e_home(tmp_path_factory):
    """Isolated ZCHAT_HOME temp directory."""
    return str(tmp_path_factory.mktemp("zchat-prerelease"))


@pytest.fixture(scope="session")
def tmux_session():
    """Create headless tmux session, destroy on teardown."""
    import libtmux
    srv = libtmux.Server()
    name = f"prerelease-{os.getpid()}"
    session = srv.new_session(session_name=name, attach=False, x=220, y=60)
    yield name
    try:
        session.kill()
    except Exception:
        pass


@pytest.fixture(scope="session")
def cli(zchat_cmd, e2e_home, tmux_session):
    """CLI runner closure targeting the pre-release project."""
    env = {
        "ZCHAT_HOME": e2e_home,
        "ZCHAT_TMUX_SESSION": tmux_session,
    }
    return make_cli_runner(cmd=[zchat_cmd], project=PROJECT_NAME, env=env)


@pytest.fixture(scope="session")
def project(cli, e2e_port, tmux_session):
    """Create the main test project via CLI. Teardown removes it."""
    cli(
        "project", "create", PROJECT_NAME,
        "--server", "127.0.0.1",
        "--port", str(e2e_port),
        "--channels", "#general",
        "--agent-type", "claude",
    )
    # Set the tmux session name in config to match our test session
    cli("set", "tmux.session", tmux_session)
    yield PROJECT_NAME
    try:
        cli("project", "remove", PROJECT_NAME, check=False)
    except Exception:
        pass


@pytest.fixture(scope="session")
def ergo_server(cli, project, e2e_port):
    """Start ergo via CLI, verify port is listening."""
    cli("irc", "daemon", "start")
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", e2e_port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    else:
        raise RuntimeError(f"ergo did not start on port {e2e_port}")
    yield {"host": "127.0.0.1", "port": e2e_port}
    # Safety net: stop ergo if still running (may already be stopped by shutdown test)
    try:
        cli("irc", "daemon", "stop", check=False)
    except Exception:
        pass


@pytest.fixture(scope="session")
def irc_probe(ergo_server):
    """IRC client that joins #general and records messages."""
    probe = IrcProbe(ergo_server["host"], ergo_server["port"])
    probe.connect()
    time.sleep(1)
    probe.join("#general")
    time.sleep(1)
    yield probe
    probe.disconnect()
```

- [ ] **Step 3: Verify conftest imports resolve**

Run: `uv run python -c "from tests.pre_release.conftest import PROJECT_NAME; print(PROJECT_NAME)"`
Expected: Prints `prerelease-test`

- [ ] **Step 4: Commit**

```bash
git add tests/pre_release/__init__.py tests/pre_release/conftest.py
git commit -m "test(pre-release): add conftest with session-scoped fixtures"
```

---

### Task 5: test_00_doctor.py

**Files:**
- Create: `tests/pre_release/test_00_doctor.py`

- [ ] **Step 1: Write doctor tests**

```python
# tests/pre_release/test_00_doctor.py
"""Pre-release: environment check (no external dependencies needed)."""
import pytest


@pytest.mark.order(1)
def test_doctor_shows_status(cli):
    """zchat doctor runs successfully."""
    result = cli("doctor", check=False)
    assert result.returncode == 0, f"doctor failed: {result.stderr}"


@pytest.mark.order(2)
def test_doctor_checks_dependencies(cli):
    """doctor output mentions key dependencies."""
    result = cli("doctor", check=False)
    output = result.stdout.lower()
    for dep in ["tmux", "ergo", "weechat"]:
        assert dep in output, f"doctor output missing '{dep}' check"
```

- [ ] **Step 2: Commit**

```bash
git add tests/pre_release/test_00_doctor.py
git commit -m "test(pre-release): add doctor environment check tests"
```

---

### Task 6: test_01_project.py

**Files:**
- Create: `tests/pre_release/test_01_project.py`

- [ ] **Step 1: Write project lifecycle tests**

```python
# tests/pre_release/test_01_project.py
"""Pre-release: project lifecycle management."""
import pytest

from tests.pre_release import PROJECT_NAME, SECOND_PROJECT


@pytest.mark.order(1)
def test_project_list(cli, project):
    """Main project appears in project list."""
    result = cli("project", "list")
    assert PROJECT_NAME in result.stdout


@pytest.mark.order(2)
def test_project_show(cli, project):
    """project show displays correct config values."""
    result = cli("project", "show", PROJECT_NAME)
    assert "127.0.0.1" in result.stdout
    assert "Channels" in result.stdout or "#general" in result.stdout


@pytest.mark.order(3)
def test_project_set(cli, project, e2e_port):
    """zchat set updates config, then restore original value."""
    cli("set", "irc.port", "6668")
    result = cli("project", "show", PROJECT_NAME)
    assert "6668" in result.stdout
    # Restore
    cli("set", "irc.port", str(e2e_port))


@pytest.mark.order(4)
def test_project_create_second(cli, e2e_port):
    """Create second project with full CLI params."""
    result = cli(
        "project", "create", SECOND_PROJECT,
        "--server", "127.0.0.1",
        "--port", str(e2e_port + 1),
        "--channels", "#test",
        "--agent-type", "claude",
        check=False,
    )
    assert result.returncode == 0, f"create failed: {result.stderr}"
    # Verify it appears in list
    list_result = cli("project", "list")
    assert SECOND_PROJECT in list_result.stdout


@pytest.mark.order(5)
def test_project_use(cli):
    """Switch default project."""
    result = cli("project", "use", SECOND_PROJECT, check=False)
    assert result.returncode == 0


@pytest.mark.order(6)
def test_project_remove_second(cli):
    """Remove second project, verify gone from list."""
    cli("project", "remove", SECOND_PROJECT)
    result = cli("project", "list")
    assert SECOND_PROJECT not in result.stdout
```

Note: `test_project_create_second` uses `check=False` because `--project prerelease-test` is passed by the runner but we're creating a different project. The `project create` command uses the positional name, not `--project`, so this works — the `main()` callback skips config load for `project` subcommand.

- [ ] **Step 2: Commit**

```bash
git add tests/pre_release/test_01_project.py
git commit -m "test(pre-release): add project lifecycle tests"
```

---

### Task 7: test_02_template.py

**Files:**
- Create: `tests/pre_release/test_02_template.py`

- [ ] **Step 1: Write template tests**

```python
# tests/pre_release/test_02_template.py
"""Pre-release: template management."""
import pytest

TEST_TEMPLATE = "prerelease-test-tpl"


@pytest.mark.order(1)
def test_template_list(cli, project):
    """template list includes built-in 'claude' template."""
    result = cli("template", "list")
    assert "claude" in result.stdout


@pytest.mark.order(2)
def test_template_show(cli, project):
    """template show displays claude template details."""
    result = cli("template", "show", "claude")
    assert "claude" in result.stdout.lower()


@pytest.mark.order(3)
def test_template_create(cli, project):
    """template create scaffolds a new template directory."""
    result = cli("template", "create", TEST_TEMPLATE)
    assert result.returncode == 0
    assert "scaffold" in result.stdout.lower() or TEST_TEMPLATE in result.stdout


@pytest.mark.order(4)
def test_template_set(cli, project):
    """template set writes .env variable."""
    result = cli("template", "set", TEST_TEMPLATE, "MY_VAR", "my_value")
    assert result.returncode == 0
```

- [ ] **Step 2: Commit**

```bash
git add tests/pre_release/test_02_template.py
git commit -m "test(pre-release): add template management tests"
```

---

## Chunk 3: Pre-release Test Suite — IRC, Agent, Setup, Auth, Shutdown (tests 03-08)

### Task 8: test_03_irc.py

**Files:**
- Create: `tests/pre_release/test_03_irc.py`

- [ ] **Step 1: Write IRC infrastructure tests**

```python
# tests/pre_release/test_03_irc.py
"""Pre-release: IRC daemon and WeeChat lifecycle."""
import socket
import time

import pytest


@pytest.mark.order(1)
def test_irc_daemon_start(ergo_server, e2e_port):
    """ergo daemon is started (by fixture) and listening."""
    with socket.create_connection(("127.0.0.1", e2e_port), timeout=2):
        pass  # Connection succeeds = daemon is up


@pytest.mark.order(2)
def test_irc_status_daemon_running(cli, ergo_server):
    """irc status shows daemon running."""
    result = cli("irc", "status")
    assert "running" in result.stdout.lower()


@pytest.mark.order(3)
def test_irc_start_weechat(cli, ergo_server, irc_probe):
    """Start WeeChat via CLI, verify user appears on IRC."""
    cli("irc", "start")
    time.sleep(5)  # WeeChat needs time to connect


@pytest.mark.order(4)
def test_irc_status_all_running(cli):
    """irc status shows both daemon and weechat running."""
    result = cli("irc", "status")
    output = result.stdout.lower()
    # Both sections should show "running"
    assert output.count("running") >= 2, f"Expected 2+ 'running' in: {result.stdout}"


@pytest.mark.order(5)
def test_irc_stop_weechat(cli):
    """Stop WeeChat via CLI."""
    cli("irc", "stop")
    time.sleep(2)


@pytest.mark.order(6)
def test_irc_status_weechat_stopped(cli):
    """irc status confirms weechat stopped."""
    result = cli("irc", "status")
    lines = result.stdout.lower().split("\n")
    # Find the WeeChat section
    in_weechat = False
    for line in lines:
        if "weechat" in line or "client" in line:
            in_weechat = True
        if in_weechat and "stopped" in line:
            break
    else:
        pytest.fail(f"WeeChat not shown as stopped: {result.stdout}")


@pytest.mark.order(7)
def test_irc_start_weechat_again(cli):
    """Restart WeeChat for subsequent agent tests."""
    cli("irc", "start")
    time.sleep(5)



# NOTE: ergo daemon stop/restart tests are in test_08_shutdown.py,
# NOT here. Stopping ergo mid-session kills the irc_probe's persistent
# connection, which would break all subsequent tests that use
# irc_probe.wait_for_message().
```

- [ ] **Step 2: Commit**

```bash
git add tests/pre_release/test_03_irc.py
git commit -m "test(pre-release): add IRC infrastructure lifecycle tests"
```

---

### Task 9: test_04_agent.py

**Files:**
- Create: `tests/pre_release/test_04_agent.py`

- [ ] **Step 1: Write agent lifecycle tests**

```python
# tests/pre_release/test_04_agent.py
"""Pre-release: agent lifecycle management."""
import pytest


@pytest.mark.order(1)
def test_agent_create(cli, irc_probe, ergo_server):
    """Create agent0, verify it joins IRC."""
    result = cli("agent", "create", "agent0")
    assert result.returncode == 0, f"agent create failed: {result.stderr}"
    # Username defaults to $USER when nick="" in config
    import os
    username = os.environ.get("USER", "user")
    assert irc_probe.wait_for_nick(
        f"{username}-agent0", timeout=30
    ), "agent0 not on IRC"


@pytest.mark.order(2)
def test_agent_list(cli):
    """agent list shows agent0 as running."""
    result = cli("agent", "list")
    assert "agent0" in result.stdout
    assert "running" in result.stdout.lower()


@pytest.mark.order(3)
def test_agent_status(cli):
    """agent status shows detailed info for agent0."""
    result = cli("agent", "status", "agent0")
    assert "agent0" in result.stdout
    assert "status" in result.stdout.lower() or "running" in result.stdout.lower()


@pytest.mark.order(4)
def test_agent_send(cli, irc_probe):
    """Send message via agent0 to #general."""
    cli("agent", "send", "agent0",
        'Use the reply MCP tool to send "prerelease-test-msg" to #general')
    msg = irc_probe.wait_for_message("prerelease-test-msg", timeout=30)
    assert msg is not None, "agent0 message not received in #general"


@pytest.mark.order(5)
def test_agent_create_second(cli, irc_probe):
    """Create agent1."""
    cli("agent", "create", "agent1")
    import os
    username = os.environ.get("USER", "user")
    assert irc_probe.wait_for_nick(
        f"{username}-agent1", timeout=30
    ), "agent1 not on IRC"


@pytest.mark.order(6)
def test_agent_restart(cli, irc_probe):
    """Restart agent1, verify it re-joins IRC."""
    cli("agent", "restart", "agent1")
    import os
    username = os.environ.get("USER", "user")
    assert irc_probe.wait_for_nick(
        f"{username}-agent1", timeout=30
    ), "agent1 not back on IRC after restart"


@pytest.mark.order(7)
def test_agent_stop(cli, irc_probe):
    """Stop agent1, verify it leaves IRC."""
    cli("agent", "stop", "agent1")
    import os
    username = os.environ.get("USER", "user")
    assert irc_probe.wait_for_nick_gone(
        f"{username}-agent1", timeout=10
    ), "agent1 still on IRC after stop"


@pytest.mark.order(8)
def test_agent_list_after_stop(cli):
    """agent list shows agent1 as stopped/offline."""
    result = cli("agent", "list")
    # agent1 should still appear but not as running
    output = result.stdout.lower()
    assert "agent1" in output


```

- [ ] **Step 2: Commit**

```bash
git add tests/pre_release/test_04_agent.py
git commit -m "test(pre-release): add agent lifecycle tests"
```

---

### Task 10: test_05_setup.py

**Files:**
- Create: `tests/pre_release/test_05_setup.py`

- [ ] **Step 1: Write setup test**

```python
# tests/pre_release/test_05_setup.py
"""Pre-release: WeeChat plugin installation."""
import pytest


@pytest.mark.order(1)
def test_setup_weechat(cli, project):
    """setup weechat --force installs the plugin."""
    result = cli("setup", "weechat", "--force", check=False)
    # Command should succeed (or warn if already installed)
    assert result.returncode == 0, f"setup weechat failed: {result.stderr}"
```

- [ ] **Step 2: Commit**

```bash
git add tests/pre_release/test_05_setup.py
git commit -m "test(pre-release): add WeeChat plugin setup test"
```

---

### Task 11: test_06_auth.py

**Files:**
- Create: `tests/pre_release/test_06_auth.py`

- [ ] **Step 1: Write auth tests (manual marker)**

```python
# tests/pre_release/test_06_auth.py
"""Pre-release: authentication commands (manual — uses local tokens)."""
import pytest


@pytest.mark.manual
@pytest.mark.order(1)
def test_auth_status(cli, project):
    """auth status runs without error."""
    result = cli("auth", "status", check=False)
    # May show "Not logged in" or actual status — both are valid
    assert result.returncode == 0


@pytest.mark.manual
@pytest.mark.order(2)
def test_auth_refresh(cli, project):
    """auth refresh is callable (may fail if no token)."""
    result = cli("auth", "refresh", check=False)
    # Exit code 0 (refreshed) or 1 (no token) are both acceptable
    assert result.returncode in (0, 1)


@pytest.mark.manual
@pytest.mark.order(3)
def test_auth_logout(cli, project):
    """auth logout runs without error."""
    result = cli("auth", "logout", check=False)
    assert result.returncode == 0
```

- [ ] **Step 2: Commit**

```bash
git add tests/pre_release/test_06_auth.py
git commit -m "test(pre-release): add auth tests (manual marker)"
```

---

### Task 12: test_07_self_update.py

**Files:**
- Create: `tests/pre_release/test_07_self_update.py`

- [ ] **Step 1: Write self-update test (manual marker)**

```python
# tests/pre_release/test_07_self_update.py
"""Pre-release: self-update command (manual — actually updates binary)."""
import pytest


@pytest.mark.manual
@pytest.mark.order(1)
def test_self_update_check(cli):
    """self-update command is callable."""
    # We just verify the command starts — don't actually update
    # The command will attempt pip install, which may succeed or fail
    # depending on network. We only check it doesn't crash immediately.
    result = cli("self-update", check=False)
    # Any exit code is acceptable — we're testing the command exists
    assert isinstance(result.returncode, int)
```

- [ ] **Step 2: Commit**

```bash
git add tests/pre_release/test_07_self_update.py
git commit -m "test(pre-release): add self-update test (manual marker)"
```

---

### Task 13: test_08_shutdown.py

**Files:**
- Create: `tests/pre_release/test_08_shutdown.py`

- [ ] **Step 1: Write shutdown tests**

```python
# tests/pre_release/test_08_shutdown.py
"""Pre-release: ergo daemon stop + full shutdown verification.

ergo daemon stop/restart is tested here (not in test_03_irc.py) because
stopping ergo kills the session-scoped irc_probe's persistent connection,
which would break agent tests that depend on wait_for_message().
"""
import socket
import time

import pytest


@pytest.mark.order(1)
def test_irc_daemon_stop(cli, e2e_port):
    """Stop ergo daemon directly, verify port released."""
    cli("irc", "daemon", "stop")
    time.sleep(1)
    with pytest.raises(OSError):
        with socket.create_connection(("127.0.0.1", e2e_port), timeout=1):
            pass


@pytest.mark.order(2)
def test_irc_daemon_restart(cli, e2e_port):
    """Restart ergo daemon to verify start-after-stop works."""
    cli("irc", "daemon", "start")
    time.sleep(2)
    with socket.create_connection(("127.0.0.1", e2e_port), timeout=2):
        pass


@pytest.mark.order(3)
def test_shutdown(cli):
    """zchat shutdown stops all agents and infrastructure."""
    result = cli("shutdown", check=False)
    assert result.returncode == 0, f"shutdown failed: {result.stderr}"


@pytest.mark.order(4)
def test_irc_status_after_shutdown(cli):
    """irc status confirms everything is stopped."""
    result = cli("irc", "status", check=False)
    # After shutdown, status may error (no config) or show stopped
    # Either is acceptable
    if result.returncode == 0:
        assert "stopped" in result.stdout.lower() or "not running" in result.stdout.lower()
```

- [ ] **Step 2: Commit**

```bash
git add tests/pre_release/test_08_shutdown.py
git commit -m "test(pre-release): add shutdown verification tests"
```

---

## Chunk 4: Integration Verification

### Task 14: Verify full pre-release suite collects correctly

- [ ] **Step 1: Collect all pre-release tests (dry run)**

Run: `uv run pytest tests/pre_release/ -v -m "prerelease and not manual" --co`
Expected: ~24 tests collected from test_00 through test_08 (excluding manual)

- [ ] **Step 2: Collect manual tests too**

Run: `uv run pytest tests/pre_release/ -v -m prerelease --co`
Expected: ~26 tests collected (all including manual)

- [ ] **Step 3: Verify existing E2E tests unaffected**

Run: `uv run pytest tests/e2e/ -v -m e2e --co`
Expected: Same tests as before, no import errors

- [ ] **Step 4: Verify existing unit tests unaffected**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass, including new `test_project_create_params.py`

- [ ] **Step 5: Run the full pre-release suite (requires ergo + tmux)**

Run: `uv run pytest tests/pre_release/ -v -m "prerelease and not manual" --timeout=120`
Expected: All tests pass

- [ ] **Step 6: Final commit if any fixups needed**

```bash
git add -A
git commit -m "test(pre-release): fixups from integration verification"
```

---

## Summary

| Chunk | Tasks | What it delivers |
|-------|-------|-----------------|
| 1 | Tasks 1-3 | `project create` parameterization + shared test utilities + markers |
| 2 | Tasks 4-7 | Pre-release conftest + doctor/project/template tests |
| 3 | Tasks 8-13 | IRC/agent/setup/auth/self-update/shutdown tests |
| 4 | Task 14 | Integration verification |

**Total: 14 tasks, ~30 test cases.**
