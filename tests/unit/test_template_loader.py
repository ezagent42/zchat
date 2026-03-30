import os
import pytest
from zchat.cli.template_loader import resolve_template_dir, TemplateNotFoundError, load_template, render_env, list_templates


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
