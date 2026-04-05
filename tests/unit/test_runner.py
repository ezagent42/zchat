"""Tests for runner module."""
from __future__ import annotations

import os
import pytest

from zchat.cli.runner import (
    resolve_runner,
    render_env,
    list_runners,
    RunnerNotFoundError,
    _parse_env_file,
)


@pytest.fixture
def zchat_home(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.runner.ZCHAT_DIR", str(tmp_path))
    return tmp_path


def _make_template(base_dir, name, env_example="", start_sh=True, hooks=None):
    """Helper: create a template directory with template.toml."""
    tpl_dir = os.path.join(base_dir, name)
    os.makedirs(tpl_dir, exist_ok=True)
    hooks_toml = ""
    if hooks:
        hooks_toml = "\n[hooks]\n" + "\n".join(f'{k} = "{v}"' for k, v in hooks.items())
    with open(os.path.join(tpl_dir, "template.toml"), "w") as f:
        f.write(f'[template]\nname = "{name}"\ndescription = "test"\n{hooks_toml}\n')
    if env_example:
        with open(os.path.join(tpl_dir, ".env.example"), "w") as f:
            f.write(env_example)
    if start_sh:
        path = os.path.join(tpl_dir, "start.sh")
        with open(path, "w") as f:
            f.write("#!/bin/bash\necho hello\n")
        os.chmod(path, 0o755)
    return tpl_dir


# --- resolve_runner ---

def test_resolve_runner_from_template(zchat_home):
    """resolve_runner finds a runner by template name when no global config."""
    tpl_dir = _make_template(str(zchat_home / "templates"), "claude",
                             env_example="KEY={{agent_name}}\n",
                             hooks={"pre_stop": "/exit"})
    result = resolve_runner("claude", {}, user_template_dirs=None)
    assert result["name"] == "claude"
    assert result["template_dir"] == tpl_dir
    assert result["start_script"].endswith("start.sh")
    assert result["env_template"].endswith(".env.example")
    assert result["hooks"]["pre_stop"] == "/exit"


def test_resolve_runner_from_global_config(zchat_home):
    """resolve_runner uses global config runners section."""
    _make_template(str(zchat_home / "templates"), "claude")
    global_cfg = {
        "runners": {
            "my-runner": {
                "command": "codex",
                "args": ["--model", "o3"],
                "template": "claude",
            }
        }
    }
    result = resolve_runner("my-runner", global_cfg)
    assert result["command"] == "codex"
    assert result["args"] == ["--model", "o3"]
    assert result["template_dir"] is not None  # resolved from template


def test_resolve_runner_config_only_no_template(zchat_home):
    """Runner defined only in global config (no matching template)."""
    global_cfg = {
        "runners": {
            "custom": {
                "command": "my-agent",
                "args": ["--fast"],
            }
        }
    }
    result = resolve_runner("custom", global_cfg)
    assert result["command"] == "my-agent"
    assert result["args"] == ["--fast"]
    assert result["template_dir"] is None
    assert result["start_script"] is None


def test_resolve_runner_not_found(zchat_home):
    """RunnerNotFoundError when runner doesn't exist anywhere."""
    with pytest.raises(RunnerNotFoundError):
        resolve_runner("nonexistent", {})


def test_resolve_runner_global_hooks_override(zchat_home):
    """Global config hooks override template hooks."""
    _make_template(str(zchat_home / "templates"), "claude",
                   hooks={"pre_stop": "/exit"})
    global_cfg = {
        "runners": {
            "claude": {
                "command": "claude",
                "hooks": {"pre_stop": "/quit"},
            }
        }
    }
    result = resolve_runner("claude", global_cfg)
    assert result["hooks"]["pre_stop"] == "/quit"


def test_resolve_runner_user_template_dirs(zchat_home, tmp_path):
    """User template dirs take priority."""
    extra_dir = str(tmp_path / "extra_templates")
    tpl_dir = _make_template(extra_dir, "special")
    result = resolve_runner("special", {}, user_template_dirs=[extra_dir])
    assert result["template_dir"] == tpl_dir


# --- render_env ---

def test_render_env_by_dir(zchat_home):
    """render_env resolves by directory path and substitutes placeholders."""
    tpl_dir = _make_template(str(zchat_home / "templates"), "claude",
                             env_example="AGENT={{agent_name}}\nSERVER={{irc_server}}\n")
    result = render_env(tpl_dir, {"agent_name": "alice-bot", "irc_server": "irc.local"})
    assert result["AGENT"] == "alice-bot"
    assert result["SERVER"] == "irc.local"


def test_render_env_by_name(zchat_home):
    """render_env resolves by template name."""
    _make_template(str(zchat_home / "templates"), "claude",
                   env_example="X={{workspace}}\n")
    result = render_env("claude", {"workspace": "/tmp/ws"})
    assert result["X"] == "/tmp/ws"


def test_render_env_missing_placeholder(zchat_home):
    """Missing placeholder context key renders as empty string."""
    _make_template(str(zchat_home / "templates"), "claude",
                   env_example="V={{missing_key}}\n")
    result = render_env("claude", {})
    assert result["V"] == ""


def test_render_env_not_found(zchat_home):
    with pytest.raises(RunnerNotFoundError):
        render_env("nope", {})


# --- list_runners ---

def test_list_runners_from_config(zchat_home):
    """list_runners includes runners from global config."""
    global_cfg = {
        "runners": {
            "alpha": {"command": "cmd-a"},
            "beta": {"command": "cmd-b"},
        }
    }
    result = list_runners(global_cfg)
    names = [r["name"] for r in result]
    assert "alpha" in names
    assert "beta" in names
    assert all(r["source"] == "config" for r in result if r["name"] in ("alpha", "beta"))


def test_list_runners_from_templates(zchat_home):
    """list_runners discovers user templates."""
    _make_template(str(zchat_home / "templates"), "my-tpl")
    result = list_runners({})
    names = [r["name"] for r in result]
    assert "my-tpl" in names


def test_list_runners_deduplicates(zchat_home):
    """Config runners take priority; template with same name is not duplicated."""
    _make_template(str(zchat_home / "templates"), "claude")
    global_cfg = {"runners": {"claude": {"command": "claude"}}}
    result = list_runners(global_cfg)
    claude_entries = [r for r in result if r["name"] == "claude"]
    assert len(claude_entries) == 1
    assert claude_entries[0]["source"] == "config"


def test_list_runners_user_template_dirs(zchat_home, tmp_path):
    """Extra user template dirs are included."""
    extra = str(tmp_path / "extra")
    _make_template(extra, "custom-agent")
    result = list_runners({}, user_template_dirs=[extra])
    names = [r["name"] for r in result]
    assert "custom-agent" in names


# --- _parse_env_file ---

def test_parse_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nKEY=value\nFOO=bar\n\nBAZ=qux\n")
    result = _parse_env_file(str(env_file))
    assert result == {"KEY": "value", "FOO": "bar", "BAZ": "qux"}


def test_parse_env_file_missing():
    result = _parse_env_file("/nonexistent/.env")
    assert result == {}
