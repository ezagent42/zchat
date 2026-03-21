# Manual Testing Guide

Tests that require a full WeeChat + Claude Code runtime and cannot be automated.

## Prerequisites

- macOS/Linux with tmux, weechat, claude, uv installed
- Two terminal windows minimum
- Claude Code account logged in

## Phase 1: Foundation

### Test: start.sh without pip
1. Temporarily remove `pip` from PATH
2. Run `./start.sh /tmp/test testuser`
3. **Expected**: eclipse-zenoh installs via `uv pip install --system`, tmux session starts

## Phase 2: weechat-zenoh

### Test: /me action rendering
1. Load weechat-zenoh, join #test
2. Type `/me waves hello`
3. **Expected**: buffer shows ` * alice waves hello` (action format)

### Test: Nick change broadcast
1. Alice and Bob both in #test (two WeeChat instances)
2. Alice runs: `/zenoh nick alice2`
3. **Expected**: Bob sees ` -- alice is now known as alice2`, nicklist updates

### Test: Nick change private warning
1. Alice has an open private buffer with @bob
2. Alice runs: `/zenoh nick alice2`
3. **Expected**: Warning message about open private buffers

### Test: /zenoh status output
1. Join a channel, run `/zenoh status`
2. **Expected**: Output shows zid, peer count, mode=peer, channel/private counts

## Phase 3: Channel Server

### Test: Full message bridge (private)
1. Run `./start.sh ~/workspace alice`
2. In WeeChat: `/zenoh join @agent0`
3. Type: `hello agent0`
4. **Expected**: Claude Code session shows `<channel>` event
5. **Expected**: Claude uses reply tool -> message appears in WeeChat buffer

### Test: Channel @mention
1. In WeeChat: `/zenoh join #dev`
2. Type: `@agent0 list files in src/`
3. **Expected**: Agent receives mention, replies to #dev

### Test: Agent auto-joins channel presence
1. After @mentioning agent0 in #dev
2. Check nicklist in #dev
3. **Expected**: agent0 appears in #dev's nicklist

## Phase 4: Agent Management

### Test: Multi-agent pane targeting
1. `/agent create helper1 --workspace /tmp/test1`
2. `/agent create helper2 --workspace /tmp/test2`
3. `/agent stop helper1`
4. **Expected**: Only helper1's tmux pane receives C-c
5. **Expected**: helper2 still running (verify in tmux)

### Test: Agent restart
1. `/agent restart helper1`
2. **Expected**: helper1 stops, then restarts after 2s in same workspace
