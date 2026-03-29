"""Template loading: resolve, load, render environment variables."""

import os
import re
import tomllib
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
