# zchat Channel Skills Plugin — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Claude Code plugin (`zchat@ezagent42`) that exposes `/zchat:reply`, `/zchat:join`, `/zchat:dm`, `/zchat:broadcast` commands, registered via the `ezagent42` marketplace.

**Architecture:** The plugin lives inside `weechat-channel-server/` (the existing MCP channel server directory), using `git-subdir` source type so the marketplace can point to a subdirectory of the zchat repo without extracting a separate repo. The `ezagent42/ezagent42` GitHub repo is renamed to `ezagent42/ezagent42-marketplace` and registered as the `ezagent42` marketplace in Claude Code.

**Tech Stack:** Claude Code plugin system (markdown commands with frontmatter), Python (server.py instruction update)

---

## File Structure

```
weechat-channel-server/                  # Existing MCP server — becomes plugin root
├── .claude-plugin/
│   └── plugin.json                      # Plugin manifest (name: "zchat")
├── commands/
│   ├── reply.md                         # /zchat:reply -c #general -t "hello"
│   ├── join.md                          # /zchat:join -c dev
│   ├── dm.md                            # /zchat:dm -u alice -t "hey"
│   └── broadcast.md                     # /zchat:broadcast -t "deploying now"
├── server.py                            # Update CHANNEL_INSTRUCTIONS (existing)
├── message.py                           # (existing, unchanged)
└── pyproject.toml                       # (existing, unchanged)
```

No `.claude/vendor/` needed — the plugin root IS `weechat-channel-server/`.

**Design decisions:**
- **Plugin inside existing dir:** `weechat-channel-server/` already contains the MCP server. Adding `.claude-plugin/` + `commands/` here makes it a self-contained plugin. The marketplace uses `git-subdir` to point at this subdirectory.
- **Commands, not skills:** These are one-shot MCP tool invocations, not multi-step workflows.
- **Flag-based args:** `--channel`, `--text`, `--user` flags. Unambiguous and self-documenting.
- **`allowed-tools`:** Each command restricts Claude to only the MCP tools it needs.
- **`dm` is syntactic sugar:** Same `reply` tool but with a user nick as `chat_id`.

---

## Chunk 1: Marketplace setup

### Task 1: Rename GitHub repo + register marketplace

**External actions (GitHub):**

- [ ] **Step 1: Rename GitHub repo**

Rename `ezagent42/ezagent42` → `ezagent42/ezagent42-marketplace` via GitHub Settings > General > Repository name.

GitHub auto-creates a redirect from the old URL, so existing references keep working.

- [ ] **Step 2: Update marketplace.json name**

In the `ezagent42/ezagent42-marketplace` repo, update `.claude-plugin/marketplace.json`:

```json
{
  "name": "ezagent42",
  "owner": {
    "name": "ezagent42"
  },
  "metadata": {
    "description": "Claude Code channel plugins by ezagent42",
    "version": "1.0.1"
  },
  "plugins": [
    {
      "name": "feishu",
      "description": "Feishu (Lark) channel for Claude Code — receive and reply to Feishu messages",
      "version": "1.0.0",
      "source": {
        "source": "github",
        "repo": "ezagent42/feishu-claude-code-channel"
      }
    },
    {
      "name": "zchat",
      "description": "IRC channel for Claude Code — reply, join, dm, broadcast via slash commands",
      "version": "0.1.0",
      "source": {
        "source": "git-subdir",
        "url": "https://github.com/ezagent42/zchat.git",
        "path": "weechat-channel-server"
      }
    }
  ]
}
```

Commit and push to `ezagent42/ezagent42-marketplace`.

- [ ] **Step 3: Register ezagent42 marketplace in known_marketplaces.json**

Add to `~/.claude/plugins/known_marketplaces.json`:

```json
"ezagent42": {
  "source": {
    "source": "github",
    "repo": "ezagent42/ezagent42-marketplace"
  },
  "installLocation": "/Users/h2oslabs/.claude/plugins/marketplaces/ezagent42",
  "lastUpdated": "<current-ISO-timestamp>"
}
```

Get timestamp: `date -u +"%Y-%m-%dT%H:%M:%S.000Z"`

---

### Task 2: Create plugin manifest + register in project

**Files:**
- Create: `weechat-channel-server/.claude-plugin/plugin.json`
- Modify: `.claude/settings.json`

- [ ] **Step 1: Create plugin.json**

```json
{
  "name": "zchat",
  "description": "IRC channel for Claude Code — reply, join, dm, broadcast via slash commands",
  "version": "0.1.0",
  "keywords": ["irc", "channel", "zchat"]
}
```

- [ ] **Step 2: Add to enabledPlugins in .claude/settings.json**

```json
{
  "enabledPlugins": {
    "agent-setup@agent-setup": true,
    "superpowers@agent-setup": true,
    "agent-browser@agent-setup": true,
    "skill-creator@claude-plugins-official": true,
    "hookify@claude-plugins-official": true,
    "learning-output-style@claude-plugins-official": true,
    "code-simplifier@claude-plugins-official": true,
    "zchat@ezagent42": true
  }
}
```

- [ ] **Step 3: Register in installed_plugins.json**

Add to `~/.claude/plugins/installed_plugins.json` under `plugins`:

```json
"zchat@ezagent42": [
  {
    "scope": "project",
    "projectPath": "/Users/h2oslabs/Workspace/zchat",
    "installPath": "/Users/h2oslabs/Workspace/zchat/weechat-channel-server",
    "version": "0.1.0",
    "installedAt": "<current-ISO-timestamp>",
    "lastUpdated": "<current-ISO-timestamp>",
    "gitCommitSha": "<current-HEAD-sha>"
  }
]
```

- [ ] **Step 4: Commit**

```bash
git add weechat-channel-server/.claude-plugin/plugin.json .claude/settings.json
git commit -m "feat(channel): scaffold zchat plugin manifest and registration"
```

---

## Chunk 2: Commands

### Task 3: Create `/zchat:reply` command

**Files:**
- Create: `weechat-channel-server/commands/reply.md`

- [ ] **Step 1: Write the reply command**

```markdown
---
description: "Reply to an IRC channel or user. Usage: /zchat:reply -c #general -t \"hello world\""
argument-hint: "--channel <#channel|nick> --text <message>"
allowed-tools: ["mcp__weechat-channel__reply"]
---

# Reply to IRC

Parse the arguments and call the `reply` MCP tool.

## Argument parsing

Extract from the args string:
- `--channel <value>` or `-c <value>`: The target channel (e.g. `#general`) or user nick. **Required.**
- `--text <value>` or `-t <value>`: The message text. **Required.** If the value contains spaces, it may be quoted or may be everything after the flag until the next flag or end of string.

If either argument is missing, tell the user the correct usage:
```
Usage: /zchat:reply --channel #general --text "hello world"
       /zchat:reply -c alice -t "hey there"
```

## Action

Call the MCP tool `reply` with:
- `chat_id`: the `--channel` value (keep the `#` prefix for channels)
- `text`: the `--text` value

After sending, confirm: `Sent to <chat_id>`.
```

- [ ] **Step 2: Commit**

```bash
git add weechat-channel-server/commands/reply.md
git commit -m "feat(channel): add /zchat:reply command"
```

---

### Task 4: Create `/zchat:join` command

**Files:**
- Create: `weechat-channel-server/commands/join.md`

- [ ] **Step 1: Write the join command**

```markdown
---
description: "Join an IRC channel. Usage: /zchat:join -c dev"
argument-hint: "--channel <channel-name>"
allowed-tools: ["mcp__weechat-channel__join_channel"]
---

# Join IRC Channel

Parse the arguments and call the `join_channel` MCP tool.

## Argument parsing

Extract from the args string:
- `--channel <value>` or `-c <value>`: Channel name to join. **Required.** Strip any leading `#` — the MCP tool adds it.

If missing, show usage:
```
Usage: /zchat:join --channel dev
       /zchat:join -c general
```

## Action

Call the MCP tool `join_channel` with:
- `channel_name`: the `--channel` value with any `#` prefix stripped

After joining, confirm: `Joined #<channel>`.
```

- [ ] **Step 2: Commit**

```bash
git add weechat-channel-server/commands/join.md
git commit -m "feat(channel): add /zchat:join command"
```

---

### Task 5: Create `/zchat:dm` command

**Files:**
- Create: `weechat-channel-server/commands/dm.md`

- [ ] **Step 1: Write the dm command**

```markdown
---
description: "Send a private message to an IRC user. Usage: /zchat:dm -u alice -t \"hey\""
argument-hint: "--user <nick> --text <message>"
allowed-tools: ["mcp__weechat-channel__reply"]
---

# Direct Message

Parse the arguments and call the `reply` MCP tool with a user nick as target.

## Argument parsing

Extract from the args string:
- `--user <value>` or `-u <value>`: The recipient IRC nick. **Required.**
- `--text <value>` or `-t <value>`: The message text. **Required.**

If either argument is missing, show usage:
```
Usage: /zchat:dm --user alice --text "hey there"
       /zchat:dm -u bob -t "check this out"
```

## Action

Call the MCP tool `reply` with:
- `chat_id`: the `--user` value (nick, no `#` prefix)
- `text`: the `--text` value

After sending, confirm: `DM sent to <user>`.
```

- [ ] **Step 2: Commit**

```bash
git add weechat-channel-server/commands/dm.md
git commit -m "feat(channel): add /zchat:dm command"
```

---

### Task 6: Create `/zchat:broadcast` command

**Files:**
- Create: `weechat-channel-server/commands/broadcast.md`

- [ ] **Step 1: Write the broadcast command**

```markdown
---
description: "Broadcast a message to all joined IRC channels. Usage: /zchat:broadcast -t \"deploying v2.1\""
argument-hint: "--text <message> [--channels <#ch1,#ch2>]"
allowed-tools: ["mcp__weechat-channel__reply"]
---

# Broadcast to All Channels

Send a message to every IRC channel this agent has joined.

## Argument parsing

Extract from the args string:
- `--text <value>` or `-t <value>`: The message to broadcast. **Required.**
- `--channels <value>` or `-C <value>`: Optional comma-separated channel list override (e.g. `"#general,#dev"`).

If `--text` is missing, show usage:
```
Usage: /zchat:broadcast --text "deploying v2.1"
       /zchat:broadcast -t "break time" --channels "#general,#dev"
```

## Determining joined channels

If `--channels` is provided, use that list. Otherwise:

1. Check the most recent `<channel>` notifications in the conversation context for `chat_id` values starting with `#`.
2. Also check the `IRC_CHANNELS` environment variable which lists channels joined at startup.

If no channels can be determined, ask the user:
```
No channels found. Specify explicitly: /zchat:broadcast --channels "#general,#dev" --text "message"
```

## Action

For each identified channel, call the MCP tool `reply` with:
- `chat_id`: the channel name (e.g. `#general`)
- `text`: the `--text` value

After sending, confirm: `Broadcast to: #channel1, #channel2, ...`
```

- [ ] **Step 2: Commit**

```bash
git add weechat-channel-server/commands/broadcast.md
git commit -m "feat(channel): add /zchat:broadcast command"
```

---

## Chunk 3: Server instructions update

### Task 7: Update CHANNEL_INSTRUCTIONS in server.py

**Files:**
- Modify: `weechat-channel-server/server.py:192-203`
- Modify: `tests/unit/test_channel_server_irc.py`

- [ ] **Step 1: Write a failing test**

Add to `tests/unit/test_channel_server_irc.py`:

```python
def test_channel_instructions_mention_slash_commands():
    """CHANNEL_INSTRUCTIONS should reference available /zchat: commands."""
    from server import CHANNEL_INSTRUCTIONS
    # Verify all four commands are mentioned
    assert "/zchat:reply" in CHANNEL_INSTRUCTIONS
    assert "/zchat:join" in CHANNEL_INSTRUCTIONS
    assert "/zchat:dm" in CHANNEL_INSTRUCTIONS
    assert "/zchat:broadcast" in CHANNEL_INSTRUCTIONS
    # Verify original core instructions are preserved
    assert "chat_id" in CHANNEL_INSTRUCTIONS
    assert "reply" in CHANNEL_INSTRUCTIONS
```

Note: The test file already has `sys.path.insert(0, ...)` pointing to `weechat-channel-server/`, so `from server import CHANNEL_INSTRUCTIONS` resolves correctly.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd weechat-channel-server && uv run python -m pytest ../tests/unit/test_channel_server_irc.py::test_channel_instructions_mention_slash_commands -v`
Expected: FAIL — CHANNEL_INSTRUCTIONS doesn't mention slash commands yet.

- [ ] **Step 3: Update CHANNEL_INSTRUCTIONS**

Replace the `CHANNEL_INSTRUCTIONS` string in `weechat-channel-server/server.py` (lines 192-203):

```python
CHANNEL_INSTRUCTIONS = f"""You are {AGENT_NAME}, a Claude Code agent connected to an IRC chat system.

Messages arrive as <channel source="weechat-channel" chat_id="..." user="..." ts="...">content</channel>.
- chat_id starting with "#" is a channel message (e.g. "#general")
- chat_id without "#" is a private message from that user

When you receive a channel notification:
1. Read the message content and the user who sent it
2. If addressed to you or relevant, respond using the "reply" tool with the same chat_id
3. For private messages requesting you to stop/exit, save any work and run /exit

## Available slash commands

Users in your session can use these shortcuts instead of describing actions in natural language:

| Command | Description |
|---------|-------------|
| `/zchat:reply -c #general -t "hello"` | Reply to a channel or user |
| `/zchat:join -c dev` | Join an IRC channel |
| `/zchat:dm -u alice -t "hey"` | Send a private message |
| `/zchat:broadcast -t "deploying"` | Send to all joined channels |

When these commands are invoked, follow the command instructions to call the appropriate MCP tool.
You can also call "reply" and "join_channel" tools directly when responding to channel messages."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd weechat-channel-server && uv run python -m pytest ../tests/unit/test_channel_server_irc.py::test_channel_instructions_mention_slash_commands -v`
Expected: PASS

- [ ] **Step 5: Run full unit test suite**

Run: `cd weechat-channel-server && uv run python -m pytest ../tests/unit/ -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add weechat-channel-server/server.py tests/unit/test_channel_server_irc.py
git commit -m "feat(channel): add slash command reference to CHANNEL_INSTRUCTIONS"
```

---

## Chunk 4: Integration verification

### Task 8: Verify plugin loads correctly

- [ ] **Step 1: Check plugin file structure is complete**

```bash
ls -la weechat-channel-server/.claude-plugin/plugin.json
ls -la weechat-channel-server/commands/reply.md
ls -la weechat-channel-server/commands/join.md
ls -la weechat-channel-server/commands/dm.md
ls -la weechat-channel-server/commands/broadcast.md
```

- [ ] **Step 2: Verify plugin.json is valid JSON**

```bash
uv run python3 -c "import json; json.load(open('weechat-channel-server/.claude-plugin/plugin.json')); print('OK')"
```

- [ ] **Step 3: Verify command frontmatter is parseable**

```bash
uv run python3 -c "
import pathlib, re
for f in pathlib.Path('weechat-channel-server/commands').glob('*.md'):
    content = f.read_text()
    m = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    assert m, f'{f.name}: missing frontmatter'
    assert 'description:' in m.group(1), f'{f.name}: missing description'
    assert 'allowed-tools:' in m.group(1), f'{f.name}: missing allowed-tools'
    print(f'{f.name}: OK')
"
```

- [ ] **Step 4: Run E2E tests to ensure nothing is broken**

Run: `pytest tests/e2e/ -v -m e2e`
Expected: All existing E2E tests pass.

- [ ] **Step 5: Start a new Claude Code session to verify commands appear**

```bash
claude --dangerously-load-development-channels
```

Check that `/zchat:reply`, `/zchat:join`, etc. appear in the available commands/skills list.

- [ ] **Step 6: Final commit (if any fixups needed)**

```bash
git add weechat-channel-server/.claude-plugin/ weechat-channel-server/commands/ .claude/settings.json weechat-channel-server/server.py tests/unit/test_channel_server_irc.py
git commit -m "chore: fixup plugin structure"
```

---

## Summary

| Deliverable | Files |
|-------------|-------|
| Plugin manifest | `weechat-channel-server/.claude-plugin/plugin.json` |
| `/zchat:reply` | `weechat-channel-server/commands/reply.md` |
| `/zchat:join` | `weechat-channel-server/commands/join.md` |
| `/zchat:dm` | `weechat-channel-server/commands/dm.md` |
| `/zchat:broadcast` | `weechat-channel-server/commands/broadcast.md` |
| Updated instructions | `weechat-channel-server/server.py` (CHANNEL_INSTRUCTIONS) |
| Test | `tests/unit/test_channel_server_irc.py` (new test) |
| Settings | `.claude/settings.json` (`zchat@ezagent42`) |
| Marketplace entry | `ezagent42/ezagent42-marketplace` marketplace.json (external) |
| Marketplace registration | `~/.claude/plugins/known_marketplaces.json` (local) |
| Plugin registration | `~/.claude/plugins/installed_plugins.json` (local) |
