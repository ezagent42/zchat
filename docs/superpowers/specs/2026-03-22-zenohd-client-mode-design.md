# Design: Migrate to Zenohd Client Mode

**Date**: 2026-03-22
**Status**: Approved
**Scope**: Switch all Zenoh sessions from peer mode (multicast scouting) to client mode (connect to local zenohd router)

---

## Context

Peer mode with multicast scouting does not work reliably on macOS — two Zenoh peer sessions on the same machine cannot discover each other. A local zenohd router solves this and also enables future storage plugin integration.

**Decision**: zenohd becomes required infrastructure, auto-started by `start.sh`. It runs as a persistent background process (not tied to any single session).

---

## Code Changes

### start.sh — zenohd lifecycle

Add after dependency checks (line ~23), before tmux creation:

```bash
# --- 确保 zenohd 运行 (localhost only) ---
if ! pgrep -x zenohd &>/dev/null; then
  echo "  Starting zenohd (localhost only)..."
  zenohd -l tcp/127.0.0.1:7447 &>/dev/null &
  sleep 1
  if ! pgrep -x zenohd &>/dev/null; then
    echo "Error: zenohd failed to start"; exit 1
  fi
fi
```

The `-l tcp/127.0.0.1:7447` flag restricts zenohd to localhost only, preventing accidental network exposure (PRD: "数据不出本机/内网").

Also add `zenohd` to the dependency check loop (line 18):
```bash
for cmd in claude uv weechat tmux zenohd; do
```

### stop.sh — optional zenohd stop

Replace current content:

```bash
#!/bin/bash
# stop.sh — Stop WeeChat-Claude session (optionally stop zenohd)
# Usage: ./stop.sh [session-name] [--all]
#   --all: also stop zenohd

SESSION="weechat-claude"
STOP_ZENOHD=false

for arg in "$@"; do
  if [ "$arg" = "--all" ]; then
    STOP_ZENOHD=true
  else
    SESSION="$arg"
  fi
done

echo "Stopping session: $SESSION"
tmux kill-session -t "$SESSION" 2>/dev/null && echo "  tmux session stopped" || echo "  (not running)"

if [ "$STOP_ZENOHD" = true ]; then
  pkill -x zenohd 2>/dev/null && echo "  zenohd stopped" || echo "  zenohd (not running)"
fi
```

### weechat-zenoh/weechat-zenoh.py — client mode

In `zc_init()`, change Zenoh config (around line 49-55):

```python
# Old:
config.insert_json5("mode", '"peer"')
connect = weechat.config_get_plugin("connect")
if connect:
    config.insert_json5("connect/endpoints", json.dumps(connect.split(",")))

# New:
config.insert_json5("mode", '"client"')
connect = weechat.config_get_plugin("connect")
if connect:
    config.insert_json5("connect/endpoints", json.dumps(connect.split(",")))
else:
    config.insert_json5("connect/endpoints", '["tcp/127.0.0.1:7447"]')
```

In `/zenoh status` handler, change `mode=peer` to `mode=client`.

Update comment (line ~49) from `# Zenoh peer mode, multicast scouting` to `# Zenoh client mode, connect to local zenohd`.

### weechat-channel-server/server.py — client mode

In `setup_zenoh()`, same change (around line 66-72):

```python
# Old:
zenoh_config.insert_json5("mode", '"peer"')
connect = os.environ.get("ZENOH_CONNECT")
if connect:
    zenoh_config.insert_json5("connect/endpoints", json.dumps(connect.split(",")))

# New:
zenoh_config.insert_json5("mode", '"client"')
connect = os.environ.get("ZENOH_CONNECT")
if connect:
    zenoh_config.insert_json5("connect/endpoints", json.dumps(connect.split(",")))
else:
    zenoh_config.insert_json5("connect/endpoints", '["tcp/127.0.0.1:7447"]')
```

### Shared helper: build_zenoh_config()

Extract duplicated config logic into a shared helper. Since weechat-zenoh runs inside WeeChat (can't import channel-server), and channel-server runs standalone, the helper is duplicated in both but with identical logic:

```python
# In both weechat-zenoh/helpers.py and weechat-channel-server/server.py:

ZENOH_DEFAULT_ENDPOINT = "tcp/127.0.0.1:7447"

def build_zenoh_config(connect: str | None = None) -> "zenoh.Config":
    """Build Zenoh client config. Connects to local zenohd by default."""
    import zenoh
    config = zenoh.Config()
    config.insert_json5("mode", '"client"')
    if connect:
        config.insert_json5("connect/endpoints", json.dumps(connect.split(",")))
    else:
        config.insert_json5("connect/endpoints", f'["{ZENOH_DEFAULT_ENDPOINT}"]')
    return config
```

Then `zc_init()` and `setup_zenoh()` both call `build_zenoh_config(connect)`.

---

## Known Limitations

### zenohd crash mid-session

If zenohd stops while sessions are active, existing Zenoh client sessions will silently fail to deliver messages. Neither weechat-zenoh nor channel-server have reconnection logic.

**Failure mode**: Messages published after zenohd stops are silently dropped. No error is shown to the user. WeeChat buffers remain open but non-functional.

**Recovery**: Restart zenohd (`zenohd -l tcp/127.0.0.1:7447 &`), then restart WeeChat sessions.

**Future**: Add a health-check timer in `weechat-zenoh.py` that periodically calls `zenoh_session.info.routers_zid()` and warns if empty. Tracked as a follow-up, not in this migration scope.

### Port 7447 conflict

If another process (or another zenohd instance) is already using port 7447, `start.sh`'s `pgrep -x zenohd` check will find it and skip startup — but it may be the wrong zenohd or on a different port. This is an edge case for single-user machines; document in manual-testing.md.

---

## Test Changes

### Existing tests — minor updates

Integration tests already use client mode. Update stale references:
- `tests/integration/test_zenoh_pubsub.py` line 3: change docstring from "peer mode" to "client mode"
- `docs/manual-testing.md` line 37: change `mode=peer` to `mode=client`

### New unit test: tests/unit/test_zenoh_config.py

Test the `build_zenoh_config()` helper without real Zenoh:

| Test | Verifies |
|------|----------|
| `test_default_mode_is_client` | Config sets mode to "client" |
| `test_default_endpoint` | Without user override, connects to `tcp/127.0.0.1:7447` |
| `test_custom_endpoint_overrides_default` | User-provided endpoints take precedence |
| `test_env_zenoh_connect_overrides_default` | `ZENOH_CONNECT` env var overrides in channel-server |

### New integration test: add `test_client_sees_router` to test_zenoh_pubsub.py

Add one test to existing file (avoid creating a near-duplicate file):

| Test | Verifies |
|------|----------|
| `test_client_sees_router` | `session.info.routers_zid()` returns non-empty list |

The existing `test_channel_message_roundtrip`, `test_private_message_roundtrip`, and `test_liveliness_token` already verify client→router→client paths via the shared conftest.

### Manual testing additions (docs/manual-testing.md)

Add to Prerequisites section:
```markdown
- zenohd installed (`brew install eclipse-zenoh/zenoh/zenohd`)
- zenohd will be auto-started by start.sh if not running
```

Add new test:
```markdown
### Test: stop.sh does not affect other users' zenohd
1. Start system A: `./start.sh /tmp/a alice`
2. In another terminal, verify zenohd is running: `pgrep -x zenohd`
3. Stop system A: `./stop.sh`
4. Verify zenohd is still running: `pgrep -x zenohd` (should still show PID)
5. Full stop: `./stop.sh --all`
6. Verify zenohd stopped: `pgrep -x zenohd` (should be empty)
```

---

## Documentation Changes

### docs/PRD.md

**§1.2** — Remove "不依赖外部平台" bullet (zenohd is local but is a dependency). Replace with:
"**本地路由**：zenohd 作为轻量本地路由，数据不出本机/内网"

**§9 限制表** — Update:
- Remove: "Zenoh Python in WeeChat .so 冲突" (no longer relevant in client mode)
- Add: "zenohd 必须运行 | 所有 Zenoh 通信依赖本地 zenohd | start.sh 自动启动"

**§10 未来演进** — Update "zenohd + storage" row:
"zenohd 已作为基础设施就绪，接入 filesystem/rocksdb storage backend 即可提供跨 session 消息历史"

### docs/PRD.md §3.4

Update `/zenoh status` description from "(mode, peers, scouting)" to "(mode, routers, peers)".

### CLAUDE.md

Add to Architecture section:
```
- `zenohd` — local Zenoh router (auto-started by start.sh, persists across sessions)
```

Update Commands:
```
./stop.sh                          # Stop tmux session (zenohd keeps running)
./stop.sh --all                    # Stop tmux session + zenohd
```

Remove line: "Zenoh Python + WeeChat .so may conflict — sidecar process is planned"

### README.md / README_zh.md

**Prerequisites** — Add:
```
- [zenohd](https://github.com/eclipse-zenoh/zenoh) — local Zenoh router (auto-started)
```

**Quick Start** — Add note:
```
# zenohd is automatically started if not already running
```

**Known Constraints** — Update Zenoh row:
```
| zenohd must be running | All Zenoh communication routes through local zenohd | Auto-started by start.sh |
```

### weechat-channel-server/README.md

Update: `ZENOH_CONNECT — Zenoh endpoints (optional, multicast by default)` → `ZENOH_CONNECT — Zenoh router endpoints (default: tcp/127.0.0.1:7447)`

### README.md / README_zh.md — additional updates

Update project structure description: "Real Zenoh peer tests" → "Real Zenoh integration tests (requires zenohd)".
Update testing instructions: "(requires Zenoh peer)" → "(requires zenohd running)".

### docs/specs/2026-03-21-prd-gap-fixes-design.md

Update MCP SDK Reference section — change Zenoh config example from `"peer"` to `"client"` with connect endpoint.

### docs/plans/2026-03-21-prd-gap-fixes-plan.md

Historical document — left as-is. It records the original plan at time of writing.

---

## File Change Summary

| File | Change | Type |
|------|--------|------|
| `start.sh` | Add zenohd check/start, add to dep list | Edit |
| `stop.sh` | Add --all flag for zenohd stop | Rewrite |
| `weechat-zenoh/weechat-zenoh.py` | peer→client, default endpoint, comment, helper | Edit |
| `weechat-zenoh/helpers.py` | Add `build_zenoh_config()` | Edit |
| `weechat-channel-server/server.py` | peer→client, default endpoint, helper | Edit |
| `weechat-channel-server/README.md` | Update ZENOH_CONNECT description | Edit |
| `tests/unit/test_zenoh_config.py` | New: config generation tests | Create |
| `tests/integration/test_zenoh_pubsub.py` | Update docstring, add router test | Edit |
| `docs/PRD.md` | §1.2, §3.4, §9, §10 updates | Edit |
| `CLAUDE.md` | Architecture, Commands, remove .so warning | Edit |
| `README.md` | Prerequisites, Quick Start, Constraints, structure | Edit |
| `README_zh.md` | Same as README.md | Edit |
| `docs/manual-testing.md` | Prerequisites, new scenario, mode=client | Edit |
| `docs/specs/2026-03-21-prd-gap-fixes-design.md` | Config example update | Edit |
