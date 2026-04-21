# zchat Restructuring Design

**Date:** 2026-03-27
**Status:** Draft

## Summary

Restructure the current `weechat-claude` monorepo in two phases: first rename + implement the WeeChat plugin (in monorepo), then split into independent repos. This spec covers Phase 1 and Phase 2 (in-monorepo work). Phase 3 (repo split) is deferred.

## Target Architecture (Final State)

Three independent repos under `ezagent42` org:

| Repo | Content | Language |
|------|---------|----------|
| `ezagent42/zchat` | CLI + protocol spec + e2e tests | Python |
| `ezagent42/claude-zchat-channel` | Claude Code plugin (MCP server, IRC bridge) | Python |
| `ezagent42/weechat-zchat-plugin` | WeeChat Python script | Python |

No shared code dependencies — each repo implements the zchat protocol independently, referencing `zchat.protocol` as the authoritative spec.

## Phase 1: Rename + Protocol Refactor (in monorepo)

### 1.1 Package Restructure

```
zchat/                             # repo root (renamed from weechat-claude)
├── zchat/                         # Python package
│   ├── __init__.py
│   ├── protocol/                  # Protocol specification (authoritative)
│   │   ├── __init__.py            # PROTOCOL_VERSION = "0.1"
│   │   ├── naming.py             # AGENT_SEPARATOR, scoped_name()
│   │   └── sys_messages.py       # __zchat_sys: prefix, encode/decode
│   └── cli/                      # CLI tool (renamed from wc-agent)
│       ├── __init__.py
│       ├── app.py                # Typer CLI entry point (renamed from cli.py)
│       ├── agent_manager.py      # Agent lifecycle
│       ├── irc_manager.py        # IRC daemon & WeeChat management
│       └── project.py            # Project config (~/.zchat/projects/)
├── weechat-channel-server/        # MCP server (stays in-place until Phase 3)
│   ├── server.py
│   ├── message.py
│   └── pyproject.toml
├── weechat-zchat-plugin/          # NEW: WeeChat Python script (Phase 2)
│   └── zchat.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── docs/
├── ergo.yaml
├── start.sh
├── stop.sh
├── pyproject.toml                 # [project.scripts] zchat = "zchat.cli.app:app"
└── README.md
```

### 1.2 Naming Changes

| Old | New | Location |
|-----|-----|----------|
| `wc-agent` (CLI) | `zchat` | pyproject.toml `[project.scripts]` |
| `wc_agent` (Python package) | `zchat.cli` | all imports |
| `wc_protocol` (Python package) | `zchat.protocol` | all imports |
| `__wc_sys:` (wire prefix) | `__zchat_sys:` | sys_messages.py, server.py |
| `~/.wc-agent/` | `~/.zchat/` | project.py |
| `~/.local/state/wc-agent/` | `~/.local/state/zchat/` | agent_manager.py `DEFAULT_STATE_FILE` |
| `.wc-agent` (project marker file) | `.zchat` | project.py `resolve_project()` |
| `WC_AGENT_HOME` | `ZCHAT_HOME` | agent_manager.py, project.py, zchat.sh |
| `WC_TMUX_SESSION` | `ZCHAT_TMUX_SESSION` | cli.py, agent_manager.py |
| `WC_PROJECT_DIR` | `ZCHAT_PROJECT_DIR` | agent_manager.py |
| `weechat-claude` (tmux session) | `zchat-{project}` (e.g. `zchat-local`) | cli.py, agent_manager.py, start.sh, stop.sh |
| `wc-agent.sh` (wrapper) | `zchat.sh` | root dir |
| `python -m wc_agent.cli` | `python -m zchat.cli` | start.sh, stop.sh, zchat.sh |

### 1.3 Protocol Changes

**`zchat/protocol/__init__.py`:**
```python
PROTOCOL_VERSION = "0.1"
```

**`zchat/protocol/sys_messages.py`:**
- Rename `IRC_SYS_PREFIX` from `"__wc_sys:"` to `"__zchat_sys:"`
- All functions remain the same

**`commands.json`:**
- Keep as OpenAPI spec (standard format), update `wc-agent` references to `zchat`

### 1.4 Channel Server Updates

- Update imports: `from wc_protocol.` → `from zchat.protocol.`
- **Remove `create_agent` tool**: delete `_handle_create_agent()`, remove from `handle_list_tools()` and `handle_call_tool()`, update `CHANNEL_INSTRUCTIONS` to remove create_agent references
- Update `__wc_sys:` references to `__zchat_sys:`
- Update `channel_server_dir` resolution in `agent_manager.py` to use monorepo-relative path (Phase 3 will switch to plugin-install-based discovery)

### 1.5 CLI Updates

- `zchat/cli/app.py`: entry point, `zchat` command
- `zchat/cli/__main__.py`: add so `python -m zchat.cli` works
- `agent_manager.py`: update tmux session name, state paths, env var names, `DEFAULT_STATE_FILE` constant
- `agent_manager.py`: remove `from_env()` classmethod (dead code after `create_agent` removal)
- `irc_manager.py`: update WeeChat launch config, tmux references
- `project.py`: update config dir `~/.zchat/`, rename `.wc-agent` marker to `.zchat`
- Delete `config.py` (dead code; `project.py:load_project_config()` duplicates it)

### 1.6 Test & Script Updates

- All test imports: `wc_agent` → `zchat.cli`, `wc_protocol` → `zchat.protocol`
- `start.sh` / `stop.sh`: update CLI calls, tmux session names
- `wc-agent.sh` → `zchat.sh`
- `pytest.ini`: update if needed

## Phase 2: Implement weechat-zchat-plugin

### 2.1 Overview

A WeeChat Python script that bridges WeeChat native UI to the zchat agent system. Lives in `weechat-zchat-plugin/` within the monorepo during development.

### 2.2 Initial Features

**`/agent` command** (core — bridges WeeChat to zchat CLI):
- `/agent create <name> [--workspace <path>]` → `subprocess.run(["zchat", "agent", "create", ...])`
- `/agent stop <name>` → `subprocess.run(["zchat", "agent", "stop", ...])`
- `/agent list` → `subprocess.run(["zchat", "agent", "list"])`
- `/agent restart <name>` → `subprocess.run(["zchat", "agent", "restart", ...])`
- `/agent send <name> <message>` → `subprocess.run(["zchat", "agent", "send", ...])`

**@mention highlighting:**
- Detect agent names in nicklist (pattern: `{user}-{name}`)
- Apply WeeChat highlight rules for @mentions directed at user

**Agent status display:**
- Monitor IRC JOIN/PART/QUIT for agent nicks
- Display agent online/offline status (nicklist group or bar item)

**System message handling:**
- Decode `__zchat_sys:` messages in channel
- Display human-readable status instead of raw JSON
- Optionally hide system messages from chat view

### 2.3 Protocol Implementation

Implements zchat protocol independently (no Python import from zchat package):
- `AGENT_SEPARATOR = "-"`
- `ZCHAT_SYS_PREFIX = "__zchat_sys:"`
- `scoped_name()` logic
- System message decode (for display purposes)

### 2.4 Installation

```
~/.weechat/python/autoload/zchat.py  (symlink or copy)
```

Or via WeeChat command:
```
/script load zchat.py
```

### 2.5 WeeChat API Integration

- `weechat.register("zchat", ...)` — script registration
- `weechat.hook_command("agent", ...)` — command registration
- `weechat.hook_signal("*,irc_in_join", ...)` — presence tracking (JOIN/PART/QUIT)
- `weechat.hook_modifier("irc_in_privmsg", ...)` — system message filtering
- `weechat.bar_item_new(...)` — agent status bar item

## Phase 3: Repo Split (Deferred)

Not in scope for this implementation cycle. High-level plan for reference:

1. **Extract `claude-zchat-channel`** → `ezagent42/claude-zchat-channel`
   - Copy `weechat-channel-server/` content
   - Add `.claude-plugin/plugin.json`, skills/, `.mcp.json` (feishu pattern)
   - Reimplement protocol inline (remove zchat.protocol import)
   - Register in `ezagent42/ezagent42` marketplace
   - Remove from monorepo

2. **Extract `weechat-zchat-plugin`** → `ezagent42/weechat-zchat-plugin`
   - Move `weechat-zchat-plugin/zchat.py` to own repo
   - Already has independent protocol implementation
   - Remove from monorepo

3. **Rename repo** `weechat-claude` → `zchat`

4. **Update e2e tests** to use plugin install mechanism

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Protocol as Python module, not shared lib | Each consumer implements independently; avoids cross-repo dependency |
| `PROTOCOL_VERSION` constant | Detect protocol mismatches across independently-implemented repos |
| Remove `create_agent` from channel server | Agent creation is CLI/WeeChat concern, not channel bridge concern |
| `__zchat_sys:` prefix rename | Consistent branding; breaking change acceptable since no external consumers yet |
| WeeChat plugin before repo split | Get the core experience right before splitting at unstable boundaries |
| Plugin calls zchat CLI via subprocess | Clean separation; plugin doesn't import zchat internals |
| Keep Python for channel server | Working implementation exists; no benefit to TypeScript rewrite |

## Out of Scope

- TypeScript/language migration
- New MCP tools beyond current set (minus `create_agent`)
- Changes to IRC protocol
- Marketplace registration (Phase 3)
- Repo rename on GitHub (Phase 3)
