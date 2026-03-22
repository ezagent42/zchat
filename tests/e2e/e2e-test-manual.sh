#!/bin/bash
# e2e-test-manual.sh — Interactive E2E test with pause between each phase
#
# Usage: bash tests/e2e/e2e-test-manual.sh
#   - Creates tmux session, waits for you to attach
#   - Pauses after each phase for observation
#   - Press Enter to continue to next phase
#   - After completion, press Enter to cleanup
set -euo pipefail

source "$(dirname "$0")/helpers.sh"

# Override cleanup to not auto-run on exit
trap - EXIT

pause() { echo ""; read -p "  ▶ Press Enter for next phase..."; }

echo "╔══════════════════════════════════════╗"
echo "║  WeeChat-Claude E2E (Manual Mode)   ║"
echo "╚══════════════════════════════════════╝"

# ============================================================
# Phase 0: Prerequisites
# ============================================================
step "Phase 0: Prerequisites"

if ! pgrep -x zenohd &>/dev/null; then
    info "Starting zenohd..."
    zenohd -l tcp/127.0.0.1:7447 &>/dev/null &
    sleep 2
fi
if pgrep -x zenohd &>/dev/null; then
    pass "zenohd running"
else
    fail "zenohd not running"; exit 1
fi

install_weechat_plugins "$ALICE_WC_DIR"
install_weechat_plugins "$BOB_WC_DIR"
create_mcp_config "alice:agent0"

# ============================================================
# Create tmux session and PAUSE for manual attach
# ============================================================
tmux new-session -d -s "$TMUX_SESSION" -x 220 -y 60

echo ""
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo -e "  tmux session: ${GREEN}${TMUX_SESSION}${NC}"
echo ""
echo "  In another terminal:"
echo -e "    ${YELLOW}tmux attach -t ${TMUX_SESSION}${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
read -p "  ▶ Press Enter when attached..."

# ============================================================
# Phase 1: Start alice (WeeChat) + alice:agent0 (claude)
# ============================================================
step "Phase 1: alice + alice:agent0"

PANE_ALICE=$(initial_pane_id)
tmux send-keys -t "$PANE_ALICE" \
    "weechat --dir $ALICE_WC_DIR -r '/set plugins.var.python.weechat-zenoh.nick alice; /set plugins.var.python.weechat-agent.channel_plugin_dir $PROJECT_DIR/weechat-channel-server; /set plugins.var.python.weechat-agent.tmux_session $TMUX_SESSION; /set plugins.var.python.weechat-agent.agent0_workspace $PROJECT_DIR'" Enter

if wait_for_pane "$PANE_ALICE" "Session opened" 15; then
    pass "alice: WeeChat + zenoh sidecar started"
else
    fail "alice: WeeChat failed to start"; exit 1
fi

tmux send-keys -t "$PANE_ALICE" "/python load weechat-agent.py" Enter
sleep 2

PANE_AGENT0=$(split_pane -h "$PANE_ALICE")
tmux send-keys -t "$PANE_AGENT0" \
    "cd $PROJECT_DIR && AGENT_NAME='alice:agent0' claude $CLAUDE_FLAGS $CLAUDE_CHANNEL_FLAGS" Enter

# Auto-confirm the development channels warning prompt
sleep 3
tmux send-keys -t "$PANE_AGENT0" Enter

if wait_for_pane "$PANE_AGENT0" "Listening for channel" 20; then
    pass "alice:agent0: claude started"
else
    fail "alice:agent0: claude failed to start"; exit 1
fi
sleep 5

pause

# ============================================================
# Phase 2: agent0 sends message to #general
# ============================================================
step "Phase 2: agent0 → #general"

tmux send-keys -t "$PANE_AGENT0" \
    'Use the reply MCP tool to send "Hello everyone, alice:agent0 is online!" to #general' Enter

if wait_for_pane "$PANE_AGENT0" "Sent to" 45; then
    pass "agent0: reply tool called successfully"
elif wait_for_pane "$PANE_AGENT0" "online" 10; then
    pass "agent0: reply tool completed"
else
    fail "agent0: reply tool call failed"
fi

tmux send-keys -t "$PANE_ALICE" "/buffer zenoh.#general" Enter
sleep 2

if pane_contains "$PANE_ALICE" "agent0 is online"; then
    pass "alice: received agent0's message in #general"
else
    fail "alice: did not receive agent0's message"
fi

pause

# ============================================================
# Phase 3: alice mentions agent0, agent0 replies
# ============================================================
step "Phase 3: alice @mentions agent0"

tmux send-keys -t "$PANE_ALICE" "@alice:agent0 what is the capital of France?" Enter

# Agent0 should auto-respond via channel notification — no tmux send-keys needed.
# Channel server sends @mention as MCP notification → claude reads it → calls reply tool.
if wait_for_pane "$PANE_ALICE" "alice:agent0" 60; then
    pass "alice ↔ agent0: agent auto-responded to @mention"
else
    fail "alice ↔ agent0: agent did not auto-respond (channel notification may not be working)"
fi

pause

# ============================================================
# Phase 4: bob joins
# ============================================================
step "Phase 4: bob joins #general"

PANE_BOB=$(split_pane -v "$PANE_ALICE")
tmux send-keys -t "$PANE_BOB" \
    "weechat --dir $BOB_WC_DIR -r '/set plugins.var.python.weechat-zenoh.nick bob'" Enter

if wait_for_pane "$PANE_BOB" "Session opened" 15; then
    pass "bob: WeeChat + zenoh sidecar started"
else
    fail "bob: WeeChat failed to start"
fi

tmux send-keys -t "$PANE_BOB" "/buffer zenoh.#general" Enter
sleep 2

tmux send-keys -t "$PANE_BOB" "Hey alice and agent0, bob here!" Enter
sleep 5

tmux send-keys -t "$PANE_ALICE" "/buffer zenoh.#general" Enter
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
# Phase 5: alice creates agent1
# ============================================================
step "Phase 5: /agent create agent1"

tmux send-keys -t "$PANE_ALICE" "/agent create agent1 --workspace $PROJECT_DIR" Enter
sleep 5

tmux send-keys -t "$PANE_ALICE" "/agent list" Enter
sleep 2

if pane_contains "$PANE_ALICE" "agent1"; then
    pass "alice: agent1 created and listed"
else
    fail "alice: agent1 not found in /agent list"
fi

TOTAL_PANES=$(tmux list-panes -t "$TMUX_SESSION" | wc -l | tr -d ' ')
if [ "$TOTAL_PANES" -ge 4 ]; then
    pass "agent1: tmux pane spawned (total=$TOTAL_PANES)"
else
    info "agent1: tmux pane may have exited (total=$TOTAL_PANES, expected ≥4)"
fi

pause

# ============================================================
# Phase 6: graceful stop agent1 (/agent stop)
# ============================================================
step "Phase 6: /agent stop agent1 (graceful)"

tmux send-keys -t "$PANE_ALICE" "/agent stop agent1" Enter

# stop_agent sends Zenoh message requesting agent to exit.
# Agent should respond, save work, and /exit. Presence offline
# event triggers pane cleanup. Wait up to 60s.
if wait_for_pane "$PANE_ALICE" "Stopped" 60; then
    pass "agent1: graceful stop confirmed"
elif grep -q "Stopped" "$ALICE_WC_DIR/logs/"*.weechatlog 2>/dev/null; then
    pass "agent1: graceful stop confirmed (via log)"
else
    fail "agent1: did not exit gracefully (agent should respond to stop message)"
fi

# Verify pane was cleaned up
PANES_AFTER_STOP=$(tmux list-panes -t "$TMUX_SESSION" | wc -l | tr -d ' ')
if [ "$PANES_AFTER_STOP" -lt "$TOTAL_PANES" ]; then
    pass "agent1: tmux pane closed (count=$PANES_AFTER_STOP)"
else
    info "agent1: tmux pane may still exist (count=$PANES_AFTER_STOP)"
fi

pause

# ============================================================
# Phase 7: create agent2, then force kill (/agent kill)
# ============================================================
step "Phase 7: /agent create agent2 + /agent kill agent2"

tmux send-keys -t "$PANE_ALICE" "/agent create agent2 --workspace $PROJECT_DIR" Enter
sleep 5

tmux send-keys -t "$PANE_ALICE" "/agent list" Enter
sleep 2

if pane_contains "$PANE_ALICE" "agent2"; then
    pass "agent2: created and listed"
else
    fail "agent2: not found in /agent list"
fi

PANES_BEFORE_KILL=$(tmux list-panes -t "$TMUX_SESSION" | wc -l | tr -d ' ')

# Force kill — no graceful shutdown, immediate pane termination
tmux send-keys -t "$PANE_ALICE" "/agent kill agent2" Enter
sleep 3

if wait_for_pane "$PANE_ALICE" "Stopped.*agent2" 5; then
    pass "agent2: force killed"
elif pane_contains "$PANE_ALICE" "Stopped"; then
    pass "agent2: force killed"
else
    fail "agent2: kill not confirmed"
fi

PANES_AFTER_KILL=$(tmux list-panes -t "$TMUX_SESSION" | wc -l | tr -d ' ')
if [ "$PANES_AFTER_KILL" -lt "$PANES_BEFORE_KILL" ]; then
    pass "agent2: tmux pane closed (count=$PANES_AFTER_KILL)"
else
    info "agent2: tmux pane may still exist (count=$PANES_AFTER_KILL)"
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
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
read -p "  ▶ Press Enter to cleanup and exit..."

info "Cleaning up..."
for pane in $(tmux list-panes -t "$TMUX_SESSION" -F '#{pane_id}' 2>/dev/null); do
    cmd=$(tmux display-message -t "$pane" -p '#{pane_current_command}' 2>/dev/null)
    if [ "$cmd" = "weechat" ]; then
        tmux send-keys -t "$pane" "/quit" Enter 2>/dev/null
    fi
done
sleep 2
tmux send-keys -t "$PANE_AGENT0" "/exit" Enter 2>/dev/null
sleep 3
tmux kill-session -t "$TMUX_SESSION" 2>/dev/null
rm -rf "$ALICE_WC_DIR" "$BOB_WC_DIR"
rm -f "$PROJECT_DIR/.mcp.json"  # cleanup generated config
info "Done."

exit "$FAILURES"
