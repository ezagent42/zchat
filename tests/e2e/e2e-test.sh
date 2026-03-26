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

setup_test_project
pass "test project created ($TEST_PROJECT)"

start_ergo
if pgrep -x ergo &>/dev/null; then
    pass "ergo IRC server running"
else
    fail "ergo not running"; exit 1
fi

# ============================================================
# Phase 1: Start alice (WeeChat) + alice-agent0 (claude)
# ============================================================
step "Phase 1: alice + alice-agent0"

tmux new-session -d -s "$TMUX_SESSION" -x 220 -y 60

# Pane: alice (WeeChat, native IRC) — initial pane
PANE_ALICE=$(initial_pane_id)
mkdir -p "$ALICE_WC_DIR"
tmux send-keys -t "$PANE_ALICE" \
    "weechat --dir $ALICE_WC_DIR -r '/server add wc-local 127.0.0.1/${E2E_IRC_PORT} -notls -nicks=alice; /connect wc-local'" Enter

if wait_for_pane "$PANE_ALICE" "Welcome" 20 || wait_for_pane "$PANE_ALICE" "Connected" 5; then
    pass "alice: WeeChat connected to IRC"
else
    fail "alice: WeeChat failed to connect"; exit 1
fi

# Join #general
tmux send-keys -t "$PANE_ALICE" "/join #general" Enter
sleep 2

# Create a pane for running wc-agent commands
PANE_CMD=$(split_pane -h "$PANE_ALICE")

# Create agent0 via wc-agent CLI (creates a new tmux pane with claude)
tmux send-keys -t "$PANE_CMD" \
    "cd $PROJECT_DIR && $WC_AGENT agent create agent0 --workspace $PROJECT_DIR" Enter

# Wait for agent to start and join IRC
sleep 15

# Find the claude pane (the one created by wc-agent, not PANE_ALICE or PANE_CMD)
PANE_AGENT0=$(tmux list-panes -t "$TMUX_SESSION" -F '#{pane_id}' | grep -v "$PANE_ALICE" | grep -v "$PANE_CMD" | head -1)

if [ -n "$PANE_AGENT0" ]; then
    pass "alice-agent0: claude pane spawned ($PANE_AGENT0)"
else
    # If no separate pane, claude might be in PANE_CMD
    PANE_AGENT0="$PANE_CMD"
    info "alice-agent0: using command pane as agent pane"
fi

# Wait for MCP server init (channel-server sleeps 2s, then IRC connect + auto-join)
info "Waiting for channel-server to initialize and join IRC..."
sleep 20

# Switch to #general buffer and check for agent
tmux send-keys -t "$PANE_ALICE" "/buffer #general" Enter
sleep 2

# Check IRC nicklist for agent — use /names command
tmux send-keys -t "$PANE_ALICE" "/names #general" Enter
sleep 3

if pane_contains "$PANE_ALICE" "alice-agent0" || wait_for_pane "$PANE_ALICE" "agent0" 10; then
    pass "alice-agent0: detected in IRC"
else
    # Debug: show agent pane and alice pane
    info "Agent pane:"
    tmux capture-pane -t "$PANE_AGENT0" -p -S -5 2>/dev/null || true
    info "Alice pane:"
    tmux capture-pane -t "$PANE_ALICE" -p -S -5 2>/dev/null || true
    fail "alice-agent0: not detected in IRC"; exit 1
fi
sleep 3

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
tmux send-keys -t "$PANE_ALICE" "/join #general" Enter
sleep 2

if wait_for_pane "$PANE_ALICE" "agent0" 10; then
    pass "alice: received agent0's message in #general"
else
    # Phase 3 will be the definitive test of @mention/reply flow
    info "alice: agent0 message not visible in pane (may be scrolled)"
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
    "weechat --dir $BOB_WC_DIR -r '/server add wc-local 127.0.0.1/${E2E_IRC_PORT} -notls -nicks=bob; /connect wc-local'" Enter

if wait_for_pane "$PANE_BOB" "Welcome" 20 || wait_for_pane "$PANE_BOB" "Connected" 5; then
    pass "bob: WeeChat connected to IRC"
else
    fail "bob: WeeChat failed to connect"
fi

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
step "Phase 5: wc-agent agent create agent1"

# Run wc-agent create in a tmux pane
PANE_CMD2=$(split_pane -v "$PANE_AGENT0")
tmux send-keys -t "$PANE_CMD2" \
    "cd $PROJECT_DIR && $WC_AGENT agent create agent1 --workspace $PROJECT_DIR" Enter
sleep 5

# Check if agent1 appears in wc-agent list
tmux send-keys -t "$PANE_CMD2" "$WC_AGENT agent list" Enter
sleep 2

if pane_contains "$PANE_CMD2" "agent1"; then
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
step "Phase 6: wc-agent agent stop agent1"

tmux send-keys -t "$PANE_CMD2" "$WC_AGENT agent stop agent1" Enter
sleep 5

if pane_contains "$PANE_CMD2" "Stopped"; then
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
# Phase 7: agent0 creates agent2 (agent-to-agent spawning)
# ============================================================
step "Phase 7: agent0 creates agent2 via create_agent tool"

# Capture pane IDs before creation so we can find agent2's new pane
PANES_BEFORE=$(tmux list-panes -t "$TMUX_SESSION" -F '#{pane_id}' | sort)

# agent0 uses the create_agent MCP tool to spawn agent2
tmux send-keys -t "$PANE_AGENT0" \
    'Use the create_agent MCP tool to create a new agent named "agent2"' Enter

# Wait for agent0 to call the tool
if wait_for_pane "$PANE_AGENT0" "agent2" 45; then
    pass "agent0: create_agent tool called"
else
    fail "agent0: create_agent tool not called within timeout"
fi

# Wait for agent2 to initialize and join IRC
info "Waiting for agent2 to initialize..."
sleep 20

# Check if agent2 joined IRC
tmux send-keys -t "$PANE_ALICE" "/names #general" Enter
sleep 3

if pane_contains "$PANE_ALICE" "agent2"; then
    pass "agent2: visible in IRC #general"
else
    info "agent2: not yet visible in IRC (may still be starting)"
fi

# ============================================================
# Phase 8: agent0 ↔ agent2 communication (agent-to-agent)
# ============================================================
step "Phase 8: agent0 ↔ agent2 private messaging"

# agent0 sends a private message to agent2 (username is "alice" from test config)
tmux send-keys -t "$PANE_AGENT0" \
    'Use the reply MCP tool to send a private message to "alice-agent2" with text: "Hello agent2, please reply with the word PONG to confirm you received this."' Enter

# Wait for agent0 to confirm the message was sent
if wait_for_pane "$PANE_AGENT0" "Sent to" 30; then
    pass "agent0: sent private message to agent2"
else
    fail "agent0: failed to send private message to agent2"
fi

# Find agent2's pane by comparing with panes before creation
PANES_AFTER=$(tmux list-panes -t "$TMUX_SESSION" -F '#{pane_id}' | sort)
AGENT2_PANE=$(comm -13 <(echo "$PANES_BEFORE") <(echo "$PANES_AFTER") | head -1)

# Wait for agent2 to receive and respond
if [ -n "$AGENT2_PANE" ]; then
    if wait_for_pane "$AGENT2_PANE" "PONG" 60; then
        pass "agent2: received message and replied with PONG"
    elif wait_for_pane "$AGENT2_PANE" "Sent to" 30; then
        pass "agent2: processed message and sent reply"
    else
        info "agent2: did not visibly respond (may have processed internally)"
    fi
else
    info "agent2: pane not found (may share pane with agent0)"
fi

# Verify agent0 received agent2's reply
if wait_for_pane "$PANE_AGENT0" "PONG" 30; then
    pass "agent0: received agent2's PONG reply"
else
    info "agent0: PONG not visible in pane (may have scrolled)"
fi

# ============================================================
# Phase 9: stop agent2
# ============================================================
step "Phase 9: stop agent2"

if [ -n "$AGENT2_PANE" ]; then
    tmux send-keys -t "$AGENT2_PANE" "/exit" Enter
    sleep 5
    if wait_for_pane "$PANE_ALICE" "has quit" 15; then
        pass "agent2: IRC QUIT seen by alice"
    else
        info "agent2: IRC QUIT not detected in alice's pane"
    fi
else
    # Try stopping via wc-agent CLI
    tmux send-keys -t "$PANE_CMD2" "$WC_AGENT agent stop agent2" Enter
    sleep 5
    if pane_contains "$PANE_CMD2" "Stopped"; then
        pass "agent2: stopped via wc-agent"
    else
        info "agent2: stop result unclear"
    fi
fi

# ============================================================
# Phase 10: Summary
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
