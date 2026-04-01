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
     - Busy with task → dispatch subagent to reply, don't interrupt current work
     - Reply requires interrupting current task → confirm with owner first
   - Other user DM → normal priority, reply when idle, brief ack + queue when busy
   - Channel @mention → reply in channel context
   - System messages (`__zchat_sys:`) → handle immediately
4. **Slash command reference** (brief table)
5. **SOUL file pointer** — Path to `soul.md` in workspace, read when needing role/style guidance

`server.py` reads `instructions.md` at startup and passes it as the MCP server `instructions` parameter. The `{agent_name}` placeholder is interpolated at runtime.

### Layer 2: SOUL File (soul.md)

A per-template role definition file, similar to SOUL.md conventions:

- Defines agent personality, communication style, domain expertise
- Different templates ship different souls (e.g., `templates/claude/soul.md`, `templates/coder/soul.md`)
- `start.sh` copies the template's `soul.md` into the agent workspace at creation time
- Claude reads it on-demand when needing style/role guidance, not loaded into every context

### Plugin Auto-Load Fix

Current issue: `start.sh` symlinks `.claude-plugin/` and `commands/` into the workspace, but the plugin isn't available until `/reload-plugins`.

Fix approach:
- Ensure symlinks are created before `claude` process starts (current order seems correct, investigate actual cause)
- If symlink-based detection is unreliable, switch to `--plugin-dir` flag pointing to the channel server package directory
- Verify `enabledPlugins` in `settings.local.json` matches the local plugin identity

## File Changes

### New files

1. **`zchat-channel-server/instructions.md`** — Full CHANNEL_INSTRUCTIONS content with `{agent_name}` placeholder, decision tree, command table, SOUL pointer
2. **`zchat/cli/templates/claude/soul.md`** — Default soul template for the `claude` agent type

### Modified files

3. **`zchat-channel-server/server.py`** — Replace hardcoded `CHANNEL_INSTRUCTIONS` string with file read of `instructions.md`, interpolate `{agent_name}`
4. **`zchat/cli/templates/claude/start.sh`** — Copy `soul.md` from template to agent workspace; fix plugin loading to work without `/reload-plugins`

### Skill files (no change needed)

`commands/dm.md`, `reply.md`, `join.md`, `broadcast.md` remain focused on send-only behavior. Message routing is handled by `instructions.md`, not individual skills.

## Non-Goals

- No changes to the MCP server protocol or tool definitions
- No changes to the zchat-protocol submodule
- No changes to WeeChat plugin
- SOUL file is not mandatory — agent functions without it, just lacks personality customization
