# zchat Zellij Migration Design

> Date: 2026-04-06
> Status: Approved
> Scope: tmux→Zellij migration + Global Config/Runner refactor + WASM Hub Plugin

## Context

zchat v0.3.x uses tmux (libtmux + tmuxp) for session/window management. The experience is fragmented — users must understand both zchat concepts (project/agent) and tmux concepts (session/window). The startup flow requires multiple CLI commands followed by `tmux attach`.

A Zellij PoC has validated all required primitives:

| tmux primitive | Zellij replacement | Status |
|---|---|---|
| `session.new_window()` | `zellij action new-tab --name <n> -- <cmd>` | Verified |
| `capture-pane` polling + `send-keys` | `zellij subscribe --pane-id <id> --format json` + `send-keys` | Verified |
| `pane.send_keys(text)` | `zellij action paste --pane-id <id> <text>` + `send-keys Enter` | Verified |
| `window_alive()` / `find_window()` | `zellij action list-panes --all --json` | Verified |
| `tmux select-window` | `zellij action go-to-tab-name <n>` | Verified |
| `tmuxp load` (declarative layout) | `zellij --new-session-with-layout <layout.kdl>` | Verified |
| zchat hub (display-popup + fzf) | Custom WASM plugin | To build |

## Design Decisions

1. **Per-project Zellij session** — each project gets its own session (`zchat-local`, `zchat-prod`), started from a generated KDL layout. Project switching = `switch-session` within Zellij.

2. **Custom WASM plugin (zchat-hub)** — floating pane triggered by `Ctrl-K`, shows project list + agent status + create/stop controls. Agent status derived from Zellij `TabUpdate` events (no polling needed).

3. **Three changes shipped together** — Zellij migration, Global Config uplift, and Runner/Agent separation are done in one refactor, but phased with tests at each step.

4. **Vertical Slice approach** — Phase 1 delivers end-to-end agent lifecycle first, then expand horizontally.

## Constraints

- Zellij ≥ 0.44.0 required (`subscribe`, `list-panes --json`, `paste`, `send-keys`)
- `GoToTabName` is CLI-only, cannot be used in keybindings (Zellij issue #3669)
- Zellij KDL does not support per-pane env vars (workaround: `bash -c "source .env && exec cmd"`)
- Zellij rejects nesting (detects `$ZELLIJ` env var) — startup must detect and use `switch-session`
- `--new-session-with-layout` for new sessions (`--layout` has different semantics on existing sessions)
- `list-panes --all --json` pane IDs must be composed from `is_plugin` + `id` → `terminal_N` or `plugin_N`

---

## Phase 1: Core — Agent Lifecycle + Concept Model

### 1.1 Global Config Uplift

Current `~/.zchat/config.toml` only has `[update]`. New schema:

```toml
# ~/.zchat/config.toml (global)

[servers.local]
host = "127.0.0.1"
port = 6667
tls = false

[servers.cloud]
host = "zchat.inside.h2os.cloud"
port = 6697
tls = true

[runners.claude-channel]
command = "claude"
args = [
    "--permission-mode", "bypassPermissions",
    "--dangerously-load-development-channels",
    "server:zchat-channel",
]

[update]
channel = "main"
auto_upgrade = true
```

Project config simplified to references:

```toml
# ~/.zchat/projects/local/config.toml
server = "local"
default_runner = "claude-channel"
default_channels = ["#general"]
username = ""
env_file = "claude.local.env"
mcp_server_cmd = ["zchat-channel"]  # MCP server command (dev override supported)

[zellij]
session = "zchat-local"
```

The `[tmux]` and `[irc]` sections are removed. Server connection details live in global config only. The `mcp_server_cmd` field is retained in project config (it's project-specific, used by `start.sh` to locate the MCP channel server binary).

### 1.2 Runner vs Agent Separation

- **Runner** = immutable template. Defined in global config `[runners.X]` (command/args) + template directory (start.sh, .env.example, soul.md). Analogous to a Docker image.
- **Agent** = project-scoped instance with workspace, state, and conversation. Analogous to a Docker container. Created with `zchat agent create agent0 --runner claude-channel`.

`template_loader.py` refactored to `runner.py`:
- `resolve_runner(name)` → merges global config command/args with template directory files
- `render_env()` logic unchanged, context source updated (built from runner + project config)

### 1.3 zellij.py — CLI Wrapper

Replaces `tmux.py`. Thin wrapper around `subprocess.run(["zellij", ...])`:

```python
# zchat/cli/zellij.py

def ensure_session(name: str, layout_path: Path | None = None) -> str:
    """Create or verify session exists. Returns session name."""

def new_tab(session: str, name: str, command: str | None = None) -> str:
    """Create tab, return tab name."""

def close_tab(session: str, tab_name: str) -> None:
    """Close tab by name."""

def list_tabs(session: str) -> list[dict]:
    """list-tabs --json, return tab/pane info."""

def send_command(session: str, pane_id: str, text: str) -> None:
    """paste + send-keys Enter."""

def send_keys(session: str, pane_id: str, keys: str) -> None:
    """send-keys for special keys (Enter, Ctrl-C, etc.)."""

def dump_screen(session: str, pane_id: str, full: bool = False) -> str:
    """dump-screen to /dev/shm, return content."""

def subscribe_pane(session: str, pane_id: str) -> subprocess.Popen:
    """Start subscribe process, return Popen for streaming reads."""

def tab_exists(session: str, tab_name: str) -> bool:
    """Check if tab exists via list-tabs."""

def get_pane_id(session: str, tab_name: str) -> str | None:
    """Parse terminal pane ID from list-tabs --json."""

def kill_session(session: str) -> None:
    """Kill session."""
```

### 1.4 agent_manager.py Migration

| Current (tmux) | Target (zellij) |
|---|---|
| `session.new_window(window_name, window_shell)` | `zellij.new_tab(session, name, command)` |
| `pane.send_keys(text)` | `zellij.send_command(session, pane_id, text)` |
| `window_alive(session, window_name)` | `zellij.tab_exists(session, tab_name)` |
| `find_window()` → `pane.capture_pane()` | `zellij.dump_screen()` or `subscribe_pane()` |
| `_auto_confirm_startup()` via capture_pane polling | `subscribe_pane()` event-driven detection + `send_keys` |

**`_auto_confirm_startup()` refactor**:
- Current: background thread polls `capture_pane()` for "trust this folder" text
- Target: `subscribe_pane()` streams output, detects prompt, sends `send_keys Enter`
- Fallback: `dump_screen` periodic check if subscribe misses split lines

**State changes**:
- `window_name` → `tab_name`
- Add `pane_id` (from `list-tabs --json`)
- Remove legacy tmux `pane_id` format (`%N`)

### 1.5 Phase 1 Acceptance

**Tests**:
- Unit: `test_zellij_helpers.py` (mock subprocess), `test_runner.py`, `test_global_config.py`
- E2E: `zchat agent create agent0` → verify tab → `zchat agent send` → verify → `zchat agent stop` → verify tab closed

**Deliverables**:
- `zellij.py` replaces `tmux.py`
- `runner.py` replaces `template_loader.py`
- Global config schema (servers/runners)
- Project config simplified
- Agent create/stop/list/send/restart/status working via Zellij

---

## Phase 2: WeeChat + KDL Layout + One-Command Startup

### 2.1 irc_manager.py Migration

| Current (tmux) | Target (zellij) |
|---|---|
| `session.new_window("weechat", window_shell=cmd)` | `zellij.new_tab(session, "weechat", cmd)` |
| WeeChat stop: `pane.send_keys("/quit")` | `zellij.send_command(session, pane_id, "/quit")` |
| State: `irc.weechat_window` | State: `irc.weechat_tab` + `irc.weechat_pane_id` |

ergo daemon management unchanged — it's an independent process managed by PID.

`_update_tmuxp_weechat()` method is removed entirely — its purpose was to patch the tmuxp YAML before loading, which is replaced by KDL layout generation in `layout.py`.

### 2.2 KDL Layout Generation

Each project generates `layout.kdl` at startup, stored in `~/.zchat/projects/<name>/layout.kdl`:

```kdl
layout {
    tab name="weechat" {
        pane command="weechat" {
            args "-d" "/path/to/.weechat" "-r" "/server add ..."
        }
    }
    tab name="alice-agent0" {
        pane command="bash" {
            args "-c" "cd /workspace && source .zchat-env && bash start.sh"
        }
    }
}
```

New module `zchat/cli/layout.py`:

```python
def generate_layout(project_config: dict, state: dict) -> str:
    """Generate KDL layout string from config + state."""

def write_layout(project_dir: Path, config: dict, state: dict) -> Path:
    """Write layout.kdl, return path."""
```

- Generated at startup based on current state (restores existing agents)
- Runtime agent creation uses `zellij.new_tab()` (no layout regeneration)
- Regenerated on next startup after `zchat shutdown`

### 2.3 `zchat project use` Migration

`cmd_project_use` currently does `tmux has-session` → `tmux switch-client` / `tmux attach`. Replaced with:

- Inside Zellij (`$ZELLIJ` set): `zellij action switch-session zchat-<project>`
- Outside Zellij: `os.execvp("zellij", ["zellij", "attach", "zchat-<project>"])` (creates if needed)

### 2.4 `claude.sh` Migration

`claude.sh` contains ~50 lines of tmux session management (session creation, iTerm2 tmux -CC integration, attach/switch). This is an alternative entry point used for direct Claude session launching. It is **rewritten** to use Zellij equivalents:

- `tmux has-session` → `zellij list-sessions | grep`
- `tmux new-session` → `zellij --new-session-with-layout` or `zellij attach --create-background`
- `tmux attach` → `os.execvp("zellij", ["zellij", "attach", ...])`
- iTerm2 `tmux -CC` integration is removed (Zellij has its own native terminal integration)

### 2.5 One-Command Startup

`zchat` with no arguments = start full environment and enter Zellij:

```python
def cmd_default():
    project = resolve_current_project()
    config = load_config(project)

    # Already in Zellij? switch-session
    if os.environ.get("ZELLIJ"):
        zellij.switch_session(f"zchat-{project}")
        return

    # Session exists? attach
    if zellij.session_exists(f"zchat-{project}"):
        os.execvp("zellij", ["zellij", "attach", f"zchat-{project}"])
        return

    # Start ergo if local server
    irc_manager.daemon_start()

    # Generate layout and launch
    layout_path = write_layout(project_dir, config, state)
    os.execvp("zellij", ["zellij", "--new-session-with-layout", str(layout_path),
                          "--session", f"zchat-{project}"])
```

### 2.6 Focus/Hide Migration

| Current | Target |
|---|---|
| `zchat agent focus agent0` → `tmux select-window` | `zellij action go-to-tab-name alice-agent0` |
| `zchat agent hide` → select weechat window | `zellij action go-to-tab-name weechat` |

### 2.7 Phase 2 Acceptance

**Tests**:
- Unit: `test_layout.py` (KDL generation correctness), `test_irc_manager_zellij.py`
- E2E: `zchat` (no args) → Zellij starts → WeeChat tab exists → agent create → focus/hide → shutdown
- Pre-release: `walkthrough.sh` updated for Zellij

**Deliverables**:
- `layout.py` — KDL layout generation
- `irc_manager.py` migrated (including `_update_tmuxp_weechat` removal)
- `zchat` one-command startup
- `zchat project use` migrated
- `claude.sh` rewritten for Zellij
- focus/hide migrated
- `start.sh` / `stop.sh` updated

---

## Phase 3: WASM Plugin — zchat Hub

### 3.1 Features

| Feature | Interaction |
|---|---|
| List all `zchat-*` sessions (projects) | List view, Enter to switch |
| Show agents + status per project | running/offline, real-time via TabUpdate |
| Create agent | Press `c`, input name, runs CLI |
| Stop agent | Select agent, press `d`, runs CLI |
| Floating pane | `Ctrl-K` to toggle, ESC to close |

### 3.2 Architecture

```
┌─────────────────────────────────┐
│  zchat-hub plugin (WASM)        │
│                                 │
│  ┌───────────────────────────┐  │
│  │ Projects                  │  │
│  │  * local (3 agents)       │  │
│  │    prod  (1 agent)        │  │
│  ├───────────────────────────┤  │
│  │ Agents (local)            │  │
│  │  > alice-agent0  running  │  │
│  │    alice-helper  running  │  │
│  │    alice-debug   offline  │  │
│  ├───────────────────────────┤  │
│  │ [c]reate [d]elete [Enter] │  │
│  │ switch   [q]uit           │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
```

### 3.3 Data Sources

- **Project list** ← `SessionUpdate` events, filter `name.starts_with("zchat-")`
- **Agent list + status** ← `TabUpdate` events on current session. Tabs (excluding system tabs like `weechat`) = agents. Tab exists = running, tab gone = offline.
- **Agent operations** → `run_command(["zchat", "agent", "create/stop", ...])` via `RunCommandResult`

No polling needed. Agent status is purely derived from Zellij tab state.

### 3.4 Permissions

```rust
request_permission(&[
    PermissionType::ReadApplicationState,    // SessionUpdate, TabUpdate
    PermissionType::ChangeApplicationState,  // switch_session, go_to_tab
    PermissionType::RunCommands,             // zchat agent create/stop
]);
```

### 3.5 Plugin Distribution

- Source in `zchat-hub-plugin/` (new directory or submodule)
- Pre-compiled `.wasm` distributed with zchat releases
- Referenced in KDL layout: `plugin location="file:~/.zchat/plugins/zchat-hub.wasm"`
- Keybinding in zchat's config.kdl:

```kdl
keybinds {
    shared_except "locked" {
        bind "Ctrl k" {
            LaunchOrFocusPlugin "file:~/.zchat/plugins/zchat-hub.wasm" {
                floating true
                move_to_focused_tab true
            }
        }
    }
}
```

### 3.6 Phase 3 Acceptance

**Tests**:
- Build: `cargo build --release --target wasm32-wasi` passes
- Integration: launch zchat → `Ctrl-K` → verify project list → switch → create/stop agent
- `zchat agent list --json` output format (unit test)

**Deliverables**:
- `zchat-hub-plugin/` — Rust WASM plugin project
- zchat config.kdl integration
- Plugin install flow

---

## Phase 4: Cleanup + Release

### 4.1 Remove tmux Dependencies

- Delete `zchat/cli/tmux.py`
- Remove `libtmux`, `tmuxp`, `pyyaml` (if unused elsewhere) from `pyproject.toml`
- `doctor.py`: check `zellij` ≥ 0.44.0 instead of `tmux`/`tmuxp`
- `install.sh`: change tmux/tmuxp checks and brew install to zellij
- `.github/workflows/test.yml`: `brew install tmux` → `brew install zellij`

### 4.2 Template → Runner Cleanup

- Delete `template_loader.py` (replaced by `runner.py`)
- CLI: `zchat template *` → `zchat runner *`
- Template directory retained as runner file assets (start.sh, .env.example, soul.md)

### 4.3 Config & State Migration

Auto-detect old config format on first startup:

```python
def migrate_config_if_needed(project_dir: Path):
    """Detect [tmux] section → generate [zellij], extract server to global config."""

def migrate_state_if_needed(project_dir: Path):
    """Migrate state.json: window_name → tab_name, remove legacy pane_id (%N format)."""
```

Config migration:
- `[tmux]` → `[zellij]`
- `[irc]` server/port/tls → global `[servers.X]`
- `[agents].default_type` → `[agents].default_runner`
- Backup to `.config.toml.bak`

State migration:
- `state.json` agent entries: `window_name` → `tab_name`, remove legacy `pane_id` (`%N` tmux format)
- `irc.weechat_window` → `irc.weechat_tab`
- Backup to `.state.json.bak`

### 4.4 Test Updates

This is significant work — the test infrastructure has deep tmux integration:

- Delete `test_tmux_helpers.py`
- Rewrite `tests/shared/tmux_helpers.py` → `tests/shared/zellij_helpers.py` (3 helper functions)
- All tmux mocks in unit tests → zellij subprocess mocks
- `tests/e2e/conftest.py`: rewrite `tmux_session`, `tmux_send`, `weechat_window` fixtures
- `tests/pre_release/conftest.py`: rewrite equivalent fixtures
- `tests/e2e/e2e-setup.sh`: tmux session validation → zellij session validation
- Pre-release `walkthrough.sh` and `walkthrough-steps.sh`: all tmux commands → zellij
- `pytest.ini`: marker description `ergo + tmux` → `ergo + zellij`
- Activate/update E2E tests

### 4.5 Release

- Version bump (dev version per project convention)
- Homebrew formula: dependency `tmux` → `zellij`
- Update README, docs/releasing.md

### 4.6 Phase 4 Acceptance

- Full test suite: Unit → E2E → Pre-release walkthrough
- `pip install zchat` has no libtmux/tmuxp dependency
- `zchat doctor` checks zellij not tmux
- `brew install zchat && zchat doctor` passes

---

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| **Zellij CLI edge cases** — `subscribe` JSON format, `list-tabs` field names, `paste` multiline escaping may differ from PoC | Phase 1-2 blocked | Write `zellij.py` + integration tests first in Phase 1; keep PoC records as reference |
| **Agent startup confirmation timing** — `subscribe` event-driven replacement of `capture_pane` polling may receive "trust this folder" text split across multiple events | Sporadic agent creation failures | Line-buffer subscribe output; fallback to `dump-screen` periodic check; timeout retry |
| **WASM Plugin development cycle** — team may lack Rust/WASM experience, Zellij plugin API docs are limited | Phase 3 delay | Phase 1-2 deliver a complete working system without the plugin; plugin is UX enhancement, not core; zellij skill available for development assistance |

---

## Acceptance Criteria (Overall)

1. `zchat` launches a customized Zellij session — users need not know Zellij internals
2. `zchat agent create/stop/list/send/focus/hide` all work via Zellij CLI
3. Agent startup trust-folder confirmation passes automatically (`subscribe` + `send-keys`)
4. Three-layer tests all pass (Unit → E2E → Pre-release)
5. `Ctrl-K` opens zchat hub plugin for project switching and agent management
6. `brew install zchat` works (depends on zellij, not tmux)
7. Global config with servers/runners, project config simplified to references
