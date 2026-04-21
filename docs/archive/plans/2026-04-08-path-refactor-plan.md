# Path Management Refactor — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Centralize all path resolution into `paths.py`, migrate `os.path` → `pathlib.Path`, replace hand-written `.env` parsers with `python-dotenv`.

**Architecture:** New `paths.py` module is the single source of truth. All other files import from it instead of computing paths locally.

**Tech Stack:** Python pathlib, python-dotenv, tomllib

---

### Task 1: Add python-dotenv dependency + defaults.toml [paths]

**Files:**
- Modify: `pyproject.toml`
- Modify: `zchat/cli/data/defaults.toml`

Add `python-dotenv>=1.0` to dependencies. Add `[paths]` section to defaults.toml.

### Task 2: Create `zchat/cli/paths.py`

**Files:**
- Create: `zchat/cli/paths.py`
- Create: `tests/unit/test_paths.py`

Core module with all path accessors. Resolution: env var > config.toml > defaults.toml.

### Task 3: Migrate `project.py`

**Files:**
- Modify: `zchat/cli/project.py`

Delete `ZCHAT_DIR` constant. Replace all `os.path` with `Path`. Import from `paths` module.

### Task 4: Migrate `config_cmd.py`

**Files:**
- Modify: `zchat/cli/config_cmd.py`

Use `paths.global_config_path()`. Migrate `os.path` → `Path`.

### Task 5: Migrate `auth.py`

**Files:**
- Modify: `zchat/cli/auth.py`

Use `paths.auth_file()`. Deprecate `_global_auth_dir()`. Migrate `os.path` → `Path`.

### Task 6: Migrate `agent_manager.py`

**Files:**
- Modify: `zchat/cli/agent_manager.py`

Use `paths.agent_workspace()`, `paths.agent_ready_marker()`. Migrate `os.path` → `Path`.

### Task 7: Migrate `irc_manager.py`

**Files:**
- Modify: `zchat/cli/irc_manager.py`

Use `paths.ergo_data_dir()`, `paths.weechat_home()`. Migrate `os.path` → `Path`.

### Task 8: Migrate `template_loader.py` + `runner.py` (dotenv)

**Files:**
- Modify: `zchat/cli/template_loader.py`
- Modify: `zchat/cli/runner.py`

Delete both `_parse_env_file()`. Replace with `dotenv_values()` + None-filtering. Use `paths.templates_dir()`. Migrate `os.path` → `Path`.

### Task 9: Migrate `app.py`, `doctor.py`, `update.py`, `defaults.py`

**Files:**
- Modify: `zchat/cli/app.py`
- Modify: `zchat/cli/doctor.py`
- Modify: `zchat/cli/update.py`
- Modify: `zchat/cli/defaults.py`

Use paths module. Migrate `os.path` → `Path`.

### Task 10: Migrate `layout.py`, `migrate.py`, `ergo_auth_script.py`

**Files:**
- Modify: `zchat/cli/layout.py`
- Modify: `zchat/cli/migrate.py`
- Modify: `zchat/cli/ergo_auth_script.py`

Use `paths.plugins_dir()` in layout.py. Migrate `os.path` → `Path`.

### Task 11: Update all tests

**Files:**
- Modify: `tests/unit/test_project.py`
- Modify: `tests/unit/test_agent_manager.py`
- Modify: `tests/unit/test_config_cmd.py`
- Modify: `tests/unit/test_auth.py`
- Modify: `tests/unit/test_defaults.py`
- Modify: `tests/unit/test_runner.py`
- Modify: `tests/unit/test_template_loader.py`
- Modify: `tests/e2e/conftest.py`
- Modify: `tests/pre_release/conftest.py`

Change `monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", ...)` → mock `paths.zchat_home`.

### Task 12: Run all tests and verify

Run: `uv run pytest tests/unit/ -v && uv run pytest tests/e2e/test_zellij_lifecycle.py -v -m e2e`
