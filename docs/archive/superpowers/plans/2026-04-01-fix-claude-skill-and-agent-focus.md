# Fix Claude Skill Loading & Agent Focus/Hide — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to implement this plan.

**Goal:** Auto-install zchat plugin on agent startup; add `focus`/`hide` CLI commands.

**Spec:** `docs/superpowers/specs/2026-04-01-fix-claude-skill-and-agent-focus-design.md`

---

## Chunk 1: Plugin Auto-Install in start.sh

### Task 1: Add plugin check to start.sh

**Files:**
- Modify: `zchat/cli/templates/claude/start.sh`

- [ ] **Step 1: Add plugin auto-install block**

In `start.sh`, after the `settings.local.json` generation (after line 46, before the `# --- Build .mcp.json ---` comment), insert:

```bash
# --- Ensure zchat plugin is available ---
if ! claude plugin list 2>/dev/null | grep -q "zchat@ezagent42.*enabled"; then
  claude plugin marketplace add ezagent42/ezagent42 2>/dev/null || true
  claude plugin install zchat@ezagent42 --scope project 2>/dev/null || true
fi
```

- [ ] **Step 2: Commit**

```bash
git add zchat/cli/templates/claude/start.sh
git commit -m "fix(template): auto-install zchat plugin on agent startup"
```

## Chunk 2: Agent Focus/Hide Commands

### Task 2: Add `session_name` property to AgentManager

**Files:**
- Modify: `zchat/cli/agent_manager.py`

- [ ] **Step 1: Add public property**

After the existing `tmux_session` property (line 49), add:

```python
@property
def session_name(self) -> str:
    return self._tmux_session_name
```

- [ ] **Step 2: Commit**

```bash
git add zchat/cli/agent_manager.py
git commit -m "refactor(agent): expose session_name as public property"
```

### Task 3: Add `_tmux_switch` helper + `focus`/`hide` commands to app.py

**Files:**
- Modify: `zchat/cli/app.py`

- [ ] **Step 1: Add `import subprocess` to app.py**

Add `import subprocess` in the imports section (after `import time`).

- [ ] **Step 2: Add `_tmux_switch` helper**

Add after `_get_tmux_session()` (around line 55):

```python
def _tmux_switch(session_name: str, window_name: str):
    """Switch to a tmux window. Attach if outside tmux, select-window if inside."""
    target = f"{session_name}:{window_name}"
    if os.environ.get("TMUX"):
        result = subprocess.run(["tmux", "select-window", "-t", target], capture_output=True)
    else:
        result = subprocess.run(["tmux", "attach", "-t", target])
    if result.returncode != 0:
        typer.echo(f"Error: tmux window '{window_name}' not found")
        raise typer.Exit(1)
```

- [ ] **Step 3: Add `cmd_agent_focus` command**

Add after `cmd_agent_restart` (end of agent commands):

```python
@agent_app.command("focus")
def cmd_agent_focus(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
):
    """Switch to an agent's tmux window."""
    mgr = _get_agent_manager(ctx)
    agent = mgr.get_status(name)
    scoped = mgr.scoped(name)
    if agent["status"] == "offline":
        typer.echo(f"{scoped} is offline")
        raise typer.Exit(1)
    _tmux_switch(mgr.session_name, agent["window_name"])
```

- [ ] **Step 4: Add `cmd_agent_hide` command**

Add after `cmd_agent_focus`:

```python
@agent_app.command("hide")
def cmd_agent_hide(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name or 'all'"),
):
    """Switch back to WeeChat window (hide agent view)."""
    mgr = _get_agent_manager(ctx)
    if name != "all":
        mgr.get_status(name)
    _tmux_switch(mgr.session_name, "weechat")
```

- [ ] **Step 5: Commit**

```bash
git add zchat/cli/app.py
git commit -m "feat(agent): add focus and hide commands for tmux window switching"
```

## Chunk 3: Tests & Verification

### Task 4: Unit tests for focus/hide

**Files:**
- Create: `tests/unit/test_agent_focus_hide.py`

- [ ] **Step 1: Write unit tests**

Test cases:
- `test_focus_offline_agent_exits` — mock `get_status` returning offline, verify exit code 1
- `test_focus_calls_tmux_select_inside_tmux` — set `TMUX` env, mock subprocess, verify `select-window` called
- `test_focus_calls_tmux_attach_outside_tmux` — unset `TMUX`, mock subprocess, verify `attach` called
- `test_hide_validates_agent_name` — mock `get_status` raising ValueError, verify error
- `test_hide_all_skips_validation` — `name="all"`, verify `get_status` not called
- `test_tmux_switch_error_handling` — mock subprocess returning non-zero, verify error message

- [ ] **Step 2: Run unit tests**

Run: `uv run pytest tests/unit/test_agent_focus_hide.py -v`

Expected: All pass

- [ ] **Step 3: Commit tests**

```bash
git add tests/unit/test_agent_focus_hide.py
git commit -m "test(agent): add unit tests for focus and hide commands"
```

### Task 5: Run full test suite

- [ ] **Step 1: Run all unit tests**

Run: `uv run pytest tests/unit/ -v`

Expected: All pass

- [ ] **Step 2: Run E2E tests**

Run: `uv run pytest tests/e2e/ -v -m e2e`

Expected: All pass
