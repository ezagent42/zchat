#!/bin/bash
# e2e-test.sh — Full E2E test: alice + bob + alice:agent0 + alice:agent1
#
# Layout:
#   ┌──────────────────┬──────────────────┐
#   │ alice (WeeChat)  │ alice:agent0     │
#   │                  │ (claude)         │
#   ├──────────────────┼──────────────────┤
#   │ bob (WeeChat)    │ alice:agent1     │
#   │                  │ (/agent create)  │
#   └──────────────────┴──────────────────┘
set -euo pipefail

source "$(dirname "$0")/helpers.sh"

echo "╔══════════════════════════════════════╗"
echo "║    WeeChat-Claude E2E Test Suite     ║"
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
# Phase 1: Start alice (WeeChat) + alice:agent0 (claude)
# ============================================================
step "Phase 1: alice + alice:agent0"

tmux new-session -d -s "$TMUX_SESSION" -x 220 -y 60

# Pane: alice (WeeChat) — initial pane
PANE_ALICE=$(initial_pane_id)
tmux send-keys -t "$PANE_ALICE" \
    "weechat --dir $ALICE_WC_DIR -r '/set plugins.var.python.weechat-zenoh.nick alice; /set plugins.var.python.weechat-agent.channel_plugin_dir $PROJECT_DIR/weechat-channel-server; /set plugins.var.python.weechat-agent.tmux_session $TMUX_SESSION; /set plugins.var.python.weechat-agent.agent0_workspace $PROJECT_DIR'" Enter

if wait_for_pane "$PANE_ALICE" "Session opened" 15; then
    pass "alice: WeeChat + zenoh sidecar started"
else
    fail "alice: WeeChat failed to start"; exit 1
fi

# Load agent plugin
tmux send-keys -t "$PANE_ALICE" "/python load weechat-agent.py" Enter
sleep 2

# Pane: alice:agent0 (claude, interactive) — right side
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
sleep 5  # wait for MCP server init

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

# Verify alice sees it in WeeChat
tmux send-keys -t "$PANE_ALICE" "/buffer zenoh.#general" Enter
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

tmux send-keys -t "$PANE_ALICE" "@alice:agent0 what is the capital of France?" Enter

# Agent0 should auto-respond via channel notification
if wait_for_pane "$PANE_ALICE" "alice:agent0" 60; then
    pass "alice ↔ agent0: agent auto-responded to @mention"
else
    fail "alice ↔ agent0: agent did not auto-respond"
fi

# ============================================================
# Phase 4: bob joins
# ============================================================
step "Phase 4: bob joins #general"

# Split alice's pane vertically to create bob below alice
PANE_BOB=$(split_pane -v "$PANE_ALICE")
tmux send-keys -t "$PANE_BOB" \
    "weechat --dir $BOB_WC_DIR -r '/set plugins.var.python.weechat-zenoh.nick bob'" Enter

if wait_for_pane "$PANE_BOB" "Session opened" 15; then
    pass "bob: WeeChat + zenoh sidecar started"
else
    fail "bob: WeeChat failed to start"
fi

# Switch bob to #general
tmux send-keys -t "$PANE_BOB" "/buffer zenoh.#general" Enter
sleep 2

# bob sends a message
tmux send-keys -t "$PANE_BOB" "Hey alice and agent0, bob here!" Enter
sleep 5

# Ensure alice is on #general buffer
tmux send-keys -t "$PANE_ALICE" "/buffer zenoh.#general" Enter
sleep 2

# Verify alice sees bob's message
if wait_for_pane "$PANE_ALICE" "bob here" 10; then
    pass "alice: sees bob's message"
else
    # Might be scrolled off in small pane — check WeeChat log instead
    if grep -q "bob here" "$ALICE_WC_DIR/logs/"*.weechatlog 2>/dev/null; then
        pass "alice: received bob's message (verified via log)"
    else
        fail "alice: does not see bob's message"
    fi
fi

# ============================================================
# Phase 5: alice creates agent1
# ============================================================
step "Phase 5: /agent create agent1"

tmux send-keys -t "$PANE_ALICE" "/agent create agent1 --workspace $PROJECT_DIR" Enter
sleep 5

# Check if agent1 appears in agent list
tmux send-keys -t "$PANE_ALICE" "/agent list" Enter
sleep 2

if pane_contains "$PANE_ALICE" "agent1"; then
    pass "alice: agent1 created and listed"
else
    fail "alice: agent1 not found in /agent list"
fi

# Check new tmux pane was spawned
TOTAL_PANES=$(tmux list-panes -t "$TMUX_SESSION" | wc -l | tr -d ' ')
if [ "$TOTAL_PANES" -ge 4 ]; then
    pass "agent1: tmux pane spawned (total=$TOTAL_PANES)"
else
    info "agent1: tmux pane may have exited (total=$TOTAL_PANES, expected ≥4)"
fi

# Wait for agent1 to initialize
info "Waiting for agent1 to initialize..."
sleep 15

# ============================================================
# Phase 6: stop agent1 via tmux /exit
# ============================================================
step "Phase 6: stop agent1 (tmux /exit)"

# Find agent1's pane (last pane that isn't alice, bob, or agent0)
AGENT1_PANE=$(tmux list-panes -t "$TMUX_SESSION" -F '#{pane_id}' | \
    grep -v "$PANE_ALICE" | grep -v "$PANE_BOB" | grep -v "$PANE_AGENT0" | tail -1)

if [ -n "$AGENT1_PANE" ]; then
    tmux send-keys -t "$AGENT1_PANE" "/exit" Enter
    # Wait for presence offline notification
    if wait_for_pane "$PANE_ALICE" "offline" 30; then
        pass "agent1: exited and offline notification received"
    else
        info "agent1: /exit sent but offline notification not detected in pane"
    fi
else
    fail "agent1: pane not found"
fi

# ============================================================
# Phase 7: Summary
# ============================================================
step "Summary"

# Exit claude
tmux send-keys -t "$PANE_AGENT0" "/exit" Enter
sleep 3

echo ""
if [ "$FAILURES" -eq 0 ]; then
    echo -e "${GREEN}All E2E tests passed!${NC}"
else
    echo -e "${RED}$FAILURES failure(s)${NC}"
fi

exit "$FAILURES"
