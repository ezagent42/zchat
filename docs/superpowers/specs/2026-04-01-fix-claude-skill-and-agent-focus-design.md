# Fix Claude Skill Loading & Agent Focus/Hide Commands

**Date:** 2026-04-01

## Problem

### 1. /zchat Skill Not Loading in Agent Workspaces

After `zchat agent create`, the `/zchat` slash commands (reply, join, dm, broadcast) are unavailable. `claude plugin list` shows:

```
❯ zchat@ezagent42
  Status: ✘ failed to load
  Error: Plugin zchat not found in marketplace ezagent42
```

Root cause: the `ezagent42` marketplace may not be registered on the user's machine, or the plugin may not be installed for the current project. The agent's `start.sh` writes `"zchat@ezagent42": true` to `settings.local.json` but never ensures the marketplace and plugin are actually available.

### 2. No Way to Focus/Hide Agent Windows

Users cannot switch to a specific agent's tmux window or return to WeeChat from the CLI. The only tmux navigation is `project use` which attaches to the session level.

## Design

### Part 1: Auto-Install zchat Plugin in `start.sh`

#### Change: `zchat/cli/templates/claude/start.sh`

Add a plugin availability check before `exec claude`, after the `.claude/settings.local.json` generation block (line 46):

```bash
# --- Ensure zchat plugin is available ---
if ! claude plugin list 2>/dev/null | grep -q "zchat@ezagent42.*enabled"; then
  claude plugin marketplace add ezagent42/ezagent42 2>/dev/null || true
  claude plugin install zchat@ezagent42 --scope project 2>/dev/null || true
fi
```

**Behavior:**
- `claude plugin list | grep` checks if plugin is already enabled (~200ms)
- Only runs `marketplace add` + `plugin install` when missing
- `marketplace add` is user-scoped (registers once, all projects benefit)
- `plugin install --scope project` writes to the agent workspace's `.claude/settings.local.json`
- `|| true` prevents network failures from blocking agent startup
- Runs on every `create` and `restart`, auto-repairs corrupted `.claude/` directories

### Part 2: `focus` and `hide` Commands

#### Helper: `_tmux_switch(session_name, window_name)`

Both `focus` and `hide` need the same tmux switching logic. Extract to a helper in `app.py`:

```python
import subprocess

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

#### `zchat agent focus <name>`

Switch terminal to the specified agent's tmux window.

```python
@agent_app.command("focus")
def cmd_agent_focus(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
):
    """Switch to an agent's tmux window."""
    mgr = _get_agent_manager(ctx)
    agent = mgr.get_status(name)  # scopes internally, validates exists
    scoped = mgr.scoped(name)
    if agent["status"] == "offline":
        typer.echo(f"{scoped} is offline")
        raise typer.Exit(1)
    _tmux_switch(mgr.session_name, agent["window_name"])
```

#### `zchat agent hide <name|all>`

Switch terminal back to the WeeChat window.

```python
@agent_app.command("hide")
def cmd_agent_hide(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name or 'all'"),
):
    """Switch back to WeeChat window (hide agent view)."""
    mgr = _get_agent_manager(ctx)
    if name != "all":
        mgr.get_status(name)  # scopes internally, validates exists
    _tmux_switch(mgr.session_name, "weechat")
```

**Semantics:**
- `hide agent0` — validates agent0 exists, then switches to weechat
- `hide all` — no validation, directly switches to weechat
- Both cases end at the same destination: the `weechat` window

### Files Changed

| File | Change |
|------|--------|
| `zchat/cli/templates/claude/start.sh` | Add plugin auto-install check (4 lines) |
| `zchat/cli/app.py` | Add `import subprocess`, `_tmux_switch()` helper, `cmd_agent_focus`, `cmd_agent_hide` |
| `zchat/cli/agent_manager.py` | Add `session_name` public property (exposes `_tmux_session_name`) |
| `tests/unit/test_agent_focus_hide.py` | Unit tests for focus/hide argument handling |

### What Is NOT Changed

- `tmux.py` — existing `find_window()` is sufficient
- `settings.local.json` generation — already correct, just needs the plugin to actually exist
- Marketplace schema — `ezagent42/ezagent42` repo already has the zchat entry
