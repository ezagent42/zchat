"""Runner module: merges global config [runners.X] with template directory assets.

A *runner* is the combination of:
  - Global config entry ``[runners.<name>]`` (command, args, env overrides)
  - Template directory files (start.sh, .env.example, soul.md, template.toml)

When the global config has no ``[runners]`` section the module falls back to
the template_loader behaviour so that existing setups keep working.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from dotenv import dotenv_values

from zchat.cli import paths

_BUILTIN_DIR = Path(__file__).parent / "templates"


class RunnerNotFoundError(Exception):
    pass


# ---------------------------------------------------------------------------
# Internal helpers (shared with / ported from template_loader)
# ---------------------------------------------------------------------------

def _parse_env_file(path: str) -> dict[str, str]:
    """Parse a .env file into a dict. Skips comments and blank lines."""
    if not Path(path).is_file():
        return {}
    return {k: v for k, v in dotenv_values(path).items() if v is not None}


def _resolve_template_dir(name: str, user_template_dirs: list[str] | None = None) -> str | None:
    """Resolve a template directory by name.  Returns *None* when not found."""
    # Check extra user dirs first
    if user_template_dirs:
        for base in user_template_dirs:
            candidate = Path(base) / name
            if candidate.is_dir() and (candidate / "template.toml").is_file():
                return str(candidate)

    # Default user dir
    user_dir = paths.templates_dir() / name
    if user_dir.is_dir() and (user_dir / "template.toml").is_file():
        return str(user_dir)

    # Built-in
    builtin = _BUILTIN_DIR / name
    if builtin.is_dir() and (builtin / "template.toml").is_file():
        return str(builtin)

    return None


def _load_template_toml(template_dir: str) -> dict:
    """Load template.toml from a directory."""
    toml_path = Path(template_dir) / "template.toml"
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    data.setdefault("hooks", {})
    data["hooks"].setdefault("pre_stop", "")
    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_env(template_dir_or_name: str, context: dict) -> dict[str, str]:
    """Render .env.example with *context*, overlay .env user overrides.

    *template_dir_or_name* can be either an absolute directory path or a
    template name (resolved via ``_resolve_template_dir``).
    """
    tpl_path = Path(template_dir_or_name)
    if tpl_path.is_dir():
        tpl_dir = template_dir_or_name
        name = tpl_path.name
    else:
        name = template_dir_or_name
        resolved = _resolve_template_dir(name)
        if resolved is None:
            raise RunnerNotFoundError(f"Template '{name}' not found")
        tpl_dir = resolved
        tpl_path = Path(tpl_dir)

    example = _parse_env_file(str(tpl_path / ".env.example"))
    rendered: dict[str, str] = {}
    placeholder_re = re.compile(r"\{\{(\w+)\}\}")
    for key, value in example.items():
        rendered[key] = placeholder_re.sub(
            lambda m: str(context.get(m.group(1), "")), value
        )

    # Overlay .env from template dir
    user_env = _parse_env_file(str(tpl_path / ".env"))
    # Also check user-scoped dir (for built-in templates)
    user_dir = paths.templates_dir() / name
    if str(user_dir) != tpl_dir:
        user_env.update(_parse_env_file(str(user_dir / ".env")))
    rendered.update(user_env)

    return rendered
