# Better Skill: Context-Aware Message Handling — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded CHANNEL_INSTRUCTIONS with modular instructions.md + soul.md, implementing subagent-based message dispatch and fixing plugin auto-load.

**Architecture:** Two-layer instruction system — `instructions.md` (always in MCP context, handles message routing via subagent dispatch) + `soul.md` (on-demand personality file, per-template). Server.py reads instructions.md at startup with string.Template interpolation.

**Tech Stack:** Python 3.11+, MCP server (mcp[cli]), hatchling build, pytest

**Spec:** `docs/superpowers/specs/2026-04-01-better-skill-design.md`

---

## Chunk 1: Extract CHANNEL_INSTRUCTIONS to instructions.md

### Task 1: Create instructions.md with message routing strategy

**Files:**
- Create: `zchat-channel-server/instructions.md`

- [ ] **Step 1: Write instructions.md**

```markdown
You are $agent_name, a Claude Code agent connected to an IRC chat system.

## Message Format

Messages arrive as `<channel source="zchat-channel" chat_id="..." user="..." ts="...">content</channel>`.
- `chat_id` starting with `#` is a channel message (e.g. `#general`)
- `chat_id` without `#` is a private message from that user

## Owner Detection

Your owner is determined by your agent name prefix. For example, if you are `alice-agent0`, your owner is `alice`. Owner messages have highest priority.

## Message Handling Strategy

When you receive an IRC message (channel notification), handle it based on your current state:

### If idle (no task in progress)

Reply directly using the `reply` tool with the same `chat_id`. No need to spawn a subagent.

### If busy (task in progress)

Use the Agent tool to spawn a subagent to handle the reply. Do NOT interrupt your current work. The subagent should:

1. Read `./soul.md` for role and communication style guidance (if the file exists)
2. Read recent session context: `tail -100 ~/.claude/projects/<project-hash>/<session-id>.jsonl` via Bash tool
3. Use the `reply` tool (MCP tool `mcp__zchat-channel__reply`) to respond

In your dispatch prompt to the subagent, include:
- What you are currently working on (brief summary)
- The incoming message content and sender
- The `chat_id` to reply to
- Instruction to read `./soul.md` and session JSONL tail for additional context

### System messages

Messages with `__zchat_sys:` prefix are system control messages. Handle these directly (not via subagent) — they may require your state (e.g., stop requests, status queries).

### Message priority

| Source | Priority | Handling |
|--------|----------|----------|
| Owner DM | High | Immediate — direct reply if idle, subagent if busy |
| Other user DM | Normal | Direct reply if idle, subagent if busy |
| Channel @mention | Normal | Reply in channel context (same rules) |
| System message | Critical | Always handle directly, never delegate |

### Deep processing

By default, keep replies quick and conversational. Whether a message requires deep processing (pausing current task, extended analysis) is determined by `./soul.md`. If no soul.md exists, always use quick response mode.

## SOUL File

At session start, read `./soul.md` if it exists. This file defines your role, communication style, and domain behavior. It may override the default message handling strategy above (e.g., "pause current task for code review requests").

Re-read `./soul.md` when encountering unfamiliar situations or role-specific decisions.

## Available Commands

| Command | Description |
|---------|-------------|
| `/zchat:reply -c #general -t "hello"` | Reply to a channel or user |
| `/zchat:join -c dev` | Join an IRC channel |
| `/zchat:dm -u alice -t "hey"` | Send a private message |
| `/zchat:broadcast -t "deploying"` | Send to all joined channels |

When these commands are invoked, follow the command instructions to call the appropriate MCP tool. You can also call `reply` and `join_channel` tools directly when responding to channel messages.
```

- [ ] **Step 2: Commit**

```bash
git add zchat-channel-server/instructions.md
git commit -m "feat: add instructions.md with subagent dispatch message handling"
```

### Task 2: Update server.py to load instructions.md

**Files:**
- Modify: `zchat-channel-server/server.py:1-10` (imports)
- Modify: `zchat-channel-server/server.py:210-233` (CHANNEL_INSTRUCTIONS)
- Test: `zchat-channel-server/tests/test_channel_server.py`

- [ ] **Step 1: Write the failing test**

Update `test_channel_server.py` — replace the import of `CHANNEL_INSTRUCTIONS` constant with a test for the new loading function:

```python
from server import load_instructions

def test_load_instructions_interpolates_agent_name():
    result = load_instructions("alice-agent0")
    assert "alice-agent0" in result
    assert "$agent_name" not in result

def test_load_instructions_contains_routing_rules():
    result = load_instructions("test-agent")
    assert "/zchat:reply" in result
    assert "/zchat:dm" in result
    assert "/zchat:join" in result
    assert "/zchat:broadcast" in result
    assert "chat_id" in result
    assert "subagent" in result.lower() or "Agent tool" in result

def test_load_instructions_contains_soul_pointer():
    result = load_instructions("test-agent")
    assert "soul.md" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd zchat-channel-server && uv run pytest tests/test_channel_server.py::test_load_instructions_interpolates_agent_name -v`
Expected: FAIL — `load_instructions` not defined

- [ ] **Step 3: Implement load_instructions in server.py**

Replace the hardcoded `CHANNEL_INSTRUCTIONS` f-string (lines 210-233) with:

```python
from pathlib import Path
from string import Template

def load_instructions(agent_name: str) -> str:
    """Load instructions.md and interpolate agent_name."""
    path = Path(__file__).parent / "instructions.md"
    tmpl = Template(path.read_text(encoding="utf-8"))
    return tmpl.safe_substitute(agent_name=agent_name)
```

Update `create_server()` to use it:

```python
def create_server():
    instructions = load_instructions(AGENT_NAME)
    server = Server("zchat-channel", instructions=instructions)
    return server
```

Remove the old `CHANNEL_INSTRUCTIONS` variable entirely.

- [ ] **Step 4: Remove old test and import**

Delete the following from `test_channel_server.py`:
- Line 6: `from server import CHANNEL_INSTRUCTIONS` (import)
- Lines 50-57: the entire `test_channel_instructions_mention_slash_commands` function

These are replaced by the new `test_load_instructions_*` tests written in Step 1.

- [ ] **Step 5: Run all tests to verify they pass**

Run: `cd zchat-channel-server && uv run pytest tests/test_channel_server.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd zchat-channel-server
git add server.py tests/test_channel_server.py
git commit -m "refactor: load CHANNEL_INSTRUCTIONS from instructions.md with Template interpolation"
```

### Task 3: Update pyproject.toml to include instructions.md in wheel

**Files:**
- Modify: `zchat-channel-server/pyproject.toml:27`

- [ ] **Step 1: Update only-include**

Change line 27 from:
```toml
only-include = ["server.py", "message.py"]
```
to:
```toml
only-include = ["server.py", "message.py", "instructions.md"]
```

- [ ] **Step 2: Verify build includes the file**

Run: `cd zchat-channel-server && uv build && unzip -l dist/*.whl | grep instructions`
Expected: `instructions.md` appears in the wheel contents

- [ ] **Step 3: Commit**

```bash
cd zchat-channel-server
git add pyproject.toml
git commit -m "build: include instructions.md in wheel package"
```

---

## Chunk 2: Add soul.md template and start.sh integration

### Task 4: Create default soul.md template

**Files:**
- Create: `zchat/cli/templates/claude/soul.md`

- [ ] **Step 1: Write soul.md**

```markdown
# Soul: Claude Code Agent

## Role

You are a helpful Claude Code agent participating in an IRC-based collaboration system. You assist your owner with software engineering tasks while being available for communication with other users.

## Communication Style

- Be concise and direct in IRC messages — IRC is a chat medium, not a document
- Use the same language as the person messaging you
- When busy, briefly explain what you're working on before addressing the message
- For technical discussions, include relevant code snippets or file references

## Message Handling Overrides

The default message handling strategy (in your MCP instructions) uses quick responses. Override this default in these cases:

- **Code review requests** — If someone asks you to review code or a PR, acknowledge receipt and add it to your task queue. Do not attempt a full review in a quick reply.
- **Bug reports from owner** — Treat as high priority. If idle, investigate immediately. If busy, finish current task first but prioritize it next.
- **Casual conversation** — Keep it brief and friendly. Do not over-explain or be overly formal.
```

- [ ] **Step 2: Commit**

```bash
git add zchat/cli/templates/claude/soul.md
git commit -m "feat: add default soul.md template for claude agent type"
```

### Task 5: Update start.sh to copy soul.md into workspace

**Files:**
- Modify: `zchat/cli/templates/claude/start.sh`

- [ ] **Step 1: Locate the template directory in start.sh**

The start script already resolves `CHANNEL_PKG` for the channel server. For soul.md, we need the template directory. Since `start.sh` itself is in the template directory, use `$(dirname "$0")`:

Add after the `# --- Claude settings with SessionStart hook ---` section (before `.claude/settings.local.json` generation):

```bash
# --- Copy soul.md from template ---
TEMPLATE_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$TEMPLATE_DIR/soul.md" ]; then
  cp "$TEMPLATE_DIR/soul.md" ./soul.md
fi
```

- [ ] **Step 2: Verify start.sh syntax**

Run: `bash -n zchat/cli/templates/claude/start.sh`
Expected: No errors

- [ ] **Step 3: Test soul.md copy behavior**

```bash
# Create a temp workspace and simulate start.sh's soul.md copy logic
TMPDIR=$(mktemp -d)
TEMPLATE_DIR="$(cd zchat/cli/templates/claude && pwd)"
if [ -f "$TEMPLATE_DIR/soul.md" ]; then
  cp "$TEMPLATE_DIR/soul.md" "$TMPDIR/soul.md"
fi
test -f "$TMPDIR/soul.md" && echo "PASS: soul.md copied" || echo "FAIL: soul.md not found"
rm -rf "$TMPDIR"
```

Expected: `PASS: soul.md copied`

- [ ] **Step 4: Commit**

```bash
git add zchat/cli/templates/claude/start.sh
git commit -m "feat: copy soul.md from template to agent workspace on create"
```

---

## Chunk 3: Fix plugin auto-load

### Task 6: Investigate and fix plugin loading

**Files:**
- Modify: `zchat/cli/templates/claude/start.sh`

This task requires investigation. The acceptance criteria is: slash commands work immediately after `zchat agent create` without `/reload-plugins`.

- [ ] **Step 1: Investigate root cause**

Check these hypotheses in order:

1. **Symlink issue** — Does Claude Code follow symlinks for `.claude-plugin/` and `commands/`?
   - Test: replace `ln -sfn` with `cp -r` in start.sh and see if plugins load
2. **Plugin identity mismatch** — Does `settings.local.json` reference `"zchat@ezagent42"` while the local plugin has no marketplace identity?
   - Test: check if removing `enabledPlugins` from settings.local.json and relying on local detection works
3. **Timing** — Is the `claude` process starting before symlinks are fully in place?
   - The current start.sh creates symlinks before `exec claude`, so timing should not be the issue

- [ ] **Step 2: Apply fix based on findings**

Most likely fix: replace symlinks with file copies. Change in start.sh:

```bash
# Replace:
# ln -sfn "$CHANNEL_PKG/.claude-plugin" .claude-plugin
# ln -sfn "$CHANNEL_PKG/commands" commands

# With:
if [ -n "$CHANNEL_PKG" ] && [ -d "$CHANNEL_PKG/.claude-plugin" ]; then
  cp -r "$CHANNEL_PKG/.claude-plugin" .claude-plugin
  cp -r "$CHANNEL_PKG/commands" commands
fi
```

If copies don't fix it either, try `--plugin-dir` flag:
```bash
exec claude --permission-mode bypassPermissions \
  --dangerously-load-development-channels server:zchat-channel \
  --plugin-dir "$CHANNEL_PKG"
```

- [ ] **Step 3: Verify fix with E2E test**

Run: `uv run pytest tests/e2e/ -v -m e2e -k plugin` (if E2E test exists)
Or manual: `zchat agent create test-agent`, then check if `/zchat:dm` is immediately available.

- [ ] **Step 4: Commit**

```bash
git add zchat/cli/templates/claude/start.sh
git commit -m "fix: plugin auto-load without /reload-plugins"
```

---

## Chunk 4: Tests

### Task 7: Unit tests for instructions loading

Already covered in Task 2.

### Task 8: E2E test for message handling behavior

**Files:**
- Modify or create: `tests/e2e/test_agent_message.py` (if E2E infra supports it)

- [ ] **Step 1: Check existing E2E test structure**

Run: `ls tests/e2e/` to see existing E2E tests and understand the patterns.

- [ ] **Step 2: Add E2E test for DM reply behavior**

This depends on the existing E2E framework. The test should:
1. Create an agent via `zchat agent create`
2. Send a DM to the agent via IRC
3. Verify the agent replies directly (not "Would you like me to reply?")
4. Verify reply content is contextual

If the E2E framework doesn't support IRC message interception, document this as a manual test case.

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "test: add E2E test for agent DM reply behavior"
```

---

## Chunk 5: Final verification

### Task 9: Run full test suite

- [ ] **Step 1: Run channel-server unit tests**

Run: `cd zchat-channel-server && uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Run CLI unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 3: Run E2E tests**

Run: `uv run pytest tests/e2e/ -v -m e2e`
Expected: All PASS

- [ ] **Step 4: Final commit and summary**

If any fixes were needed during verification, commit them. Then summarize all changes.
