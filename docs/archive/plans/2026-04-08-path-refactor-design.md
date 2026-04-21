# Path Management Refactor — Design

> Date: 2026-04-08
> Status: Approved

## Problem

1. **~130 `os.path` calls scattered across 11 files** — no single source of truth for path resolution
2. **`ZCHAT_DIR` is a module-level constant** (`project.py:9`) set at import time — hard to override in tests, can't react to runtime config changes
3. **Two duplicate `_parse_env_file()` implementations** in `template_loader.py` and `runner.py` — hand-written, doesn't support `export`, quotes, or multiline
4. **No way to override sub-paths** — plugins/templates dirs are hardcoded as `{ZCHAT_HOME}/plugins`, can't relocate

## Solution

### 1. New `zchat/cli/paths.py` module

Single entry point for all path resolution. Uses `pathlib.Path` throughout.

```python
from pathlib import Path

def zchat_home() -> Path:
    """Root path. Priority: $ZCHAT_HOME > ~/.zchat"""

def plugins_dir() -> Path:
    """Priority: $ZCHAT_PLUGINS_DIR > config.toml [paths].plugins > defaults.toml [paths].plugins"""

def templates_dir() -> Path:
    """Priority: $ZCHAT_TEMPLATES_DIR > config.toml [paths].templates > defaults.toml [paths].templates"""

def projects_dir() -> Path:
    """Always {zchat_home}/projects"""

def project_dir(name: str) -> Path: ...
def project_config(name: str) -> Path: ...     # {project}/config.toml
def project_state(name: str) -> Path: ...      # {project}/state.json
def agent_workspace(project: str, agent: str) -> Path: ...
def agent_ready_marker(project: str, agent: str) -> Path: ...
def global_config_path() -> Path: ...          # {home}/config.toml
def auth_file() -> Path: ...                   # {home}/auth.json
def update_state() -> Path: ...                # {home}/update.json
def ergo_data_dir(project: str) -> Path: ...   # {project}/ergo
def weechat_home(project: str) -> Path: ...    # {project}/.weechat
def zellij_layout_dir() -> Path: ...           # {home}/main (Zellij layout storage)
def project_env_file(project: str) -> Path: ... # {project}/claude.local.env
def project_kdl_config(project: str) -> Path: ... # {project}/config.kdl
def legacy_agent_state() -> Path: ...          # ~/.local/state/zchat/agents.json (DEFAULT_STATE_FILE)
```

Resolution priority for overridable paths:

```
env var  >  config.toml [paths]  >  defaults.toml [paths]
```

### 2. `defaults.toml` — new `[paths]` section

```toml
[paths]
plugins = "plugins"
templates = "templates"
projects = "projects"
```

Sub-path names only (relative to `ZCHAT_HOME`). Combined with `zchat_home()` at resolution time.

### 3. `python-dotenv` replaces hand-written parsers

- Add `python-dotenv` to dependencies
- Delete both `_parse_env_file()` implementations (template_loader.py, runner.py)
- Use `dotenv_values(path)` for reading `.env` files as dict (no global side effects)
- Agent `.env` files, template `.env.example` rendering all go through `dotenv_values()`
- Filter `None` values from `dotenv_values()` output (current `_parse_env_file` returns empty string for valueless keys; `dotenv_values` returns `None`)
- Deprecate `auth._global_auth_dir()` — callers use `paths.zchat_home()` or `paths.auth_file()` directly

### 4. Full `os.path` → `pathlib.Path` migration

All 11 CLI files migrate from `os.path.join/isfile/isdir/exists/dirname/expanduser` to `Path` equivalents:

| os.path | pathlib |
|---------|---------|
| `os.path.join(a, b)` | `Path(a) / b` |
| `os.path.isfile(p)` | `Path(p).is_file()` |
| `os.path.isdir(p)` | `Path(p).is_dir()` |
| `os.path.exists(p)` | `Path(p).exists()` |
| `os.path.dirname(p)` | `Path(p).parent` |
| `os.path.expanduser(p)` | `Path(p).expanduser()` |
| `os.path.basename(p)` | `Path(p).name` |
| `os.path.abspath(p)` | `Path(p).resolve()` |
| `os.makedirs(p, exist_ok=True)` | `Path(p).mkdir(parents=True, exist_ok=True)` |

### 5. Environment variables

| Variable | Overrides | Default |
|----------|-----------|---------|
| `ZCHAT_HOME` | Root path | `~/.zchat` |
| `ZCHAT_PLUGINS_DIR` | Plugin WASM directory | `{home}/plugins` |
| `ZCHAT_TEMPLATES_DIR` | User templates | `{home}/templates` |

## Files Changed

| File | Change |
|------|--------|
| `zchat/cli/paths.py` | **New** — centralized path resolution |
| `zchat/cli/data/defaults.toml` | Add `[paths]` section |
| `zchat/cli/project.py` | Delete `ZCHAT_DIR`, use `paths.*`, all `os.path` → `Path` |
| `zchat/cli/config_cmd.py` | Use `paths.global_config_path()`, `Path` migration |
| `zchat/cli/agent_manager.py` | Use `paths.agent_*()`, `Path` migration |
| `zchat/cli/irc_manager.py` | Use `paths.ergo_data_dir()`, `paths.weechat_home()`, `Path` migration |
| `zchat/cli/auth.py` | Use `paths.auth_file()`, `Path` migration |
| `zchat/cli/update.py` | Use `paths.update_state()`, `Path` migration |
| `zchat/cli/template_loader.py` | Use `paths.templates_dir()`, delete `_parse_env_file`, use `dotenv_values`, `Path` migration |
| `zchat/cli/runner.py` | Delete `_parse_env_file`, use `dotenv_values`, `Path` migration |
| `zchat/cli/doctor.py` | `Path` migration for weechat discovery |
| `zchat/cli/app.py` | Use paths module, `Path` migration |
| `zchat/cli/defaults.py` | `Path` for data file loading |
| `zchat/cli/ergo_auth_script.py` | `Path` migration |
| `zchat/cli/migrate.py` | `Path` migration (6 `os.path` calls) |
| `zchat/cli/layout.py` | Use `paths.plugins_dir()`, `Path` migration |
| `zchat/cli/zellij.py` | `Path` migration if applicable |
| `pyproject.toml` | Add `python-dotenv` dependency |
| `tests/unit/test_paths.py` | **New** — tests for paths.py |
| `tests/unit/test_*.py` | `monkeypatch ZCHAT_DIR` → mock `paths.zchat_home` |
| `tests/e2e/conftest.py` | Path construction uses `Path` |

## Not in scope

- XDG directory splitting (config/data/state stay under single `ZCHAT_HOME`)
- Directory structure changes (only how code references paths)
- `load_dotenv()` global injection (only `dotenv_values()` for reading files)
