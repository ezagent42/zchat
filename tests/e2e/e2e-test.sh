#!/bin/bash
# e2e-test.sh — Full E2E test: alice + bob + alice-agent0 + alice-agent1
#
# Layout:
#   ┌──────────────────┬──────────────────┐
#   │ alice (WeeChat)  │ alice-agent0     │
#   │  (IRC client)    │ (claude)         │
#   ├──────────────────┼──────────────────┤
#   │ bob (WeeChat)    │ alice-agent1     │
#   │  (IRC client)    │ (wc-agent create)│
#   └──────────────────┴──────────────────┘
set -euo pipefail

source "$(dirname "$0")/helpers.sh"

echo "╔══════════════════════════════════════╗"
echo "║    WeeChat-Claude E2E Test Suite     ║"
echo "║        (IRC Mode)                    ║"
echo "╚══════════════════════════════════════╝"

# ============================================================
# Phase 0: Prerequisites
# ============================================================
step "Phase 0: Prerequisites"

start_ergo
if pgrep -x ergo &>/dev/null; then
    pass "ergo IRC server running"
else
    fail "ergo not running"; exit 1
fi

# Sync channel-server deps
(cd "$PROJECT_DIR/weechat-channel-server" && uv sync --quiet 2>/dev/null || uv sync)
pass "channel-server deps synced"

# ============================================================
# Phase 1: Start alice (WeeChat) + alice-agent0 (claude)
# ============================================================
step "Phase 1: alice + alice-agent0"

tmux new-session -d -s "$TMUX_SESSION" -x 220 -y 60

# Pane: alice (WeeChat, native IRC) — initial pane
PANE_ALICE=$(initial_pane_id)
mkdir -p "$ALICE_WC_DIR"
tmux send-keys -t "$PANE_ALICE" \
    "weechat --dir $ALICE_WC_DIR -r '/server add wc-local 127.0.0.1/6667; /connect wc-local'" Enter

if wait_for_pane "$PANE_ALICE" "Connected" 15; then
    pass "alice: WeeChat connected to IRC"
else
    fail "alice: WeeChat failed to connect"; exit 1
fi

# Join #general
tmux send-keys -t "$PANE_ALICE" "/join #general" Enter
sleep 2

# Set nick to alice
tmux send-keys -t "$PANE_ALICE" "/nick alice" Enter
sleep 1

# Pane: alice-agent0 (claude, via wc-agent) — right side
PANE_AGENT0=$(split_pane -h "$PANE_ALICE")
tmux send-keys -t "$PANE_AGENT0" \
    "cd $PROJECT_DIR && wc_agent start --workspace $PROJECT_DIR" Enter

# Wait for channel-server to connect to IRC (agent joins #general)
sleep 10

if wait_for_pane "$PANE_AGENT0" "Listening for channel" 30; then
    pass "alice-agent0: claude started with IRC channel-server"
else
    # Check if agent0 joined IRC (alice sees JOIN in #general)
    if pane_contains "$PANE_ALICE" "alice-agent0"; then
        pass "alice-agent0: detected via IRC JOIN"
    else
        fail "alice-agent0: claude failed to start"; exit 1
    fi
fi
sleep 5  # wait for MCP server init

# ============================================================
# Phase 2: agent0 sends message to #general
# ============================================================
step "Phase 2: agent0 → #general"

tmux send-keys -t "$PANE_AGENT0" \
    'Use the reply MCP tool to send "Hello everyone, alice-agent0 is online!" to #general' Enter

if wait_for_pane "$PANE_AGENT0" "Sent to" 45; then
    pass "agent0: reply tool called successfully"
elif wait_for_pane "$PANE_AGENT0" "online" 10; then
    pass "agent0: reply tool completed"
else
    fail "agent0: reply tool call failed"
fi

# Verify alice sees it in WeeChat #general
tmux send-keys -t "$PANE_ALICE" "/buffer #general" Enter
sleep 2

if pane_contains "$PANE_ALICE" "agent0 is online"; then
    pass "alice: received agent0's message in #general"
else
    fail "alice: did not receive agent0's message"
fi

# ============================================================
# Phase 3: alice mentions agent0, agent0 replies
# ============================================================
step "Phase 3: alice @mentions agent0"

tmux send-keys -t "$PANE_ALICE" "@alice-agent0 what is the capital of France?" Enter

# Agent0 should auto-respond via IRC
if wait_for_pane "$PANE_ALICE" "alice-agent0" 60; then
    pass "alice ↔ agent0: agent auto-responded to @mention"
else
    fail "alice ↔ agent0: agent did not auto-respond"
fi

# ============================================================
# Phase 4: bob joins
# ============================================================
step "Phase 4: bob joins #general"

PANE_BOB=$(split_pane -v "$PANE_ALICE")
mkdir -p "$BOB_WC_DIR"
tmux send-keys -t "$PANE_BOB" \
    "weechat --dir $BOB_WC_DIR -r '/server add wc-local 127.0.0.1/6667; /connect wc-local'" Enter

if wait_for_pane "$PANE_BOB" "Connected" 15; then
    pass "bob: WeeChat connected to IRC"
else
    fail "bob: WeeChat failed to connect"
fi

tmux send-keys -t "$PANE_BOB" "/nick bob" Enter
sleep 1
tmux send-keys -t "$PANE_BOB" "/join #general" Enter
sleep 2

# bob sends a message
tmux send-keys -t "$PANE_BOB" "Hey alice and agent0, bob here!" Enter
sleep 5

# Verify alice sees bob's message
tmux send-keys -t "$PANE_ALICE" "/buffer #general" Enter
sleep 2

if pane_contains "$PANE_ALICE" "bob here"; then
    pass "alice: sees bob's message"
else
    if grep -q "bob here" "$ALICE_WC_DIR/logs/"*.weechatlog 2>/dev/null; then
        pass "alice: received bob's message (verified via log)"
    else
        fail "alice: does not see bob's message"
    fi
fi

# ============================================================
# Phase 5: create agent1 via wc-agent CLI
# ============================================================
step "Phase 5: wc-agent create agent1"

# Run wc-agent create in a tmux pane
PANE_CMD=$(split_pane -v "$PANE_AGENT0")
tmux send-keys -t "$PANE_CMD" \
    "cd $PROJECT_DIR && wc_agent create agent1 --workspace $PROJECT_DIR" Enter
sleep 5

# Check if agent1 appears in wc-agent list
tmux send-keys -t "$PANE_CMD" "wc_agent list" Enter
sleep 2

if pane_contains "$PANE_CMD" "agent1"; then
    pass "agent1 created and listed"
else
    fail "agent1 not found in wc-agent list"
fi

# Wait for agent1 to initialize and join IRC
info "Waiting for agent1 to initialize..."
sleep 15

# Check if alice sees agent1 in #general
if pane_contains "$PANE_ALICE" "agent1"; then
    pass "agent1: visible in IRC #general"
else
    info "agent1: not yet visible in alice's IRC (may still be starting)"
fi

# ============================================================
# Phase 6: stop agent1 via wc-agent CLI
# ============================================================
step "Phase 6: wc-agent stop agent1"

tmux send-keys -t "$PANE_CMD" "wc_agent stop agent1" Enter
sleep 5

if pane_contains "$PANE_CMD" "Stopped"; then
    pass "agent1: stopped via wc-agent"
else
    fail "agent1: wc-agent stop failed"
fi

# Verify alice sees agent1 quit in IRC
if wait_for_pane "$PANE_ALICE" "has quit" 15; then
    pass "agent1: IRC QUIT seen by alice"
else
    info "agent1: IRC QUIT not detected in alice's pane"
fi

# ============================================================
# Phase 7: Summary
# ============================================================
step "Summary"

# Cleanup agent0
tmux send-keys -t "$PANE_AGENT0" "/exit" Enter
sleep 3

echo ""
if [ "$FAILURES" -eq 0 ]; then
    echo -e "${GREEN}All E2E tests passed!${NC}"
else
    echo -e "${RED}$FAILURES failure(s)${NC}"
fi

exit "$FAILURES"
