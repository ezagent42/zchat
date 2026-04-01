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
3. **Message handling strategy — subagent dispatch model:**

   **Why subagent, not inline response:** 主 agent 可能正在执行长时间的 tool use（跑测试、大量文件操作等），期间无法被中断。如果用 inline response，用户要等 tool use 完成后才能收到回复，可能等待数分钟。Subagent 可以立即并行响应。

   **Default behavior:** 收到 IRC 消息时，使用 Claude Code 的 Agent tool spawn 一个 subagent 处理回复。主 agent 不中断当前工作。

   Subagent 的上下文：
   - 消息内容本身（来自谁、说了什么）
   - `soul.md`（角色定义，由 subagent 自行 Read）
   - 主 agent 的对话历史 — 通过 Read session JSONL 文件获取（`~/.claude/projects/<project-hash>/<session-id>.jsonl`），了解主 agent 当前正在做什么
   - 可用工具：reply tool（发送 IRC 回复）、Read tool（读取 soul.md 和 session JSONL）

   **Message priority:**
   - **Owner DM（agent 名字前缀用户）** → 高优先级，立即 dispatch subagent
   - **Other user DM** → 正常优先级，dispatch subagent
   - **Channel @mention** → dispatch subagent，回复到对应频道
   - **System messages（`__zchat_sys:`）** → 主 agent 直接处理（不用 subagent，系统消息需要主 agent 状态）

   **是否需要深入处理** → 由 `soul.md` 角色定义决定。instructions.md 只定义 "spawn subagent 快速回复" 的默认行为。soul.md 可以覆盖（例如"收到代码审查请求时，暂停当前任务全力处理"）。

   **Idle 状态优化:** 如果主 agent 空闲（无进行中的任务），可以直接回复而不 spawn subagent，避免不必要的 token 开销。
4. **Slash command reference** (brief table)
5. **SOUL file pointer** — instructs Claude to `Read ./soul.md` at session start for role/style guidance, and re-read when encountering unfamiliar situations

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
- **可覆盖 instructions.md 的默认消息处理行为** — 例如定义何时需要深入处理而非 quick response
- Different templates ship different souls (e.g., `templates/claude/soul.md`, `templates/coder/soul.md`)
- `start.sh` copies the template's `soul.md` into the agent workspace root at creation time
- CHANNEL_INSTRUCTIONS instructs Claude to read `./soul.md` at session start
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
