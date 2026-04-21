# Agent Template System Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded Claude Code agent creation with a template-based system that supports arbitrary agent types.

**Architecture:** Templates are directories (`~/.zchat/templates/{name}/`) containing `template.toml`, `start.sh`, `.env.example`, and optional `.env`. A `template_loader.py` module resolves and renders templates. `AgentManager` delegates all agent-type-specific logic to templates. Built-in `claude` template ships as package data.

**Tech Stack:** Python 3.11+, tomllib (read), tomli-w (write), hatchling (packaging), typer (CLI)

**Spec:** `docs/superpowers/specs/2026-03-29-agent-template-system-design.md`

---

## Chunk 1: Template Loader and Built-in Template

### Task 1: Create template_loader.py with resolve_template_dir()

**Files:**
- Create: `zchat/cli/template_loader.py`
- Test: `tests/unit/test_template_loader.py`

- [ ] **Step 1: Write failing test for resolve_template_dir**

```python
# tests/unit/test_template_loader.py
import os
import pytest
from zchat.cli.template_loader import resolve_template_dir, TemplateNotFoundError


def test_resolve_user_template(tmp_path, monkeypatch):
    """User template dir takes priority over built-in."""
    monkeypatch.setattr("zchat.cli.template_loader.ZCHAT_DIR", str(tmp_path))
    user_tpl = tmp_path / "templates" / "my-bot"
    user_tpl.mkdir(parents=True)
    (user_tpl / "template.toml").write_text('[template]\nname = "my-bot"\n')
    assert resolve_template_dir("my-bot") == str(user_tpl)


def test_resolve_builtin_template(tmp_path, monkeypatch):
    """Falls back to built-in template."""
    monkeypatch.setattr("zchat.cli.template_loader.ZCHAT_DIR", str(tmp_path))
    result = resolve_template_dir("claude")
    assert "templates/claude" in result
    assert os.path.isfile(os.path.join(result, "template.toml"))


def test_resolve_unknown_template_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.template_loader.ZCHAT_DIR", str(tmp_path))
    with pytest.raises(TemplateNotFoundError):
        resolve_template_dir("nonexistent")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_template_loader.py -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_template_dir'`

- [ ] **Step 3: Implement resolve_template_dir**

```python
# zchat/cli/template_loader.py
"""Template loading: resolve, load, render environment variables."""

import os
from pathlib import Path

from zchat.cli.project import ZCHAT_DIR

_BUILTIN_DIR = Path(__file__).parent / "templates"


class TemplateNotFoundError(Exception):
    pass


def resolve_template_dir(name: str) -> str:
    """Resolve template directory. User dir takes priority over built-in."""
    user_dir = os.path.join(ZCHAT_DIR, "templates", name)
    if os.path.isdir(user_dir) and os.path.isfile(os.path.join(user_dir, "template.toml")):
        return user_dir
    builtin = _BUILTIN_DIR / name
    if builtin.is_dir() and (builtin / "template.toml").is_file():
        return str(builtin)
    raise TemplateNotFoundError(f"Template '{name}' not found")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_template_loader.py -v`
Expected: PASS (builtin test will fail until Task 2 creates the claude template files)

- [ ] **Step 5: Commit**

```bash
git add zchat/cli/template_loader.py tests/unit/test_template_loader.py
git commit -m "feat: add template_loader with resolve_template_dir"
```

### Task 2: Create built-in claude template files

**Files:**
- Create: `zchat/cli/templates/claude/template.toml`
- Create: `zchat/cli/templates/claude/start.sh`
- Create: `zchat/cli/templates/claude/.env.example`

- [ ] **Step 1: Create the claude template directory and files**

`zchat/cli/templates/claude/template.toml`:
```toml
[template]
name = "claude"
description = "Claude Code agent with MCP channel server"

[hooks]
pre_stop = "/exit"
```

`zchat/cli/templates/claude/.env.example`:
```bash
# Auto-injected by zchat
AGENT_NAME={{agent_name}}
IRC_SERVER={{irc_server}}
IRC_PORT={{irc_port}}
IRC_CHANNELS={{irc_channels}}
IRC_TLS={{irc_tls}}
IRC_PASSWORD={{irc_password}}
WORKSPACE={{workspace}}

# User configuration
ANTHROPIC_API_KEY=

# MCP server command — override for dev (e.g., "uv run --project /path zchat-channel")
MCP_SERVER_CMD=zchat-channel
```

`zchat/cli/templates/claude/start.sh`:
```bash
#!/bin/bash
set -euo pipefail

# Parse MCP server command (first word = command, rest = args)
read -ra MCP_PARTS <<< "$MCP_SERVER_CMD"
MCP_CMD="${MCP_PARTS[0]}"
MCP_ARGS=("${MCP_PARTS[@]:1}")

mkdir -p .claude
cat > .claude/settings.local.json << 'EOF'
{
  "permissions": {
    "allow": [
      "mcp__zchat-channel__reply",
      "mcp__zchat-channel__join_channel"
    ]
  }
}
EOF

# Build .mcp.json
if [ ${#MCP_ARGS[@]} -gt 0 ]; then
  ARGS_JSON=$(printf '%s\n' "${MCP_ARGS[@]}" | jq -R . | jq -s .)
  ARGS_LINE="\"args\": $ARGS_JSON,"
else
  ARGS_LINE=""
fi

cat > .mcp.json << EOF
{
  "mcpServers": {
    "zchat-channel": {
      "command": "$MCP_CMD",
      ${ARGS_LINE}
      "env": {
        "AGENT_NAME": "$AGENT_NAME",
        "IRC_SERVER": "$IRC_SERVER",
        "IRC_PORT": "$IRC_PORT",
        "IRC_CHANNELS": "$IRC_CHANNELS",
        "IRC_TLS": "$IRC_TLS"
      }
    }
  }
}
EOF

exec claude --permission-mode bypassPermissions \
  --dangerously-load-development-channels server:zchat-channel
```

- [ ] **Step 2: Verify built-in resolve test now passes**

Run: `uv run pytest tests/unit/test_template_loader.py::test_resolve_builtin_template -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add zchat/cli/templates/
git commit -m "feat: add built-in claude template (template.toml, start.sh, .env.example)"
```

### Task 3: Add load_template() and render_env()

**Files:**
- Modify: `zchat/cli/template_loader.py`
- Test: `tests/unit/test_template_loader.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_template_loader.py`:

```python
from zchat.cli.template_loader import load_template, render_env


def test_load_template_returns_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.template_loader.ZCHAT_DIR", str(tmp_path))
    tpl_dir = tmp_path / "templates" / "test-tpl"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "template.toml").write_text(
        '[template]\nname = "test-tpl"\ndescription = "Test"\n\n[hooks]\npre_stop = "quit"\n'
    )
    (tpl_dir / ".env.example").write_text("FOO={{agent_name}}\nBAR=fixed\n")
    tpl = load_template("test-tpl")
    assert tpl["template"]["name"] == "test-tpl"
    assert tpl["hooks"]["pre_stop"] == "quit"


def test_render_env_replaces_placeholders(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.template_loader.ZCHAT_DIR", str(tmp_path))
    tpl_dir = tmp_path / "templates" / "test-tpl"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "template.toml").write_text('[template]\nname = "test-tpl"\n')
    (tpl_dir / ".env.example").write_text(
        "AGENT_NAME={{agent_name}}\nIRC_SERVER={{irc_server}}\nFIXED=hello\n"
    )
    context = {"agent_name": "alice-bot", "irc_server": "10.0.0.1"}
    env = render_env("test-tpl", context)
    assert env["AGENT_NAME"] == "alice-bot"
    assert env["IRC_SERVER"] == "10.0.0.1"
    assert env["FIXED"] == "hello"


def test_render_env_dot_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.template_loader.ZCHAT_DIR", str(tmp_path))
    tpl_dir = tmp_path / "templates" / "test-tpl"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "template.toml").write_text('[template]\nname = "test-tpl"\n')
    (tpl_dir / ".env.example").write_text("API_KEY=\nFOO=default\n")
    (tpl_dir / ".env").write_text("API_KEY=sk-secret\n")
    context = {}
    env = render_env("test-tpl", context)
    assert env["API_KEY"] == "sk-secret"
    assert env["FOO"] == "default"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_template_loader.py -v -k "load_template or render_env"`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement load_template and render_env**

Add to `zchat/cli/template_loader.py`:

```python
import re
import tomllib


def _parse_env_file(path: str) -> dict[str, str]:
    """Parse a .env file into a dict. Skips comments and blank lines."""
    env = {}
    if not os.path.isfile(path):
        return env
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def load_template(name: str) -> dict:
    """Load template.toml metadata. Returns dict with 'template' and 'hooks' keys."""
    tpl_dir = resolve_template_dir(name)
    toml_path = os.path.join(tpl_dir, "template.toml")
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    data.setdefault("hooks", {})
    data["hooks"].setdefault("pre_stop", "")
    return data


def render_env(name: str, context: dict) -> dict[str, str]:
    """Render .env.example with context, overlay .env. Returns merged env dict.

    context keys: agent_name, irc_server, irc_port, irc_channels, irc_tls,
                  irc_password, workspace
    """
    tpl_dir = resolve_template_dir(name)

    # 1. Parse .env.example and render {{placeholders}}
    example = _parse_env_file(os.path.join(tpl_dir, ".env.example"))
    rendered = {}
    placeholder_re = re.compile(r"\{\{(\w+)\}\}")
    for key, value in example.items():
        rendered[key] = placeholder_re.sub(
            lambda m: str(context.get(m.group(1), "")), value
        )

    # 2. Overlay .env (user overrides) — check both template dir and user dir
    user_env = _parse_env_file(os.path.join(tpl_dir, ".env"))
    # Also check user-scoped .env (for built-in templates where .env is in ~/.zchat/templates/)
    user_dir = os.path.join(ZCHAT_DIR, "templates", name)
    if user_dir != tpl_dir:
        user_env.update(_parse_env_file(os.path.join(user_dir, ".env")))
    rendered.update(user_env)

    return rendered


def get_start_script(name: str) -> str:
    """Return absolute path to template's start.sh."""
    tpl_dir = resolve_template_dir(name)
    script = os.path.join(tpl_dir, "start.sh")
    if not os.path.isfile(script):
        raise FileNotFoundError(f"start.sh not found in template '{name}'")
    return script


def list_templates() -> list[dict]:
    """List all available templates (user + built-in, deduplicated)."""
    seen = set()
    templates = []

    # User templates first
    user_dir = os.path.join(ZCHAT_DIR, "templates")
    if os.path.isdir(user_dir):
        for name in sorted(os.listdir(user_dir)):
            toml_path = os.path.join(user_dir, name, "template.toml")
            if os.path.isfile(toml_path):
                tpl = load_template(name)
                tpl["source"] = "user"
                templates.append(tpl)
                seen.add(name)

    # Built-in templates (skip if user has override)
    if _BUILTIN_DIR.is_dir():
        for entry in sorted(_BUILTIN_DIR.iterdir()):
            if entry.is_dir() and (entry / "template.toml").is_file():
                name = entry.name
                if name not in seen:
                    tpl = load_template(name)
                    tpl["source"] = "builtin"
                    templates.append(tpl)

    return templates
```

- [ ] **Step 4: Run all template_loader tests**

Run: `uv run pytest tests/unit/test_template_loader.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add zchat/cli/template_loader.py tests/unit/test_template_loader.py
git commit -m "feat: add load_template, render_env, list_templates to template_loader"
```

### Task 4: Add list_templates test

**Files:**
- Test: `tests/unit/test_template_loader.py`

- [ ] **Step 1: Write test for list_templates**

Append to `tests/unit/test_template_loader.py`:

```python
from zchat.cli.template_loader import list_templates


def test_list_templates_includes_builtin(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.template_loader.ZCHAT_DIR", str(tmp_path))
    templates = list_templates()
    names = [t["template"]["name"] for t in templates]
    assert "claude" in names


def test_list_templates_user_overrides_builtin(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.template_loader.ZCHAT_DIR", str(tmp_path))
    user_tpl = tmp_path / "templates" / "claude"
    user_tpl.mkdir(parents=True)
    (user_tpl / "template.toml").write_text(
        '[template]\nname = "claude"\ndescription = "Custom claude"\n'
    )
    templates = list_templates()
    claude = [t for t in templates if t["template"]["name"] == "claude"]
    assert len(claude) == 1
    assert claude[0]["source"] == "user"
    assert claude[0]["template"]["description"] == "Custom claude"
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/test_template_loader.py -v -k "list_templates"`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_template_loader.py
git commit -m "test: add list_templates tests"
```

---

## Chunk 2: Refactor AgentManager to Use Templates

### Task 5: Add tomli-w dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add tomli-w to dependencies**

In `pyproject.toml`, add `"tomli-w>=1.0.0"` to `dependencies`.

- [ ] **Step 2: Install**

Run: `uv sync`
Expected: tomli-w installed

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add tomli-w for TOML writing"
```

### Task 6: Update config.toml to use default_type instead of claude_args

**Files:**
- Modify: `zchat/cli/project.py:21-52` (create_project_config)
- Modify: `zchat/cli/project.py:89-109` (load_project_config)
- Modify: `tests/unit/test_project.py`

- [ ] **Step 1: Write failing test for new config format**

Replace relevant tests in `tests/unit/test_project.py`:

```python
def test_config_has_default_type(tmp_path, monkeypatch):
    """config.toml should have default_type instead of claude_args."""
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("test", server="127.0.0.1", port=6667, tls=False,
                          password="", nick="alice", channels="#general")
    cfg = load_project_config("test")
    assert cfg["agents"]["default_type"] == "claude"
    assert "claude_args" not in cfg["agents"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_project.py::test_config_has_default_type -v`
Expected: FAIL

- [ ] **Step 3: Update create_project_config**

In `zchat/cli/project.py`, modify `create_project_config` signature and body:

```python
def create_project_config(name: str, server: str, port: int, tls: bool,
                          password: str, nick: str, channels: str,
                          env_file: str = "", default_type: str = "claude"):
    """Create project directory and write config.toml."""
    pdir = project_dir(name)
    os.makedirs(pdir, exist_ok=True)
    channels_list = [ch.strip() for ch in channels.split(",") if ch.strip()]
    channels_toml = ", ".join(f'"{ch}"' for ch in channels_list)
    tmux_session = _generate_tmux_session_name(name)
    config_content = f'''[irc]
server = "{server}"
port = {port}
tls = {"true" if tls else "false"}
password = "{password}"

[agents]
default_type = "{default_type}"
default_channels = [{channels_toml}]
username = "{nick}"
env_file = "{env_file}"

[tmux]
session = "{tmux_session}"
'''
    with open(os.path.join(pdir, "config.toml"), "w") as f:
        f.write(config_content)
```

- [ ] **Step 4: Update load_project_config**

In `zchat/cli/project.py`, update `load_project_config`:

```python
def load_project_config(name: str) -> dict:
    """Load and validate project config.toml."""
    config_path = os.path.join(project_dir(name), "config.toml")
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)
    irc = cfg.setdefault("irc", {})
    irc.setdefault("server", "127.0.0.1")
    irc.setdefault("port", 6667)
    irc.setdefault("tls", False)
    irc.setdefault("password", "")
    agents = cfg.setdefault("agents", {})
    agents.setdefault("default_type", "claude")
    agents.setdefault("default_channels", ["#general"])
    if not agents.get("username"):
        agents["username"] = os.environ.get("USER", "user")
    agents.setdefault("env_file", "")
    return cfg
```

- [ ] **Step 5: Update existing test_project.py tests**

Remove `test_config_has_agent_launch_fields` and `test_config_defaults_without_agent_launch_fields`. Update `test_create_project_config` to remove `claude_args` references. Remove the `claude_args` parameter from all `create_project_config` calls in tests.

- [ ] **Step 6: Run all project tests**

Run: `uv run pytest tests/unit/test_project.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add zchat/cli/project.py tests/unit/test_project.py
git commit -m "refactor: replace claude_args/mcp_server_cmd with default_type in config"
```

### Task 7: Refactor AgentManager to use templates

**Files:**
- Modify: `zchat/cli/agent_manager.py`
- Modify: `tests/unit/test_agent_manager.py`

This is the core refactor. `AgentManager` removes `claude_args`, `mcp_server_cmd`, and `_write_workspace_config`. Instead, it calls `template_loader` functions.

- [ ] **Step 1: Write failing tests for template-based create**

Replace `tests/unit/test_agent_manager.py`:

```python
import os
import json
import tempfile

from zchat.cli.agent_manager import AgentManager


def _make_manager(state_file="/tmp/test-agents.json", env_file=""):
    return AgentManager(
        irc_server="localhost", irc_port=6667, irc_tls=False,
        irc_password="",
        username="alice", default_channels=["#general"],
        env_file=env_file,
        default_type="claude",
        state_file=state_file,
    )


def test_scope_agent_name():
    mgr = _make_manager()
    assert mgr.scoped("helper") == "alice-helper"
    assert mgr.scoped("alice-helper") == "alice-helper"


def test_create_workspace_exists():
    """create_workspace should create a directory."""
    mgr = _make_manager(state_file="/tmp/test-agents-ws2.json")
    ws = mgr._create_workspace("alice-helper")
    assert os.path.isdir(ws)
    import shutil
    shutil.rmtree(ws)


def test_build_env_context():
    """_build_env_context renders all required placeholders."""
    mgr = _make_manager()
    ctx = mgr._build_env_context("alice-bot", "/tmp/ws", ["#general", "#dev"])
    assert ctx["agent_name"] == "alice-bot"
    assert ctx["irc_server"] == "localhost"
    assert ctx["irc_port"] == "6667"
    assert ctx["irc_channels"] == "general,dev"
    assert ctx["irc_tls"] == "false"
    assert ctx["workspace"] == "/tmp/ws"


def test_agent_state_persistence(tmp_path):
    state_file = str(tmp_path / "agents.json")
    mgr = _make_manager(state_file=state_file)
    mgr._agents["alice-helper"] = {
        "type": "claude",
        "workspace": "/tmp/x", "pane_id": "%42", "status": "running",
        "created_at": 0, "channels": ["#general"],
    }
    mgr._save_state()
    mgr2 = _make_manager(state_file=state_file)
    assert "alice-helper" in mgr2._agents
    assert mgr2._agents["alice-helper"]["type"] == "claude"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_agent_manager.py -v`
Expected: FAIL — `AgentManager` doesn't accept `default_type`

- [ ] **Step 3: Refactor AgentManager**

Rewrite `zchat/cli/agent_manager.py`:

```python
"""Agent lifecycle management: create workspace, spawn tmux, track state."""

import json
import os
import shutil
import subprocess
import tempfile
import time

import libtmux

from zchat.cli.tmux import get_or_create_session, find_pane, pane_alive
from zchat.cli.template_loader import load_template, render_env, get_start_script
from zchat_protocol.naming import scoped_name, AGENT_SEPARATOR


DEFAULT_STATE_FILE = os.path.expanduser("~/.local/state/zchat/agents.json")


class AgentManager:
    def __init__(self, irc_server: str, irc_port: int, irc_tls: bool,
                 irc_password: str,
                 username: str, default_channels: list[str],
                 env_file: str = "",
                 default_type: str = "claude",
                 tmux_session: str = "zchat",
                 state_file: str = DEFAULT_STATE_FILE):
        self.irc_server = irc_server
        self.irc_port = irc_port
        self.irc_tls = irc_tls
        self.irc_password = irc_password
        self.username = username
        self.default_channels = default_channels
        self.env_file = env_file
        self.default_type = default_type
        self._tmux_session_name = tmux_session
        self._tmux_session: libtmux.Session | None = None
        self._state_file = state_file
        self._agents: dict[str, dict] = {}
        self._load_state()

    @property
    def tmux_session(self) -> libtmux.Session:
        if self._tmux_session is None:
            self._tmux_session = get_or_create_session(self._tmux_session_name)
        return self._tmux_session

    def scoped(self, name: str) -> str:
        return scoped_name(name, self.username)

    def create(self, name: str, workspace: str | None = None,
               channels: list[str] | None = None,
               agent_type: str | None = None) -> dict:
        """Create and launch a new agent. Returns agent info dict."""
        name = self.scoped(name)
        if name in self._agents and self._agents[name].get("status") == "running":
            raise ValueError(f"{name} already exists and is running")

        agent_type = agent_type or self.default_type
        channels = channels or list(self.default_channels)
        agent_workspace = workspace or self._create_workspace(name)

        pane_id = self._spawn_tmux(name, agent_workspace, agent_type, channels)

        self._agents[name] = {
            "type": agent_type,
            "workspace": agent_workspace,
            "pane_id": pane_id,
            "status": "starting",
            "created_at": time.time(),
            "channels": channels,
        }
        self._save_state()
        return self._agents[name]

    def stop(self, name: str, force: bool = False):
        """Stop an agent."""
        name = self.scoped(name)
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        if agent["status"] == "offline":
            raise ValueError(f"{name} is already offline")
        self._force_stop(name)
        agent["status"] = "offline"
        self._cleanup_workspace(name)
        self._save_state()

    def restart(self, name: str):
        """Stop then re-create with same config."""
        name = self.scoped(name)
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        channels = list(agent.get("channels", self.default_channels))
        agent_type = agent.get("type", self.default_type)
        self.stop(name)
        base_name = name.split(AGENT_SEPARATOR, 1)[-1] if AGENT_SEPARATOR in name else name
        self.create(base_name, channels=channels, agent_type=agent_type)

    def list_agents(self) -> dict[str, dict]:
        """Return all agents with refreshed status."""
        for name, info in self._agents.items():
            if info.get("status") != "offline":
                info["status"] = self._check_alive(name)
        self._save_state()
        return dict(self._agents)

    def get_status(self, name: str) -> dict:
        name = self.scoped(name)
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        if agent["status"] != "offline":
            agent["status"] = self._check_alive(name)
        return agent

    def _create_workspace(self, name: str) -> str:
        safe = name.replace(AGENT_SEPARATOR, "_")
        workspace = os.path.join(tempfile.gettempdir(), f"zchat-{safe}")
        os.makedirs(workspace, exist_ok=True)
        return workspace

    def _build_env_context(self, name: str, workspace: str, channels: list[str]) -> dict:
        """Build the context dict for template placeholder rendering."""
        channels_str = ",".join(ch.lstrip("#") for ch in channels)
        return {
            "agent_name": name,
            "irc_server": self.irc_server,
            "irc_port": str(self.irc_port),
            "irc_channels": channels_str,
            "irc_tls": str(self.irc_tls).lower(),
            "irc_password": self.irc_password,
            "workspace": workspace,
        }

    def _spawn_tmux(self, name: str, workspace: str, agent_type: str,
                    channels: list[str]) -> str:
        context = self._build_env_context(name, workspace, channels)
        env = render_env(agent_type, context)

        # Overlay project-level env_file (lower priority than template env)
        if self.env_file and os.path.isfile(self.env_file):
            from zchat.cli.template_loader import _parse_env_file
            project_env = _parse_env_file(self.env_file)
            merged = dict(project_env)
            merged.update(env)
            env = merged

        start_script = get_start_script(agent_type)

        # Write env to a temp file to avoid shell quoting issues
        import shlex
        env_file_path = os.path.join(workspace, ".zchat-env")
        with open(env_file_path, "w") as f:
            for k, v in env.items():
                f.write(f"export {k}={shlex.quote(v)}\n")

        cmd = f"cd '{workspace}' && source .zchat-env && bash '{start_script}'"

        window = self.tmux_session.active_window
        pane = window.split(attach=False, direction=libtmux.constants.PaneDirection.Below, shell=cmd)
        pane_id = pane.pane_id
        pane.cmd("select-pane", "-T", f"agent: {name}")
        # Auto-confirm development channels prompt after 3s (needed for Claude)
        subprocess.Popen(
            ["bash", "-c", f"sleep 3 && tmux send-keys -t {pane_id} Enter"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return pane_id

    def _force_stop(self, name: str):
        agent = self._agents.get(name)
        if not agent or not agent.get("pane_id"):
            return
        pane = find_pane(self.tmux_session, agent["pane_id"])
        if not pane:
            return

        agent_type = agent.get("type", self.default_type)
        try:
            tpl = load_template(agent_type)
            pre_stop = tpl.get("hooks", {}).get("pre_stop", "")
        except Exception:
            pre_stop = ""

        if pre_stop:
            pane.send_keys(pre_stop, enter=True)
            # Poll for up to 5 seconds
            for _ in range(10):
                time.sleep(0.5)
                if not pane_alive(self.tmux_session, agent["pane_id"]):
                    return
        # Kill pane as fallback
        try:
            pane.cmd("kill-pane")
        except Exception:
            pass

    def _cleanup_workspace(self, name: str):
        agent = self._agents.get(name)
        if agent:
            ws = agent.get("workspace", "")
            if ws.startswith(tempfile.gettempdir()):
                shutil.rmtree(ws, ignore_errors=True)

    def _check_alive(self, name: str) -> str:
        agent = self._agents.get(name)
        if not agent or not agent.get("pane_id"):
            return "offline"
        if pane_alive(self.tmux_session, agent["pane_id"]):
            return "running"
        return "offline"

    def send(self, name: str, text: str):
        """Send text to agent's tmux pane."""
        name = self.scoped(name)
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        if self._check_alive(name) != "running":
            raise ValueError(f"{name} is not running")
        pane = find_pane(self.tmux_session, agent["pane_id"])
        if pane:
            pane.send_keys(text, enter=True)

    def _load_state(self):
        if os.path.isfile(self._state_file):
            try:
                with open(self._state_file) as f:
                    data = json.load(f)
                self._agents = data.get("agents", {})
            except (json.JSONDecodeError, OSError):
                self._agents = {}

    def _save_state(self):
        os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
        existing = {}
        if os.path.isfile(self._state_file):
            try:
                with open(self._state_file) as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        existing["agents"] = self._agents
        with open(self._state_file, "w") as f:
            json.dump(existing, f, indent=2)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_agent_manager.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add zchat/cli/agent_manager.py tests/unit/test_agent_manager.py
git commit -m "refactor: AgentManager uses template system instead of hardcoded claude"
```

### Task 8: Update app.py — _get_agent_manager and agent create

**Files:**
- Modify: `zchat/cli/app.py:63-77` (_get_agent_manager)
- Modify: `zchat/cli/app.py:279-294` (cmd_agent_create)
- Modify: `zchat/cli/app.py:103-133` (cmd_project_create)

- [ ] **Step 1: Update _get_agent_manager**

```python
def _get_agent_manager(ctx: typer.Context) -> AgentManager:
    cfg = _get_config(ctx)
    project_name = ctx.obj["project"]
    return AgentManager(
        irc_server=cfg["irc"]["server"],
        irc_port=cfg["irc"]["port"],
        irc_tls=cfg["irc"].get("tls", False),
        irc_password=cfg["irc"].get("password", ""),
        username=cfg["agents"]["username"],
        default_channels=cfg["agents"]["default_channels"],
        env_file=cfg["agents"].get("env_file", ""),
        default_type=cfg["agents"].get("default_type", "claude"),
        tmux_session=_get_tmux_session(ctx),
        state_file=state_file_path(project_name),
    )
```

- [ ] **Step 2: Add --type to cmd_agent_create**

```python
@agent_app.command("create")
def cmd_agent_create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    workspace: Optional[str] = typer.Option(None, help="Custom workspace path"),
    channels: Optional[str] = typer.Option(None, help="Comma-separated channels to join"),
    agent_type: Optional[str] = typer.Option(None, "--type", "-t", help="Template type (default: from config)"),
):
    """Create and launch a new agent."""
    mgr = _get_agent_manager(ctx)
    ch = [c.strip() for c in channels.split(",")] if channels else None
    info = mgr.create(name, workspace=workspace, channels=ch, agent_type=agent_type)
    scoped = mgr.scoped(name)
    typer.echo(f"Created {scoped} (type: {info['type']})")
    typer.echo(f"  pane: {info['pane_id']}")
    typer.echo(f"  workspace: {info['workspace']}")
```

- [ ] **Step 3: Update cmd_project_create — remove claude_args parameter**

In `cmd_project_create`, remove the `claude_args` parameter from the `create_project_config` call. The proxy env_file is still generated the same way.

- [ ] **Step 4: Update cmd_project_remove — update AgentManager constructor**

In `cmd_project_remove` (line 179-185), update the `AgentManager` instantiation to remove `claude_args` and use new signature.

- [ ] **Step 5: Run all unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add zchat/cli/app.py
git commit -m "refactor: app.py uses template-based AgentManager, add --type to agent create"
```

### Task 9: Include templates in package build

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add package data configuration for hatchling**

Add to `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["zchat"]

[tool.hatch.build.targets.wheel.force-include]
"zchat/cli/templates" = "zchat/cli/templates"
```

- [ ] **Step 2: Verify template files are included**

Run: `uv build && unzip -l dist/zchat-*.whl | grep templates`
Expected: `zchat/cli/templates/claude/template.toml`, `start.sh`, `.env.example` listed

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: include template files in wheel package"
```

---

## Chunk 3: New CLI Commands (set, template)

### Task 10: Add zchat set command

**Files:**
- Modify: `zchat/cli/app.py`
- Modify: `zchat/cli/project.py`

- [ ] **Step 1: Add set_config_value to project.py**

```python
# In zchat/cli/project.py, add import
import tomli_w

def set_config_value(name: str, key: str, value: str):
    """Set a dotted key in project config.toml. e.g., 'agents.default_type' = 'codex'."""
    config_path = os.path.join(project_dir(name), "config.toml")
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)

    # Navigate dotted key
    parts = key.split(".")
    target = cfg
    for part in parts[:-1]:
        target = target.setdefault(part, {})

    # Type coercion: try int, bool, then string
    if value.lower() in ("true", "false"):
        value = value.lower() == "true"
    else:
        try:
            value = int(value)
        except ValueError:
            pass
    target[parts[-1]] = value

    with open(config_path, "wb") as f:
        tomli_w.dump(cfg, f)
```

- [ ] **Step 2: Write test for set_config_value**

```python
# In tests/unit/test_project.py
from zchat.cli.project import set_config_value

def test_set_config_value(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    create_project_config("test-set", server="127.0.0.1", port=6667,
                          tls=False, password="", nick="alice", channels="#general")
    set_config_value("test-set", "agents.default_type", "codex")
    cfg = load_project_config("test-set")
    assert cfg["agents"]["default_type"] == "codex"
```

- [ ] **Step 3: Add CLI command in app.py**

```python
@app.command("set")
def cmd_set(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Config key (dotted, e.g. agents.default_type)"),
    value: str = typer.Argument(..., help="Value to set"),
):
    """Set a project config value."""
    from zchat.cli.project import set_config_value
    project_name = ctx.obj.get("project")
    if not project_name:
        typer.echo("Error: No project selected.")
        raise typer.Exit(1)
    set_config_value(project_name, key, value)
    typer.echo(f"Set {key} = {value}")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_project.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add zchat/cli/project.py zchat/cli/app.py tests/unit/test_project.py
git commit -m "feat: add 'zchat set' command for project config"
```

### Task 11: Add zchat template subcommands

**Files:**
- Modify: `zchat/cli/app.py`

- [ ] **Step 1: Add template_app typer group and commands**

Add to `app.py` after other app definitions:

```python
template_app = typer.Typer(help="Agent template management")
app.add_typer(template_app, name="template")


@template_app.command("list")
def cmd_template_list():
    """List available agent templates."""
    from zchat.cli.template_loader import list_templates
    templates = list_templates()
    if not templates:
        typer.echo("No templates found.")
        return
    for tpl in templates:
        name = tpl["template"]["name"]
        desc = tpl["template"].get("description", "")
        source = tpl.get("source", "")
        typer.echo(f"  {name}\t{desc}\t({source})")


@template_app.command("show")
def cmd_template_show(name: str = typer.Argument(..., help="Template name")):
    """Show template details."""
    from zchat.cli.template_loader import load_template, resolve_template_dir
    try:
        tpl = load_template(name)
        tpl_dir = resolve_template_dir(name)
    except Exception as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(1)
    typer.echo(f"Template: {tpl['template']['name']}")
    typer.echo(f"  Description: {tpl['template'].get('description', '')}")
    typer.echo(f"  Location: {tpl_dir}")
    typer.echo(f"  pre_stop: {tpl['hooks'].get('pre_stop', '')!r}")


@template_app.command("set")
def cmd_template_set(
    name: str = typer.Argument(..., help="Template name"),
    key: str = typer.Argument(..., help="Environment variable name"),
    value: str = typer.Argument(..., help="Value"),
):
    """Set a template .env variable."""
    from zchat.cli.template_loader import resolve_template_dir, _parse_env_file
    from zchat.cli.project import ZCHAT_DIR
    try:
        tpl_dir = resolve_template_dir(name)
    except Exception as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(1)
    # If template is built-in (inside package), .env goes to user dir
    user_tpl_dir = os.path.join(ZCHAT_DIR, "templates", name)
    if not tpl_dir.startswith(ZCHAT_DIR):
        os.makedirs(user_tpl_dir, exist_ok=True)
        env_path = os.path.join(user_tpl_dir, ".env")
    else:
        env_path = os.path.join(tpl_dir, ".env")
    env = _parse_env_file(env_path)
    env[key] = value
    with open(env_path, "w") as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")
    typer.echo(f"Set {key} in {name} template .env")


@template_app.command("create")
def cmd_template_create(name: str = typer.Argument(..., help="Template name")):
    """Create an empty template scaffold."""
    from zchat.cli.project import ZCHAT_DIR
    tpl_dir = os.path.join(ZCHAT_DIR, "templates", name)
    if os.path.exists(tpl_dir):
        typer.echo(f"Template '{name}' already exists at {tpl_dir}")
        raise typer.Exit(1)
    os.makedirs(tpl_dir)
    with open(os.path.join(tpl_dir, "template.toml"), "w") as f:
        f.write(f'[template]\nname = "{name}"\ndescription = ""\n\n[hooks]\npre_stop = ""\n')
    with open(os.path.join(tpl_dir, "start.sh"), "w") as f:
        f.write("#!/bin/bash\nset -euo pipefail\nexec echo \"TODO: implement start script\"\n")
    os.chmod(os.path.join(tpl_dir, "start.sh"), 0o755)
    with open(os.path.join(tpl_dir, ".env.example"), "w") as f:
        f.write("# Auto-injected by zchat\nAGENT_NAME={{agent_name}}\nIRC_SERVER={{irc_server}}\n"
                "IRC_PORT={{irc_port}}\nIRC_CHANNELS={{irc_channels}}\nIRC_TLS={{irc_tls}}\n"
                "IRC_PASSWORD={{irc_password}}\nWORKSPACE={{workspace}}\n")
    typer.echo(f"Created template scaffold at {tpl_dir}/")
```

- [ ] **Step 2: Run a quick smoke test**

Run: `uv run zchat template list`
Expected: Shows `claude` template (builtin)

- [ ] **Step 3: Commit**

```bash
git add zchat/cli/app.py
git commit -m "feat: add 'zchat template' subcommands (list, show, set, create)"
```

---

## Chunk 4: Final Integration and Verification

### Task 12: Update agent list to show type

**Files:**
- Modify: `zchat/cli/app.py` (cmd_agent_list, cmd_agent_status)

- [ ] **Step 1: Add type column to agent list**

In `cmd_agent_list`, add `agent_type = info.get("type", "unknown")` and include it in the output line.

In `cmd_agent_status`, add `typer.echo(f"  type:      {info.get('type', 'unknown')}")`.

- [ ] **Step 2: Commit**

```bash
git add zchat/cli/app.py
git commit -m "feat: show agent type in list and status commands"
```

### Task 13: Run full test suite

- [ ] **Step 1: Run all unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 2: Run E2E tests (if ergo + tmux available)**

Run: `uv run pytest tests/e2e/ -v -m e2e`
Expected: All PASS (E2E tests use `zchat agent create` which now goes through template system)

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address issues found during integration testing"
```
