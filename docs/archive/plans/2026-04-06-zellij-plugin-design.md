# zchat Zellij Plugin Design — Dashboard + Command Palette

> Date: 2026-04-06
> Status: Approved
> Depends on: `2026-04-06-zellij-migration-design.md` (Phase 1-2 complete)

## Goal

Replace the "type CLI commands in ctl tab" workflow with a native Zellij UI:
- **Status Bar**: always-visible project name + agent count
- **Command Palette**: `Ctrl-K` floating panel with fuzzy-matched commands

All business logic stays in the CLI. The plugin is a pure UI shell — it discovers commands from CLI and delegates execution via `run_command(["zchat", ...])`.

## Architecture

```
┌──────────────────────────────────────────┐
│ Zellij Session (zchat-local)             │
│                                          │
│  ┌─ tab-bar (zellij built-in) ────────┐  │
│  │ [chat] [ctl] [alice-agent0]        │  │
│  └────────────────────────────────────┘  │
│                                          │
│  ┌─ main content ────────────────────┐   │
│  │                                    │   │
│  │  ┌─ Command Palette (Ctrl-K) ──┐  │   │
│  │  │ > ag cr_                     │  │   │
│  │  │   agent create               │  │   │
│  │  │   agent restart              │  │   │
│  │  │   project create             │  │   │
│  │  └──────────────────────────────┘  │   │
│  │                                    │   │
│  └────────────────────────────────────┘   │
│                                          │
│  ┌─ zchat-status (1 row, borderless) ─┐  │
│  │ local │ agents: 2/3                │  │
│  └────────────────────────────────────┘  │
│  ┌─ status-bar (zellij built-in) ─────┐  │
│  │ NORMAL │ ...                       │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

## Principle: CLI as Single Source of Truth

The plugin has **zero business logic**. This is a hard constraint because:
- WeeChat plugin (`/agent create`) also calls CLI
- Future integrations (API, MCP tools) will also call CLI
- One place to maintain, one place to test

The plugin's only responsibilities:
1. Render UI (status bar, palette)
2. Discover available commands from CLI
3. Forward user selections to CLI via `run_command`
4. Reflect state from Zellij events (TabUpdate, SessionUpdate)

## Component 1: Status Bar Plugin (`zchat-status.wasm`)

### Behavior

- `set_selectable(false)` — cannot be focused
- Subscribes to `TabUpdate` and `SessionUpdate`
- Renders one line: `{project_name} │ agents: {running}/{total}`
- Project name: extracted from session name (`zchat-local` → `local`)
- Agent count: derived from TabUpdate (count tabs that are not system tabs like `*/chat`, `*/ctl`, tab-bar, status-bar)
- Running count: tabs with non-exited terminal panes

### Permissions

```rust
request_permission(&[PermissionType::ReadApplicationState]);
```

No `RunCommands` needed — all data from Zellij events.

### Events

```rust
subscribe(&[EventType::TabUpdate, EventType::SessionUpdate]);
```

## Component 2: Command Palette Plugin (`zchat-palette.wasm`)

### Behavior

**Launch**: `Ctrl-K` → floating pane, centered

**Phase 1 — Command Discovery** (on load):
```rust
run_command(&["zchat", "list-commands"], context);
// Returns JSON array of {name, args: [{name, required, source?}]}
```

**Phase 2 — Fuzzy Filter** (on keypress):
- User types characters → filter command list by fuzzy match
- Up/Down or j/k to navigate
- Enter to select

**Phase 3 — Argument Collection** (after command selected):
- If command has no args → execute immediately
- If command has args with `source` (e.g., `"running_agents"`, `"projects"`) → show selection list from TabUpdate/SessionUpdate data
- If command has args without `source` → show text input prompt
- After all args collected → execute

**Phase 4 — Execution**:
```rust
run_command(&["zchat", "agent", "create", &name], context);
// Wait for RunCommandResult
// Show brief result (success/error) → auto-close after 1s, or close on any key
```

### Fuzzy Matching

Simple substring-based scoring in Rust (no external dependency):

```rust
fn fuzzy_score(query: &str, target: &str) -> Option<i32> {
    // Match each query char in order within target
    // Score: consecutive matches bonus, start-of-word bonus
    // Return None if no match
}
```

### Argument Sources

Commands can declare where to get argument candidates:

| Source | Data Origin | Example |
|--------|------------|---------|
| `running_agents` | TabUpdate — non-system tabs | `agent stop`, `agent focus` |
| `all_agents` | TabUpdate — all agent tabs (including offline from last list-commands) | `agent restart` |
| `projects` | SessionUpdate — filter `zchat-*` sessions | `project use` |
| (none) | Free text input | `agent create`, `agent send` |

### Permissions

```rust
request_permission(&[
    PermissionType::ReadApplicationState,    // TabUpdate, SessionUpdate
    PermissionType::ChangeApplicationState,  // switch_session (for project use)
    PermissionType::RunCommands,             // zchat CLI calls
]);
```

### Events

```rust
subscribe(&[
    EventType::Key,
    EventType::TabUpdate,
    EventType::SessionUpdate,
    EventType::RunCommandResult,
]);
```

### UI States

```
enum PaletteState {
    CommandFilter { query: String, selected: usize },
    ArgSelect { command: String, arg_name: String, candidates: Vec<String>, selected: usize },
    ArgInput { command: String, arg_name: String, input: String },
    Executing { command: String },
    Result { success: bool, message: String },
}
```

## CLI Changes

### New hidden command: `list-commands`

```python
@app.command("list-commands", hidden=True)
def cmd_list_commands():
    """Output all CLI commands as JSON (for plugin discovery)."""
    click_group = typer.main.get_group(app)
    # Walk command tree, collect name + params
    # Output JSON to stdout
```

Output format:
```json
[
  {"name": "agent create", "args": [
    {"name": "name", "required": true},
    {"name": "workspace", "required": false},
    {"name": "channels", "required": false}
  ]},
  {"name": "agent stop", "args": [
    {"name": "name", "required": true, "source": "running_agents"}
  ]},
  {"name": "agent focus", "args": [
    {"name": "name", "required": true, "source": "running_agents"}
  ]},
  {"name": "project use", "args": [
    {"name": "name", "required": true, "source": "projects"}
  ]},
  {"name": "shutdown", "args": []},
  ...
]
```

The `source` field is added via a decorator or annotation on the CLI command, not auto-detected by typer introspection. Example:

```python
# In app.py, a registry for argument sources
_ARG_SOURCES = {
    "agent stop": {"name": "running_agents"},
    "agent focus": {"name": "running_agents"},
    "agent hide": {"name": "running_agents"},
    "agent restart": {"name": "running_agents"},
    "agent send": {"name": "running_agents"},
    "agent status": {"name": "running_agents"},
    "project use": {"name": "projects"},
    "project remove": {"name": "projects"},
    "project show": {"name": "projects"},
}
```

### `--json` flag for agent list

```python
@agent_app.command("list")
def cmd_agent_list(ctx, json_output: bool = typer.Option(False, "--json")):
```

## KDL Layout Integration

`layout.py` generates:

```kdl
layout {
    default_tab_template {
        pane size=1 borderless=true {
            plugin location="zellij:tab-bar"
        }
        children
        pane size=1 borderless=true {
            plugin location="file:~/.zchat/plugins/zchat-status.wasm"
        }
        pane size=2 borderless=true {
            plugin location="zellij:status-bar"
        }
    }
    tab name="local/chat" focus=true { ... }
    tab name="local/ctl" { ... }
}
```

Keybinding in zchat's `config.kdl`:

```kdl
keybinds {
    shared_except "locked" {
        bind "Ctrl k" {
            LaunchOrFocusPlugin "file:~/.zchat/plugins/zchat-palette.wasm" {
                floating true
                move_to_focused_tab true
            }
        }
    }
}
```

## Distribution

- Source: `zchat-hub-plugin/` (Cargo workspace with two crates, or two separate dirs)
- Build: `cargo build --release --target wasm32-wasi`
- Install: `zchat` startup auto-copies `.wasm` to `~/.zchat/plugins/` if missing or outdated
- Release: pre-compiled `.wasm` bundled in PyPI package via `package_data`

## Project Structure

```
zchat-hub-plugin/
├── Cargo.toml              # workspace
├── zchat-status/
│   ├── Cargo.toml          # cdylib, zellij-tile dep
│   └── src/lib.rs
├── zchat-palette/
│   ├── Cargo.toml          # cdylib, zellij-tile dep, serde_json
│   └── src/
│       ├── lib.rs          # ZellijPlugin impl
│       ├── fuzzy.rs        # fuzzy matching
│       └── ui.rs           # render helpers
└── .cargo/
    └── config.toml         # target = wasm32-wasi
```

## Acceptance Criteria

1. `zchat` launches Zellij → status bar shows `local │ agents: 0/0`
2. Agent 创建后 status bar 实时更新 `agents: 1/1`
3. `Ctrl-K` 弹出 command palette → 输入 "ag cr" → 匹配 "agent create"
4. 选择命令 → 输入 agent name → agent 在新 tab 中启动
5. `Ctrl-K` → "shutdown" → 执行关闭
6. `Ctrl-K` → "project use" → 列出 projects → 选择 → switch-session
7. Plugin 不含任何业务逻辑 — 所有操作通过 `zchat` CLI 完成
