# Better Skill: Context-Aware Message Handling

## Problem

Current zchat skills only define how to send messages. When replies arrive, Claude lacks routing rules and falls back to generic behavior (e.g., asking "Would you like me to reply?" instead of responding directly). Additionally, the plugin requires a manual `/reload-plugins` after Claude Code starts.

## Design

### Two-Layer Instruction Architecture

| Layer | Content | Loading | Location |
|---|---|---|---|
| **CHANNEL_INSTRUCTIONS** | Message format + general routing strategy + command list | MCP server instructions, always in context | `zchat-channel-server/instructions.md` → read by `server.py` at startup |
| **SOUL file** | Role definition, communication style, domain behavior | On-demand Read by Claude | Agent workspace `soul.md`, generated from template |

### Layer 1: CHANNEL_INSTRUCTIONS (instructions.md)

Extracted from `server.py` hardcoded string into a standalone markdown file. Contains:

1. **Message format** — How notifications arrive (`<channel>` tags, `chat_id` conventions)
2. **Owner detection** — Agent name prefix determines the owner (e.g., `alice-agent0` → owner is `alice`)
3. **Message priority decision tree:**
   - Owner DM → high priority
     - Idle → reply directly
     - Busy with task → use Claude Code's built-in Agent tool to dispatch a subagent for reply, continue current work
     - Reply requires interrupting current task → confirm with owner first
   - Other user DM → normal priority, reply when idle, brief ack + queue when busy
   - Channel @mention → reply in channel context
   - System messages (`__zchat_sys:`) → handle immediately
4. **Slash command reference** (brief table)
5. **SOUL file pointer** — instructs Claude to `Read ./soul.md` when needing role/style guidance

Note: "dispatch subagent" refers to Claude Code's native Agent tool, not zchat agent creation. No new MCP tools needed.

### Placeholder interpolation

`instructions.md` uses `string.Template` syntax (`$agent_name`) for variable substitution. This avoids conflicts with curly braces in markdown code blocks.

Variables interpolated by `server.py` at startup:
- `$agent_name` — the agent's IRC nick (from `AGENT_NAME` env var)

### File packaging

`instructions.md` must be included in the Python wheel. Add to `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["."]
only-include = ["server.py", "message.py", "instructions.md"]
```

`server.py` reads the file using `Path(__file__).parent / "instructions.md"`, which works for both editable installs and wheel installs.

### Layer 2: SOUL File (soul.md)

A per-template role definition file, similar to SOUL.md conventions:

- Defines agent personality, communication style, domain expertise
- Different templates ship different souls (e.g., `templates/claude/soul.md`, `templates/coder/soul.md`)
- `start.sh` copies the template's `soul.md` into the agent workspace root at creation time
- CHANNEL_INSTRUCTIONS tells Claude: "For role and communication style guidance, read `./soul.md` in your workspace if it exists."
- Claude uses its native Read tool to access the file — no new MCP tools needed

### Plugin Auto-Load Fix

Current issue: `start.sh` symlinks `.claude-plugin/` and `commands/` into the workspace, but the plugin isn't available until `/reload-plugins`.

Root cause investigation needed during implementation. Likely causes and fixes:

1. **Plugin identity mismatch** — `settings.local.json` enables `"zchat@ezagent42"` (marketplace identity), but the local symlinked plugin may have a different identity. Fix: align the identities or use local plugin detection.
2. **Symlink not followed** — Claude Code's plugin loader may not follow symlinks. Fix: copy files instead of symlink, or use `--plugin-dir` flag.
3. **Race condition** — MCP server connects before plugin loader scans workspace. Fix: adjust startup order.

Acceptance criteria: after `zchat agent create`, slash commands (`/zchat:dm`, `/zchat:reply`, etc.) work immediately without `/reload-plugins`.

Implementation approach: investigate the actual cause first, then apply the appropriate fix. If the root cause is unclear, switch from symlinks to copying the plugin files directly.

## File Changes

### New files

1. **`zchat-channel-server/instructions.md`** — Full CHANNEL_INSTRUCTIONS content with `$agent_name` placeholder, decision tree, command table, SOUL pointer
2. **`zchat/cli/templates/claude/soul.md`** — Default soul template for the `claude` agent type

### Modified files

3. **`zchat-channel-server/server.py`** — Replace hardcoded `CHANNEL_INSTRUCTIONS` string with: read `instructions.md` via `Path(__file__).parent`, interpolate with `string.Template`
4. **`zchat-channel-server/pyproject.toml`** — Add `instructions.md` to `only-include` list
5. **`zchat/cli/templates/claude/start.sh`** — Copy `soul.md` from template to agent workspace; fix plugin loading

### Skill files (no change needed)

`commands/dm.md`, `reply.md`, `join.md`, `broadcast.md` remain focused on send-only behavior. Message routing is handled by `instructions.md`, not individual skills.

## Test Plan

- **Unit test:** `server.py` loads `instructions.md` and interpolates `$agent_name` correctly
- **Unit test:** `start.sh` copies `soul.md` into agent workspace
- **E2E test:** agent starts, receives a DM from owner, replies directly without asking "Would you like me to reply?"
- **E2E test:** plugin slash commands work immediately after `zchat agent create` (no `/reload-plugins`)

## Non-Goals

- No changes to the MCP server protocol or tool definitions
- No changes to the zchat-protocol submodule
- No changes to WeeChat plugin
- SOUL file is not mandatory — agent functions without it, just lacks personality customization
