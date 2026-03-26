#!/bin/bash
# e2e-test-manual.sh — Interactive E2E test with pause between each phase
#
# Usage: bash tests/e2e/e2e-test-manual.sh
#   - Creates tmux session, waits for you to attach
#   - Pauses after each phase for observation
#   - Press Enter to continue to next phase
#   - After completion, press Enter to cleanup
#
# Layout (IRC Mode):
#   ┌──────────────────┬──────────────────┐
#   │ alice (WeeChat)  │ cmd / agent0     │
#   │  (IRC client)    │ (claude)         │
#   ├──────────────────┼──────────────────┤
#   │ bob (WeeChat)    │ agent1           │
#   │  (IRC client)    │ (wc-agent create)│
#   └──────────────────┴──────────────────┘
set -euo pipefail

source "$(dirname "$0")/helpers.sh"

# Override cleanup to not auto-run on exit
trap - EXIT

pause() { echo ""; read -p "  ▶ Press Enter for next phase..."; }

WC_AGENT="uv run --project $PROJECT_DIR/weechat-channel-server python3 $PROJECT_DIR/wc-agent/cli.py --config $TEST_CONFIG --tmux-session $TMUX_SESSION"

echo "╔══════════════════════════════════════╗"
echo "║  WeeChat-Claude E2E (Manual Mode)   ║"
echo "║          (IRC Mode)                  ║"
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
# Create tmux session and PAUSE for manual attach
# ============================================================
tmux new-session -d -s "$TMUX_SESSION" -x 220 -y 60

echo ""
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo -e "  tmux session: ${GREEN}${TMUX_SESSION}${NC}"
echo ""
echo "  In another terminal (iTerm2 integration):"
echo -e "    ${YELLOW}tmux -CC attach -t ${TMUX_SESSION}${NC}"
echo ""
echo "  Or standard tmux:"
echo -e "    ${YELLOW}tmux attach -t ${TMUX_SESSION}${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
read -p "  ▶ Press Enter when attached..."

# ============================================================
# Phase 1: Start alice (WeeChat) + alice-agent0 (claude)
# ============================================================
step "Phase 1: alice + alice-agent0"

# Pane: alice (WeeChat, native IRC) — initial pane
PANE_ALICE=$(initial_pane_id)
mkdir -p "$ALICE_WC_DIR"
tmux send-keys -t "$PANE_ALICE" \
    "weechat --dir $ALICE_WC_DIR -r '/server add wc-local 127.0.0.1/6667 -notls; /connect wc-local'" Enter

if wait_for_pane "$PANE_ALICE" "Welcome" 20 || wait_for_pane "$PANE_ALICE" "Connected" 5; then
    pass "alice: WeeChat connected to IRC"
else
    fail "alice: WeeChat failed to connect"; exit 1
fi

# Join #general and set nick
tmux send-keys -t "$PANE_ALICE" "/join #general" Enter
sleep 2
tmux send-keys -t "$PANE_ALICE" "/nick alice" Enter
sleep 1

# Create agent0 via wc-agent CLI (this creates a new tmux pane with claude)
PANE_CMD=$(split_pane -h "$PANE_ALICE")
tmux send-keys -t "$PANE_CMD" \
    "cd $PROJECT_DIR && $WC_AGENT start --workspace $PROJECT_DIR" Enter

# Wait for agent to start and join IRC
info "Waiting for channel-server to initialize and join IRC..."
sleep 20

# Find the claude pane
PANE_AGENT0=$(tmux list-panes -t "$TMUX_SESSION" -F '#{pane_id}' | grep -v "$PANE_ALICE" | grep -v "$PANE_CMD" | head -1)
if [ -z "$PANE_AGENT0" ]; then
    PANE_AGENT0="$PANE_CMD"
fi

# Switch to #general and check for agent
tmux send-keys -t "$PANE_ALICE" "/join #general" Enter
sleep 2
tmux send-keys -t "$PANE_ALICE" "/names #general" Enter
sleep 3

if pane_contains "$PANE_ALICE" "alice-agent0" || wait_for_pane "$PANE_ALICE" "agent0" 10; then
    pass "alice-agent0: detected in IRC"
else
    info "alice-agent0: not detected in IRC (check tmux panes manually)"
fi

pause

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

# Verify alice sees it
tmux send-keys -t "$PANE_ALICE" "/join #general" Enter
sleep 2

if wait_for_pane "$PANE_ALICE" "agent0" 10; then
    pass "alice: received agent0's message in #general"
else
    info "alice: agent0 message not visible in pane (check manually)"
fi

pause

# ============================================================
# Phase 3: alice mentions agent0, agent0 replies
# ============================================================
step "Phase 3: alice @mentions agent0"

tmux send-keys -t "$PANE_ALICE" "@alice-agent0 what is the capital of France?" Enter

if wait_for_pane "$PANE_ALICE" "alice-agent0" 60; then
    pass "alice ↔ agent0: agent auto-responded to @mention"
else
    fail "alice ↔ agent0: agent did not auto-respond"
fi

pause

# ============================================================
# Phase 4: bob joins
# ============================================================
step "Phase 4: bob joins #general"

PANE_BOB=$(split_pane -v "$PANE_ALICE")
mkdir -p "$BOB_WC_DIR"
tmux send-keys -t "$PANE_BOB" \
    "weechat --dir $BOB_WC_DIR -r '/server add wc-local 127.0.0.1/6667 -notls; /connect wc-local'" Enter

if wait_for_pane "$PANE_BOB" "Welcome" 20 || wait_for_pane "$PANE_BOB" "Connected" 5; then
    pass "bob: WeeChat connected to IRC"
else
    fail "bob: WeeChat failed to connect"
fi

tmux send-keys -t "$PANE_BOB" "/nick bob" Enter
sleep 1
tmux send-keys -t "$PANE_BOB" "/join #general" Enter
sleep 2

tmux send-keys -t "$PANE_BOB" "Hey alice and agent0, bob here!" Enter
sleep 5

tmux send-keys -t "$PANE_ALICE" "/join #general" Enter
sleep 2

if wait_for_pane "$PANE_ALICE" "bob here" 10; then
    pass "alice: sees bob's message"
else
    if grep -q "bob here" "$ALICE_WC_DIR/logs/"*.weechatlog 2>/dev/null; then
        pass "alice: received bob's message (verified via log)"
    else
        fail "alice: does not see bob's message"
    fi
fi

pause

# ============================================================
# Phase 5: create agent1 via wc-agent CLI
# ============================================================
step "Phase 5: wc-agent create agent1"

PANE_AGENT1_CMD=$(split_pane -v "$PANE_CMD")
tmux send-keys -t "$PANE_AGENT1_CMD" \
    "cd $PROJECT_DIR && $WC_AGENT create agent1 --workspace $PROJECT_DIR" Enter
sleep 5

tmux send-keys -t "$PANE_AGENT1_CMD" "$WC_AGENT list" Enter
sleep 2

if pane_contains "$PANE_AGENT1_CMD" "agent1"; then
    pass "agent1 created and listed"
else
    fail "agent1 not found in wc-agent list"
fi

TOTAL_PANES=$(tmux list-panes -t "$TMUX_SESSION" | wc -l | tr -d ' ')
info "Total tmux panes: $TOTAL_PANES"

# Wait for agent1 to initialize and join IRC
info "Waiting for agent1 to initialize..."
sleep 15

if pane_contains "$PANE_ALICE" "agent1"; then
    pass "agent1: visible in IRC #general"
else
    info "agent1: not yet visible in alice's IRC (check manually)"
fi

pause

# ============================================================
# Phase 6: stop agent1 via wc-agent CLI
# ============================================================
step "Phase 6: wc-agent stop agent1"

tmux send-keys -t "$PANE_AGENT1_CMD" "$WC_AGENT stop agent1" Enter
sleep 5

if pane_contains "$PANE_AGENT1_CMD" "Stopped"; then
    pass "agent1: stopped via wc-agent"
else
    fail "agent1: wc-agent stop failed"
fi

if wait_for_pane "$PANE_ALICE" "has quit" 15; then
    pass "agent1: IRC QUIT seen by alice"
else
    info "agent1: IRC QUIT not detected in alice's pane"
fi

# ============================================================
# Summary + cleanup
# ============================================================
step "Summary"

echo ""
if [ "$FAILURES" -eq 0 ]; then
    echo -e "${GREEN}All E2E tests passed!${NC}"
else
    echo -e "${RED}$FAILURES failure(s)${NC}"
fi

echo ""
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo "  tmux session ${TMUX_SESSION} is still running."
echo "  Inspect all panes in your attached terminal."
echo ""
echo "  Useful commands:"
echo "    - Switch panes: Ctrl+b, arrow keys"
echo "    - In agent pane: type natural language to interact"
echo "    - In WeeChat: @alice-agent0 <message>"
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
read -p "  ▶ Press Enter to cleanup and exit..."

info "Cleaning up..."
# Stop all agents
$WC_AGENT shutdown 2>/dev/null || true
# Quit WeeChat instances
for pane in $(tmux list-panes -t "$TMUX_SESSION" -F '#{pane_id}' 2>/dev/null); do
    cmd=$(tmux display-message -t "$pane" -p '#{pane_current_command}' 2>/dev/null)
    if [ "$cmd" = "weechat" ]; then
        tmux send-keys -t "$pane" "/quit" Enter 2>/dev/null
    fi
done
sleep 2
# Stop ergo
pkill -f "ergo.*ergo-test" 2>/dev/null
tmux kill-session -t "$TMUX_SESSION" 2>/dev/null
rm -rf "$ALICE_WC_DIR" "$BOB_WC_DIR"
info "Done."

exit "$FAILURES"
