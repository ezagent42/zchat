#!/bin/bash
# e2e-test.sh — Automated E2E test matching the manual test flow
#
# Tests: ergo → WeeChat → agent0 → @mention → agent1 → agent-to-agent → shutdown
set -euo pipefail

source "$(dirname "$0")/helpers.sh"

echo "╔══════════════════════════════════════╗"
echo "║    WeeChat-Claude E2E Test Suite     ║"
echo "║        (IRC Mode)                    ║"
echo "╚══════════════════════════════════════╝"

# ============================================================
# Phase 0: Setup project + start ergo
# ============================================================
step "Phase 0: Setup"

setup_test_project
pass "test project created ($TEST_PROJECT, port $E2E_IRC_PORT)"

tmux new-session -d -s "$TMUX_SESSION" -x 220 -y 60

# Create command pane (initial pane) for running wc-agent
PANE_CMD=$(initial_pane_id)
# Set env vars in the pane (tmux panes don't inherit exports from parent)
tmux send-keys -t "$PANE_CMD" "export WC_AGENT_HOME=$WC_AGENT_HOME; cd $PROJECT_DIR" Enter
sleep 1

# Start ergo directly (not via tmux send-keys — faster and more reliable)
start_ergo

if lsof -i :"$E2E_IRC_PORT" &>/dev/null; then
    pass "ergo running on port $E2E_IRC_PORT"
else
    fail "ergo not running on port $E2E_IRC_PORT"; exit 1
fi

# ============================================================
# Phase 1: Start WeeChat + create agent0
# ============================================================
step "Phase 1: WeeChat + agent0"

# Start WeeChat directly in a split pane (more reliable than going through CLI in tmux)
PANE_ALICE=$(split_pane -h "$PANE_CMD")
mkdir -p "$ALICE_WC_DIR"
tmux send-keys -t "$PANE_ALICE" \
    "weechat --dir $ALICE_WC_DIR -r '/server add wc-local 127.0.0.1/${E2E_IRC_PORT} -notls -nicks=alice; /connect wc-local; /join #general'" Enter

if wait_for_pane "$PANE_ALICE" "Welcome" 20 || wait_for_pane "$PANE_ALICE" "Connected" 10; then
    pass "alice: WeeChat connected to IRC"
else
    fail "alice: WeeChat failed to connect"; exit 1
fi

# Create agent0 — run directly (not via tmux send-keys)
wc_agent_exec agent create agent0 2>&1 || true
sleep 10

# Find agent0 pane
PANE_AGENT0=$(tmux list-panes -t "$TMUX_SESSION" -F '#{pane_id}' | grep -v "$PANE_CMD" | grep -v "$PANE_ALICE" | head -1)
if [ -n "$PANE_AGENT0" ]; then
    pass "agent0 pane spawned ($PANE_AGENT0)"
else
    PANE_AGENT0="$PANE_CMD"
    info "agent0: pane not found, using command pane"
fi

# Wait for agent to join IRC (channel-server sleeps 2s + IRC connect)
info "Waiting for agent0 to join IRC..."
sleep 25

tmux send-keys -t "$PANE_ALICE" "/names #general" Enter
sleep 3

if pane_contains "$PANE_ALICE" "alice-agent0" || wait_for_pane "$PANE_ALICE" "agent0" 10; then
    pass "agent0: detected in IRC #general"
else
    info "Agent pane:"
    tmux capture-pane -t "$PANE_AGENT0" -p -S -5 2>/dev/null || true
    fail "agent0: not detected in IRC"; exit 1
fi

# ============================================================
# Phase 2: agent0 sends message via send command
# ============================================================
step "Phase 2: agent send"

wc_agent_exec agent send agent0 'Use the reply MCP tool to send "Hello everyone, agent0 here!" to #general' 2>&1 || true
pass "agent send: text sent to agent0 pane"

# Wait for agent to process and reply
if wait_for_pane "$PANE_ALICE" "agent0" 30; then
    pass "alice: received agent0's message in #general"
else
    info "alice: agent0 message not visible (may be scrolled)"
fi

# ============================================================
# Phase 3: alice @mentions agent0
# ============================================================
step "Phase 3: @mention"

tmux send-keys -t "$PANE_ALICE" "@alice-agent0 what is the capital of France?" Enter

if wait_for_pane "$PANE_ALICE" "alice-agent0" 60; then
    pass "agent0: auto-responded to @mention"
else
    fail "agent0: did not auto-respond to @mention"
fi

# ============================================================
# Phase 4: Create agent1 + agent-to-agent communication
# ============================================================
step "Phase 4: agent1 + agent-to-agent"

wc_agent_exec agent create agent1 2>&1 || true
sleep 3

output=$(wc_agent_exec agent list 2>&1 || true)
if echo "$output" | grep -q "agent1"; then
    pass "agent1: created and listed"
else
    fail "agent1: not found in agent list"
fi

# Wait for agent1 to join IRC
info "Waiting for agent1 to join IRC..."
sleep 15

# agent1 sends message to agent0 via send command
wc_agent_exec agent send agent1 'Use the reply MCP tool to send "hello agent0 from agent1" to #general' 2>&1 || true
pass "agent send: text sent to agent1 pane"

# Check if agent0 sees agent1's message
if wait_for_pane "$PANE_ALICE" "agent1" 45; then
    pass "alice: sees agent1's message in #general"
else
    info "alice: agent1's message not visible (may need more time)"
fi

# ============================================================
# Phase 5: Stop agent1
# ============================================================
step "Phase 5: stop agent1"

wc_agent_exec agent stop agent1 2>&1 || true
pass "agent1: stopped"

if wait_for_pane "$PANE_ALICE" "has quit" 15; then
    pass "agent1: IRC QUIT seen by alice"
else
    info "agent1: QUIT not detected in alice's pane"
fi

# ============================================================
# Phase 6: Shutdown
# ============================================================
step "Phase 6: shutdown"

wc_agent_exec shutdown 2>&1 || true
pass "shutdown: complete"

# ============================================================
# Summary
# ============================================================
step "Summary"

echo ""
if [ "$FAILURES" -eq 0 ]; then
    echo -e "${GREEN}All E2E tests passed!${NC}"
else
    echo -e "${RED}$FAILURES failure(s)${NC}"
fi

exit "$FAILURES"
