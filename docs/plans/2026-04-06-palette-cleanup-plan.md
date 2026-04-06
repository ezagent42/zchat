# Palette Interactive Pane — Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Clean up the palette plugin after the architectural shift from "form filler" to "launcher", remove dead code, simplify `build_cli_args`, and add missing tests.

**Architecture:** The POC is already merged. The palette now uses `open_command_pane_floating` to launch an interactive terminal pane instead of `run_command`. This plan cleans up leftover code from the old approach and ensures all paths are tested.

**Tech Stack:** Rust (`zellij-tile` 0.44), Python (typer), `wasm32-wasip1`

**Design Doc:** `docs/plans/2026-04-06-palette-interactive-pane-design.md`

---

### Task 1: Simplify `build_cli_args` — only positional args

Since the palette now only collects required positional args (optional args handled by CLI in the terminal pane), `collected_args` no longer needs the `(name, value, required)` tuple. Simplify to `Vec<String>`.

**Files:**
- Modify: `zchat-hub-plugin/zchat-palette/src/commands.rs`
- Modify: `zchat-hub-plugin/zchat-palette/src/main.rs`

**Step 1: Update `build_cli_args` signature and tests**

In `commands.rs`, change `collected_args` from `&[(String, String, bool)]` to `&[String]`:

```rust
pub fn build_cli_args(
    zchat_bin: &str,
    project_name: &str,
    command_name: &str,
    collected_args: &[String],
) -> Vec<String> {
    let mut cmd: Vec<String> = zchat_bin.split_whitespace().map(String::from).collect();
    if !project_name.is_empty() {
        cmd.push("--project".to_string());
        cmd.push(project_name.to_string());
    }
    cmd.extend(command_name.split_whitespace().map(String::from));
    cmd.extend(collected_args.iter().cloned());
    cmd
}
```

Update tests — remove `build_cli_args_optional_flags` (dead path), simplify the rest:

```rust
#[test]
fn build_cli_args_with_project() {
    let args = build_cli_args("/usr/bin/zchat", "local", "agent create", &["myagent".into()]);
    assert_eq!(args, vec!["/usr/bin/zchat", "--project", "local", "agent", "create", "myagent"]);
}

#[test]
fn build_cli_args_without_project() {
    let args = build_cli_args("zchat", "", "shutdown", &[]);
    assert_eq!(args, vec!["zchat", "shutdown"]);
}

#[test]
fn build_cli_args_multiword_bin() {
    let args = build_cli_args("/usr/bin/python -m zchat.cli", "dev", "agent stop", &["a0".into()]);
    assert_eq!(args, vec!["/usr/bin/python", "-m", "zchat.cli", "--project", "dev", "agent", "stop", "a0"]);
}
```

**Step 2: Update `main.rs` — change `collected_args` type**

Change `collected_args: Vec<(String, String, bool)>` to `collected_args: Vec<String>`.

Update all `.push(...)` calls:
- `ArgSelect` Enter handler: `.push(val.clone())` (was `.push((name, val, required))`)
- `ArgInput` Enter handler: `.push(input.clone())` (was `.push((n, v, r))`)

Remove `required` field from `ArgSelect` and `ArgInput` states (palette only collects required args, so it's always true). Also remove the Esc "skip optional" logic — Esc always returns to CommandFilter.

```rust
enum PaletteState {
    CommandFilter { query: String, selected: usize },
    ArgSelect {
        arg_name: String,
        candidates: Vec<String>,
        values: Vec<String>,
        selected: usize,
    },
    ArgInput {
        arg_name: String,
        input: String,
    },
}
```

**Step 3: Build and test**

```bash
cd zchat-hub-plugin && cargo build --release && cargo test -p zchat-palette --target aarch64-apple-darwin
```

Expected: compiles cleanly, all tests pass.

**Step 4: Run Python tests**

```bash
uv run pytest tests/unit/ -v
```

Expected: all pass (Python side unchanged).

**Step 5: Commit**

```bash
git add zchat-hub-plugin/zchat-palette/src/
git commit -m "refactor: simplify palette args to Vec<String>, remove optional arg handling"
```

---

### Task 2: Remove dead `choices` path from `advance_args`

Since palette only collects required positional args, the `choices` branch in `advance_args` is never reached (no required arg has static choices). Remove it.

**Files:**
- Modify: `zchat-hub-plugin/zchat-palette/src/main.rs`

**Step 1: Simplify `advance_args`**

```rust
fn advance_args(&mut self) {
    if let Some(arg) = self.remaining_args.pop_front() {
        match arg.source.as_deref() {
            Some("running_agents") => {
                let tabs = self.agent_tabs.clone();
                self.state = PaletteState::ArgSelect {
                    arg_name: arg.name,
                    candidates: tabs.clone(),
                    values: tabs,
                    selected: 0,
                };
            }
            Some("projects") => {
                let sessions = self.session_names.clone();
                self.state = PaletteState::ArgSelect {
                    arg_name: arg.name,
                    candidates: sessions.clone(),
                    values: sessions,
                    selected: 0,
                };
            }
            _ => {
                self.state = PaletteState::ArgInput {
                    arg_name: arg.name,
                    input: String::new(),
                };
            }
        }
    } else {
        self.execute_command();
    }
}
```

**Step 2: Build and test**

```bash
cd zchat-hub-plugin && cargo build --release && cargo test -p zchat-palette --target aarch64-apple-darwin
```

**Step 3: Commit**

```bash
git add zchat-hub-plugin/zchat-palette/src/main.rs
git commit -m "refactor: remove dead choices path from advance_args"
```

---

### Task 3: Add Rust test for `execute_command` arg building

Currently no test verifies the full flow: command selected → args collected → `build_cli_args` produces correct CLI invocation. Add integration-style tests in `commands.rs`.

**Files:**
- Modify: `zchat-hub-plugin/zchat-palette/src/commands.rs`

**Step 1: Add tests for the launcher flow scenarios**

```rust
#[test]
fn no_args_command() {
    // shutdown: no args → just "zchat shutdown"
    let args = build_cli_args("zchat", "", "shutdown", &[]);
    assert_eq!(args, vec!["zchat", "shutdown"]);
}

#[test]
fn required_positional_arg() {
    // agent create <name>: palette collects name
    let args = build_cli_args("zchat", "local", "agent create", &["agent0".into()]);
    assert_eq!(args, vec!["zchat", "--project", "local", "agent", "create", "agent0"]);
}

#[test]
fn runtime_source_arg() {
    // agent stop <name>: palette selects from running agents
    let args = build_cli_args("zchat", "local", "agent stop", &["alice-agent0".into()]);
    assert_eq!(args, vec!["zchat", "--project", "local", "agent", "stop", "alice-agent0"]);
}

#[test]
fn no_project_in_main_session() {
    // In main "zchat" session, project_name is empty → no --project flag
    let args = build_cli_args("zchat", "", "project create", &["myproj".into()]);
    assert_eq!(args, vec!["zchat", "project", "create", "myproj"]);
}
```

**Step 2: Run tests**

```bash
cd zchat-hub-plugin && cargo test -p zchat-palette --target aarch64-apple-darwin -v
```

**Step 3: Commit**

```bash
git add zchat-hub-plugin/zchat-palette/src/commands.rs
git commit -m "test: add launcher flow scenarios for build_cli_args"
```

---

### Task 4: Clean up `render_arg_input` — remove optional hint

Since palette only collects required args, the `(optional, Enter to skip)` hint is dead code.

**Files:**
- Modify: `zchat-hub-plugin/zchat-palette/src/main.rs`

**Step 1: Simplify render**

```rust
fn render_arg_input(&self, _cols: usize, arg_name: &str, input: &str) {
    println!(" {} | {}:", self.current_command, arg_name);
    println!(" > {}_", input);
}
```

Update the call site in `render()` to drop the `required` parameter.

**Step 2: Build and test**

```bash
cd zchat-hub-plugin && cargo build --release && cargo test -p zchat-palette --target aarch64-apple-darwin
```

**Step 3: Install and verify Python tests**

```bash
./bin/build-plugins && uv run pytest tests/unit/ -v
```

**Step 4: Commit**

```bash
git add zchat-hub-plugin/zchat-palette/src/main.rs
git commit -m "refactor: remove optional arg hint from palette render"
```

---

### Task 5: Remove `Choice` struct from `commands.rs`

`Choice` (value + label) was used for the old optional-arg-collection flow. Palette no longer uses it. Keep it in the `ArgInfo` struct for deserialization compatibility (CLI still emits `choices` in JSON for other consumers), but it's not used by the plugin.

**Decision: Keep `Choice` and `choices` field.** The `list-commands` JSON includes `choices` for shell completion and WeeChat integration. The Rust struct must be able to deserialize it even if the palette ignores it. No code change needed — just document it.

**Step 1: Add comment**

In `commands.rs`, update the doc comment on `choices`:

```rust
    /// Pre-resolved choices from CLI (for static sources like servers).
    /// Not used by palette (which launches interactive terminal panes),
    /// but retained for JSON deserialization compatibility with list-commands output.
    #[serde(default)]
    pub choices: Vec<Choice>,
```

**Step 2: Commit**

```bash
git add zchat-hub-plugin/zchat-palette/src/commands.rs
git commit -m "docs: clarify choices field is for JSON compat, not used by palette"
```

---

### Task 6: Verify all acceptance criteria

**Step 1: Build and install**

```bash
./bin/build-plugins
```

**Step 2: Manual test — no-args command (shutdown)**

```bash
zellij delete-session zchat 2>/dev/null
./bin/zchat-dev
# Ctrl-K → "shut" → Enter → floating terminal runs "zchat shutdown"
```

Expected: floating pane opens, runs shutdown, no `--project` flag.

**Step 3: Manual test — required positional arg (project create)**

```bash
# In zchat main session:
# Ctrl-K → "pr cr" → Enter → type "test0406" → Enter
# → floating terminal opens with "zchat project create test0406"
# → CLI shows server selection, channels prompt, etc.
```

Expected: full CLI interactive flow in terminal pane.

**Step 4: Commit test results note**

If all pass, update design doc acceptance criteria to mark all as validated:

```bash
git add docs/plans/2026-04-06-palette-interactive-pane-design.md
git commit -m "docs: mark all acceptance criteria as validated"
```

---

## Task Dependency Graph

```
Task 1 (simplify args) → Task 2 (remove choices path) → Task 4 (clean render)
Task 3 (add tests) — independent
Task 5 (document Choice) — independent
Task 1-5 → Task 6 (verify)
```

**Parallelizable:** Tasks 3 and 5 are independent of Tasks 1-2-4.
