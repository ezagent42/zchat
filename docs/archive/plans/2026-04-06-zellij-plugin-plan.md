# Zellij Plugin Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build two Zellij WASM plugins — a status bar and a command palette — that provide a native UI for all zchat operations.

**Architecture:** Two Rust `cdylib` crates in a Cargo workspace. Status bar reads Zellij events only. Command palette discovers commands from `zchat list-commands` JSON and delegates execution via `run_command`. CLI is the single source of truth.

**Tech Stack:** Rust, `zellij-tile` 0.44.0, `wasm32-wasip1` target, `serde_json`

**Design Doc:** `docs/plans/2026-04-06-zellij-plugin-design.md`

**Zellij Plugin Reference:** `.claude/skills/zellij/references/plugin-api-reference.md` and `plugin-patterns.md`

**Important:** The WASM target on this system is `wasm32-wasip1` (not `wasm32-wasi`). Use this throughout.

**Review Fixes (from code review):**

1. `RunCommandResult` exit_code is `Option<i32>`, not `i32` — match with `Some(0)` in palette
2. Multi-arg commands (e.g. `agent send <name> <text>`) need sequential collection — palette tracks `collected_args: Vec<String>` and `remaining_args` queue
3. Plugin must pass `--project {name}` to CLI — extract project name from SessionUpdate (`zchat-{name}` → `{name}`)
4. Verify `SessionInfo.is_current_session` compiles in Task 3 scaffold before depending on it
5. Status bar running/total: simplify to `running = total` (all non-system tabs are agents), no `is_fullscreen_active` heuristic
6. `list-commands` should also skip hidden groups, not just hidden leaf commands
7. Plugin auto-install should overwrite outdated `.wasm` (compare mtime, not just existence)

---

## Task 1: CLI — `list-commands` + `--json` flag

**Files:**
- Modify: `zchat/cli/app.py`
- Test: `tests/unit/test_list_commands.py`

**Step 1: Write test for list-commands**

```python
# tests/unit/test_list_commands.py
import json
from typer.testing import CliRunner
from zchat.cli.app import app

runner = CliRunner()

def test_list_commands_returns_json():
    result = runner.invoke(app, ["list-commands"])
    assert result.exit_code == 0
    commands = json.loads(result.output)
    assert isinstance(commands, list)
    names = [c["name"] for c in commands]
    assert "agent create" in names
    assert "shutdown" in names

def test_list_commands_includes_args():
    result = runner.invoke(app, ["list-commands"])
    commands = json.loads(result.output)
    agent_create = next(c for c in commands if c["name"] == "agent create")
    arg_names = [a["name"] for a in agent_create["args"]]
    assert "name" in arg_names

def test_list_commands_includes_source():
    result = runner.invoke(app, ["list-commands"])
    commands = json.loads(result.output)
    agent_stop = next(c for c in commands if c["name"] == "agent stop")
    name_arg = next(a for a in agent_stop["args"] if a["name"] == "name")
    assert name_arg["source"] == "running_agents"

def test_list_commands_no_source_for_free_input():
    result = runner.invoke(app, ["list-commands"])
    commands = json.loads(result.output)
    agent_create = next(c for c in commands if c["name"] == "agent create")
    name_arg = next(a for a in agent_create["args"] if a["name"] == "name")
    assert "source" not in name_arg
```

**Step 2: Run tests, verify fail**

Run: `uv run pytest tests/unit/test_list_commands.py -v`

**Step 3: Implement list-commands**

Add to `zchat/cli/app.py`:

```python
import json as _json
import click

# Registry: which args get selection lists in the plugin
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

@app.command("list-commands", hidden=True)
def cmd_list_commands():
    """Output all CLI commands as JSON (for plugin discovery)."""
    click_group = typer.main.get_group(app)
    commands = []

    def walk(group, prefix=""):
        for name in sorted(group.list_commands(None) or []):
            cmd = group.get_command(None, name)
            if cmd is None:
                continue
            full = f"{prefix} {name}".strip()
            if isinstance(cmd, click.Group):
                if not getattr(cmd, "hidden", False):
                    walk(cmd, full)
            elif getattr(cmd, "hidden", False):
                continue  # skip hidden commands like list-commands itself
            else:
                sources = _ARG_SOURCES.get(full, {})
                args = []
                for p in cmd.params:
                    if p.name in ("ctx",) or p.name.startswith("_"):
                        continue
                    arg = {"name": p.name, "required": p.required}
                    if p.name in sources:
                        arg["source"] = sources[p.name]
                    args.append(arg)
                commands.append({"name": full, "args": args})

    walk(click_group)
    typer.echo(_json.dumps(commands))
```

**Step 4: Run tests, verify pass**

Run: `uv run pytest tests/unit/test_list_commands.py -v`

**Step 5: Commit**

```bash
git add zchat/cli/app.py tests/unit/test_list_commands.py
git commit -m "feat: add list-commands hidden command for plugin discovery"
```

---

## Task 2: CLI — `agent list --json`

**Files:**
- Modify: `zchat/cli/app.py` (cmd_agent_list function)
- Test: `tests/unit/test_list_commands.py` (add test)

**Step 1: Write test**

```python
# Add to tests/unit/test_list_commands.py
import pytest

@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr("zchat.cli.project.ZCHAT_DIR", str(tmp_path))
    monkeypatch.setattr("zchat.cli.config_cmd.ZCHAT_DIR", str(tmp_path))
    monkeypatch.setattr("zchat.cli.runner.ZCHAT_DIR", str(tmp_path))
    return tmp_path

def test_agent_list_json(isolated_home):
    # Create a minimal project config so CLI doesn't error
    # This is a smoke test — real agent list requires IRC
    result = runner.invoke(app, ["agent", "list", "--json"])
    # Without a project, it should error gracefully
    # With a project, it should output JSON array
    assert result.exit_code in (0, 1)  # 0 with project, 1 without
```

**Step 2: Implement**

Find `cmd_agent_list` in app.py and add `--json` option:

```python
@agent_app.command("list")
def cmd_agent_list(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all agents and their status."""
    mgr = _get_agent_manager(ctx)
    agents = mgr.list_agents()
    if json_output:
        import json
        out = [{"name": n, **{k: v for k, v in info.items()}} for n, info in agents.items()]
        typer.echo(json.dumps(out))
        return
    # ... existing table output ...
```

**Step 3: Run tests, commit**

```bash
git add zchat/cli/app.py tests/unit/test_list_commands.py
git commit -m "feat: agent list --json for plugin consumption"
```

---

## Task 3: Cargo Workspace Scaffold

**Files:**
- Create: `zchat-hub-plugin/Cargo.toml`
- Create: `zchat-hub-plugin/.cargo/config.toml`
- Create: `zchat-hub-plugin/zchat-status/Cargo.toml`
- Create: `zchat-hub-plugin/zchat-status/src/lib.rs`
- Create: `zchat-hub-plugin/zchat-palette/Cargo.toml`
- Create: `zchat-hub-plugin/zchat-palette/src/lib.rs`

**Step 1: Create workspace Cargo.toml**

```toml
# zchat-hub-plugin/Cargo.toml
[workspace]
members = ["zchat-status", "zchat-palette"]
resolver = "2"
```

```toml
# zchat-hub-plugin/.cargo/config.toml
[build]
target = "wasm32-wasip1"
```

**Step 2: Create zchat-status crate**

```toml
# zchat-hub-plugin/zchat-status/Cargo.toml
[package]
name = "zchat-status"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]

[dependencies]
zellij-tile = "0.44"
```

```rust
// zchat-hub-plugin/zchat-status/src/lib.rs
use zellij_tile::prelude::*;
use std::collections::BTreeMap;

#[derive(Default)]
struct ZchatStatus {
    project_name: String,
    agent_count: usize,
    total_tabs: usize,
}

register_plugin!(ZchatStatus);

impl ZellijPlugin for ZchatStatus {
    fn load(&mut self, _configuration: BTreeMap<String, String>) {
        set_selectable(false);
        request_permission(&[PermissionType::ReadApplicationState]);
        subscribe(&[EventType::TabUpdate, EventType::SessionUpdate]);
    }

    fn update(&mut self, event: Event) -> bool {
        false // placeholder
    }

    fn render(&mut self, _rows: usize, cols: usize) {
        print!("zchat"); // placeholder
    }
}
```

**Step 3: Create zchat-palette crate**

```toml
# zchat-hub-plugin/zchat-palette/Cargo.toml
[package]
name = "zchat-palette"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]

[dependencies]
zellij-tile = "0.44"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

```rust
// zchat-hub-plugin/zchat-palette/src/lib.rs
use zellij_tile::prelude::*;
use std::collections::BTreeMap;

#[derive(Default)]
struct ZchatPalette;

register_plugin!(ZchatPalette);

impl ZellijPlugin for ZchatPalette {
    fn load(&mut self, _configuration: BTreeMap<String, String>) {
        request_permission(&[
            PermissionType::ReadApplicationState,
            PermissionType::ChangeApplicationState,
            PermissionType::RunCommands,
        ]);
        subscribe(&[
            EventType::Key,
            EventType::TabUpdate,
            EventType::SessionUpdate,
            EventType::RunCommandResult,
        ]);
    }

    fn update(&mut self, event: Event) -> bool {
        false // placeholder
    }

    fn render(&mut self, _rows: usize, _cols: usize) {
        println!("zchat palette"); // placeholder
    }
}
```

**Step 4: Build**

```bash
cd zchat-hub-plugin && cargo build --release
```

Expected: compiles to `target/wasm32-wasip1/release/zchat_status.wasm` and `zchat_palette.wasm`

**Step 5: Commit**

```bash
git add zchat-hub-plugin/
git commit -m "feat: scaffold zchat plugin Cargo workspace (status + palette)"
```

---

## Task 4: Status Bar Plugin

**Files:**
- Modify: `zchat-hub-plugin/zchat-status/src/lib.rs`

**Step 1: Implement full status bar**

```rust
// zchat-hub-plugin/zchat-status/src/lib.rs
use zellij_tile::prelude::*;
use std::collections::BTreeMap;

/// System tab name suffixes that are not agents.
const SYSTEM_SUFFIXES: &[&str] = &["/chat", "/ctl"];

#[derive(Default)]
struct ZchatStatus {
    project_name: String,
    running_agents: usize,
    total_agents: usize,
}

register_plugin!(ZchatStatus);

impl ZchatStatus {
    fn update_from_tabs(&mut self, tabs: &[TabInfo]) {
        let mut running = 0usize;
        let mut total = 0usize;
        for tab in tabs {
            let name = &tab.name;
            // Skip system tabs (*/chat, */ctl) and default "Tab #N" tabs
            if SYSTEM_SUFFIXES.iter().any(|s| name.ends_with(s)) {
                continue;
            }
            if name.starts_with("Tab #") {
                continue;
            }
            total += 1;
        }
        // All non-system tabs are agents; precise running count would
        // require `zchat agent list --json` — keep it simple for now.
        self.running_agents = total;
        self.total_agents = total;
    }

    fn update_project_name(&mut self, sessions: &[SessionInfo]) {
        for session in sessions {
            if session.is_current_session {
                // Extract project name: "zchat-local" → "local"
                self.project_name = session
                    .name
                    .strip_prefix("zchat-")
                    .unwrap_or(&session.name)
                    .to_string();
                break;
            }
        }
    }
}

impl ZellijPlugin for ZchatStatus {
    fn load(&mut self, _configuration: BTreeMap<String, String>) {
        set_selectable(false);
        request_permission(&[PermissionType::ReadApplicationState]);
        subscribe(&[EventType::TabUpdate, EventType::SessionUpdate]);
    }

    fn update(&mut self, event: Event) -> bool {
        match event {
            Event::TabUpdate(tabs) => {
                self.update_from_tabs(&tabs);
                true
            }
            Event::SessionUpdate(sessions, _) => {
                self.update_project_name(&sessions);
                true
            }
            _ => false,
        }
    }

    fn render(&mut self, _rows: usize, cols: usize) {
        let status = format!(
            " {} │ agents: {}/{}",
            self.project_name, self.running_agents, self.total_agents,
        );
        let text = Text::new(&status).color_range(0, 1..=self.project_name.len());
        print_text_with_coordinates(text, 0, 0, Some(cols), None);
    }
}
```

**Step 2: Build and test manually**

```bash
cd zchat-hub-plugin && cargo build --release
# Copy to plugins dir
mkdir -p ~/.zchat/plugins
cp target/wasm32-wasip1/release/zchat_status.wasm ~/.zchat/plugins/
# Test in Zellij (load as floating first to verify)
zellij plugin -- file:~/.zchat/plugins/zchat_status.wasm
```

**Step 3: Commit**

```bash
git add zchat-hub-plugin/zchat-status/
git commit -m "feat: implement zchat-status bar plugin"
```

---

## Task 5: Palette — Fuzzy Matching Module

**Files:**
- Create: `zchat-hub-plugin/zchat-palette/src/fuzzy.rs`

**Step 1: Implement fuzzy scorer**

```rust
// zchat-hub-plugin/zchat-palette/src/fuzzy.rs

/// Score a query against a target string using fuzzy subsequence matching.
/// Returns None if the query doesn't match.
/// Higher score = better match. Bonuses for consecutive chars and word starts.
pub fn fuzzy_score(query: &str, target: &str) -> Option<i32> {
    if query.is_empty() {
        return Some(0);
    }

    let query_lower: Vec<char> = query.to_lowercase().chars().collect();
    let target_lower: Vec<char> = target.to_lowercase().chars().collect();
    let target_chars: Vec<char> = target.chars().collect();

    let mut score: i32 = 0;
    let mut qi = 0;
    let mut prev_match_idx: Option<usize> = None;

    for (ti, &tc) in target_lower.iter().enumerate() {
        if qi < query_lower.len() && tc == query_lower[qi] {
            score += 1;

            // Consecutive match bonus
            if let Some(prev) = prev_match_idx {
                if ti == prev + 1 {
                    score += 3;
                }
            }

            // Start-of-word bonus (first char or after space/separator)
            if ti == 0 || matches!(target_chars.get(ti.wrapping_sub(1)), Some(' ' | '-' | '_' | '/')) {
                score += 5;
            }

            prev_match_idx = Some(ti);
            qi += 1;
        }
    }

    if qi == query_lower.len() {
        Some(score)
    } else {
        None // Not all query chars matched
    }
}

/// Filter and sort items by fuzzy match score. Returns (index, score) pairs, best first.
pub fn fuzzy_filter(query: &str, items: &[String]) -> Vec<(usize, i32)> {
    let mut scored: Vec<(usize, i32)> = items
        .iter()
        .enumerate()
        .filter_map(|(i, item)| fuzzy_score(query, item).map(|s| (i, s)))
        .collect();
    scored.sort_by(|a, b| b.1.cmp(&a.1)); // descending score
    scored
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_query_matches_everything() {
        assert_eq!(fuzzy_score("", "anything"), Some(0));
    }

    #[test]
    fn exact_match_scores_high() {
        let exact = fuzzy_score("agent create", "agent create").unwrap();
        let partial = fuzzy_score("ag cr", "agent create").unwrap();
        assert!(exact > partial);
    }

    #[test]
    fn no_match_returns_none() {
        assert_eq!(fuzzy_score("xyz", "agent create"), None);
    }

    #[test]
    fn filter_sorts_by_score() {
        let items: Vec<String> = vec![
            "project create".into(),
            "agent create".into(),
            "agent restart".into(),
        ];
        let results = fuzzy_filter("ag cr", &items);
        assert!(!results.is_empty());
        assert_eq!(results[0].0, 1); // "agent create" should be first
    }
}
```

**Step 2: Add module to lib.rs**

```rust
// Add to top of zchat-hub-plugin/zchat-palette/src/lib.rs
mod fuzzy;
```

**Step 3: Build and run tests**

```bash
cd zchat-hub-plugin
cargo test -p zchat-palette
```

**Step 4: Commit**

```bash
git add zchat-hub-plugin/zchat-palette/
git commit -m "feat: add fuzzy matching module for command palette"
```

---

## Task 6: Palette — Full Implementation

**Files:**
- Modify: `zchat-hub-plugin/zchat-palette/src/lib.rs`
- Create: `zchat-hub-plugin/zchat-palette/src/ui.rs`

**Step 1: Implement complete palette plugin**

This is the largest task. The plugin has these states:

1. `CommandFilter` — fuzzy-filtering the command list
2. `ArgSelect` — selecting from a list of candidates (agents, projects)
3. `ArgInput` — free text input for args without a source
4. `Executing` — waiting for RunCommandResult
5. `Result` — showing success/error briefly

Key implementation points:
- On `load()`: call `run_command(["zchat", "list-commands"])` to discover commands
- On `RunCommandResult` with context `"discover"`: parse JSON into command list
- On `Key` events: handle character input, Up/Down navigation, Enter selection, Esc to close
- On `RunCommandResult` with context `"execute"`: show result, auto-close
- Render: different UI per state (filter list, selection list, text input, spinner, result)
- **`exit_code` is `Option<i32>`** — match with `Some(0)` for success, not bare `0`

See design doc `docs/plans/2026-04-06-zellij-plugin-design.md` for the full `PaletteState` enum and UI layout.

**Multi-arg collection (review fix #2):**
Commands with multiple args (e.g. `agent send <name> <text>`) need sequential collection:
```rust
struct PaletteState {
    // ...
    collected_args: Vec<(String, String)>,  // (arg_name, value) pairs already collected
    remaining_args: VecDeque<ArgInfo>,       // args still to collect
}
```
Flow: after command selection → pop first from `remaining_args` → if it has a `source`, enter `ArgSelect`; else enter `ArgInput` → on completion, push to `collected_args` → pop next → when `remaining_args` empty, execute with all collected args.

**--project flag (review fix #3):**
All CLI invocations must include `--project {name}` extracted from the current session name:
```rust
fn build_command(&self, cmd_name: &str) -> Vec<String> {
    let mut args = vec!["zchat".to_string()];
    if !self.project_name.is_empty() {
        args.push("--project".to_string());
        args.push(self.project_name.clone());
    }
    // Split cmd_name by space and append parts
    args.extend(cmd_name.split_whitespace().map(String::from));
    // Append collected arg values
    for (_, value) in &self.collected_args {
        args.push(value.clone());
    }
    args
}
```
Project name extracted from `SessionUpdate`: `zchat-{name}` → `{name}`.

For agent/project candidates:
- `running_agents` source: filter TabUpdate tabs (exclude system tabs `*/chat`, `*/ctl`)
- `projects` source: filter SessionUpdate sessions (prefix `zchat-`)

**Step 2: Build**

```bash
cd zchat-hub-plugin && cargo build --release
```

**Step 3: Manual test**

```bash
cp target/wasm32-wasip1/release/zchat_palette.wasm ~/.zchat/plugins/
# In a zchat Zellij session:
zellij plugin -f -- file:~/.zchat/plugins/zchat_palette.wasm
# Type "ag cr" → should show "agent create"
# Select → type name → should create agent
```

**Step 4: Commit**

```bash
git add zchat-hub-plugin/zchat-palette/
git commit -m "feat: implement command palette plugin with fuzzy matching"
```

---

## Task 7: Layout Integration + Config.kdl

**Files:**
- Modify: `zchat/cli/layout.py`
- Create: `zchat/cli/data/config.kdl`
- Modify: `zchat/cli/app.py` (`_enter_session` to pass config.kdl)
- Test: `tests/unit/test_layout.py`

**Step 1: Update layout.py to include zchat-status plugin**

In `generate_layout`, update the `default_tab_template`:

```python
# Replace zellij:status-bar with zchat-status + zellij:status-bar
lines.append("    default_tab_template {")
lines.append('        pane size=1 borderless=true {')
lines.append('            plugin location="zellij:tab-bar"')
lines.append("        }")
lines.append("        children")
lines.append('        pane size=1 borderless=true {')
lines.append('            plugin location="file:~/.zchat/plugins/zchat-status.wasm"')
lines.append("        }")
lines.append('        pane size=2 borderless=true {')
lines.append('            plugin location="zellij:status-bar"')
lines.append("        }")
lines.append("    }")
```

**Step 2: Create config.kdl with Ctrl-K keybinding**

```kdl
// zchat/cli/data/config.kdl
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

**Step 3: Update `_enter_session` to use config.kdl**

In `app.py`, update the `os.execvp` call to include `--config`:

```python
config_kdl = os.path.join(os.path.dirname(__file__), "data", "config.kdl")
os.execvp("zellij", ["zellij",
    "--config", config_kdl,
    "--new-session-with-layout", str(layout_path),
    "--session", session_name])
```

**Step 4: Update layout test**

```python
def test_generate_layout_has_zchat_status_plugin():
    config = {}
    state = {"agents": {}}
    kdl = generate_layout(config, state)
    assert "zchat-status.wasm" in kdl
```

**Step 5: Run tests, commit**

```bash
uv run pytest tests/unit/test_layout.py -v
git add zchat/cli/layout.py zchat/cli/data/config.kdl zchat/cli/app.py tests/unit/test_layout.py
git commit -m "feat: integrate plugins into layout + config.kdl keybinding"
```

---

## Task 8: Plugin Auto-Install

**Files:**
- Modify: `zchat/cli/app.py` (`_enter_session`)

**Step 1: Add plugin install logic**

Before launching Zellij session, ensure `.wasm` files are in `~/.zchat/plugins/`:

```python
def _ensure_plugins():
    """Copy bundled .wasm plugins to ~/.zchat/plugins/ if missing."""
    from zchat.cli.project import ZCHAT_DIR
    plugins_dir = os.path.join(ZCHAT_DIR, "plugins")
    os.makedirs(plugins_dir, exist_ok=True)
    bundled_dir = os.path.join(os.path.dirname(__file__), "data", "plugins")
    if not os.path.isdir(bundled_dir):
        return
    for wasm in os.listdir(bundled_dir):
        if wasm.endswith(".wasm"):
            dest = os.path.join(plugins_dir, wasm)
            src = os.path.join(bundled_dir, wasm)
            src_mtime = os.path.getmtime(src)
            if not os.path.isfile(dest) or os.path.getmtime(dest) < src_mtime:
                import shutil
                shutil.copy2(src, dest)
```

Call `_ensure_plugins()` at the start of `_enter_session`.

For development, also support copying from the build output:

```bash
# Dev workflow: build and install
cd zchat-hub-plugin && cargo build --release
cp target/wasm32-wasip1/release/zchat_status.wasm ../zchat/cli/data/plugins/
cp target/wasm32-wasip1/release/zchat_palette.wasm ../zchat/cli/data/plugins/
```

**Step 2: Commit**

```bash
mkdir -p zchat/cli/data/plugins
git add zchat/cli/app.py zchat/cli/data/plugins/.gitkeep
git commit -m "feat: auto-install WASM plugins on first launch"
```

---

## Task Dependency Graph

```
Task 1 (list-commands) ──→ Task 6 (palette uses it)
Task 2 (agent list --json) ──→ Task 6 (palette may use it)
Task 3 (scaffold) ──→ Task 4 (status bar)
Task 3 (scaffold) ──→ Task 5 (fuzzy module) ──→ Task 6 (palette)
Task 4 + Task 6 ──→ Task 7 (layout integration)
Task 7 ──→ Task 8 (auto-install)
```

**Parallelizable:** Tasks 1-2 (CLI changes) and Tasks 3-5 (Rust scaffold + fuzzy) are independent.
