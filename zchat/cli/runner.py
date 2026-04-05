"""Runner module: merges global config [runners.X] with template directory assets.

A *runner* is the combination of:
  - Global config entry ``[runners.<name>]`` (command, args, env overrides)
  - Template directory files (start.sh, .env.example, soul.md, template.toml)

When the global config has no ``[runners]`` section the module falls back to
the template_loader behaviour so that existing setups keep working.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

from zchat.cli.project import ZCHAT_DIR

_BUILTIN_DIR = Path(__file__).parent / "templates"


class RunnerNotFoundError(Exception):
    pass


# ---------------------------------------------------------------------------
# Internal helpers (shared with / ported from template_loader)
# ---------------------------------------------------------------------------

def _parse_env_file(path: str) -> dict[str, str]:
    """Parse a .env file into a dict. Skips comments and blank lines."""
    env: dict[str, str] = {}
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


def _resolve_template_dir(name: str, user_template_dirs: list[str] | None = None) -> str | None:
    """Resolve a template directory by name.  Returns *None* when not found."""
    # Check extra user dirs first
    if user_template_dirs:
        for base in user_template_dirs:
            candidate = os.path.join(base, name)
            if os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "template.toml")):
                return candidate

    # Default user dir
    user_dir = os.path.join(ZCHAT_DIR, "templates", name)
    if os.path.isdir(user_dir) and os.path.isfile(os.path.join(user_dir, "template.toml")):
        return user_dir

    # Built-in
    builtin = _BUILTIN_DIR / name
    if builtin.is_dir() and (builtin / "template.toml").is_file():
        return str(builtin)

    return None


def _load_template_toml(template_dir: str) -> dict:
    """Load template.toml from a directory."""
    toml_path = os.path.join(template_dir, "template.toml")
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    data.setdefault("hooks", {})
    data["hooks"].setdefault("pre_stop", "")
    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_runner(
    name: str,
    global_config: dict,
    user_template_dirs: list[str] | None = None,
) -> dict:
    """Resolve a runner by *name*.

    Merges global config ``runners.<name>`` (if present) with the template
    directory assets.  Returns a dict::

        {
            "name": str,
            "command": str,            # e.g. "claude"
            "args": list[str],
            "template_dir": str|None,
            "start_script": str|None,
            "env_template": str|None,  # path to .env.example
            "hooks": dict,
        }

    Falls back to pure template_loader behaviour when global config has no
    ``runners`` section.
    """
    runners_cfg = global_config.get("runners", {})
    runner_cfg = runners_cfg.get(name, {})

    # Try to find a matching template directory (name may differ from runner name)
    template_name = runner_cfg.get("template", name)
    template_dir = _resolve_template_dir(template_name, user_template_dirs)

    # If neither global config nor template dir exist, error out
    if not runner_cfg and template_dir is None:
        raise RunnerNotFoundError(f"Runner '{name}' not found in global config or templates")

    # Start building result from template if available
    hooks: dict = {}
    if template_dir:
        tpl_data = _load_template_toml(template_dir)
        hooks = tpl_data.get("hooks", {})

    # Global config overrides
    command = runner_cfg.get("command", "claude" if not runner_cfg else "")
    args = runner_cfg.get("args", [])

    # Override hooks from global config if provided
    if "hooks" in runner_cfg:
        hooks.update(runner_cfg["hooks"])

    start_script = None
    env_template = None
    if template_dir:
        ss = os.path.join(template_dir, "start.sh")
        if os.path.isfile(ss):
            start_script = ss
        et = os.path.join(template_dir, ".env.example")
        if os.path.isfile(et):
            env_template = et

    return {
        "name": name,
        "command": command,
        "args": args,
        "template_dir": template_dir,
        "start_script": start_script,
        "env_template": env_template,
        "hooks": hooks,
    }


def render_env(template_dir_or_name: str, context: dict) -> dict[str, str]:
    """Render .env.example with *context*, overlay .env user overrides.

    *template_dir_or_name* can be either an absolute directory path or a
    template name (resolved via ``_resolve_template_dir``).
    """
    if os.path.isdir(template_dir_or_name):
        tpl_dir = template_dir_or_name
        name = os.path.basename(tpl_dir)
    else:
        name = template_dir_or_name
        resolved = _resolve_template_dir(name)
        if resolved is None:
            raise RunnerNotFoundError(f"Template '{name}' not found")
        tpl_dir = resolved

    example = _parse_env_file(os.path.join(tpl_dir, ".env.example"))
    rendered: dict[str, str] = {}
    placeholder_re = re.compile(r"\{\{(\w+)\}\}")
    for key, value in example.items():
        rendered[key] = placeholder_re.sub(
            lambda m: str(context.get(m.group(1), "")), value
        )

    # Overlay .env from template dir
    user_env = _parse_env_file(os.path.join(tpl_dir, ".env"))
    # Also check user-scoped dir (for built-in templates)
    user_dir = os.path.join(ZCHAT_DIR, "templates", name)
    if user_dir != tpl_dir:
        user_env.update(_parse_env_file(os.path.join(user_dir, ".env")))
    rendered.update(user_env)

    return rendered


def list_runners(
    global_config: dict,
    user_template_dirs: list[str] | None = None,
) -> list[dict]:
    """List all available runners (from global config + template directories).

    Each entry has keys: name, source ("config", "user", "builtin"), command.
    """
    seen: set[str] = set()
    runners: list[dict] = []

    # 1. Runners from global config
    for name, cfg in global_config.get("runners", {}).items():
        runners.append({
            "name": name,
            "source": "config",
            "command": cfg.get("command", ""),
        })
        seen.add(name)

    # 2. Extra user template dirs
    if user_template_dirs:
        for base in user_template_dirs:
            if not os.path.isdir(base):
                continue
            for entry in sorted(os.listdir(base)):
                if entry in seen:
                    continue
                toml_path = os.path.join(base, entry, "template.toml")
                if os.path.isfile(toml_path):
                    runners.append({"name": entry, "source": "user", "command": ""})
                    seen.add(entry)

    # 3. Default user templates dir
    user_dir = os.path.join(ZCHAT_DIR, "templates")
    if os.path.isdir(user_dir):
        for entry in sorted(os.listdir(user_dir)):
            if entry in seen:
                continue
            toml_path = os.path.join(user_dir, entry, "template.toml")
            if os.path.isfile(toml_path):
                runners.append({"name": entry, "source": "user", "command": ""})
                seen.add(entry)

    # 4. Built-in templates
    if _BUILTIN_DIR.is_dir():
        for entry in sorted(_BUILTIN_DIR.iterdir()):
            if entry.is_dir() and (entry / "template.toml").is_file():
                name = entry.name
                if name not in seen:
                    runners.append({"name": name, "source": "builtin", "command": ""})
                    seen.add(name)

    return runners
