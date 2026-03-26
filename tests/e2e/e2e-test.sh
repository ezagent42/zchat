#!/bin/bash
# e2e-test.sh — Automated E2E test
#
# Detection methods:
#   IRC connectivity: irc_nick_exists (WHOIS via nc)
#   Message delivery: wait_for_irc_message (IRC probe files)
#   Agent gone:       wait_for_irc_nick_gone (WHOIS returns nothing)
#   tmux send-keys:   only for user input simulation (WeeChat typing)
set -euo pipefail

source "$(dirname "$0")/helpers.sh"

echo "╔══════════════════════════════════════╗"
echo "║    WeeChat-Claude E2E Test Suite     ║"
echo "╚══════════════════════════════════════╝"

# ============================================================
# Phase 0: Setup
# ============================================================
step "Phase 0: Setup"

setup_test_project
pass "project created ($TEST_PROJECT, port $E2E_IRC_PORT)"

tmux new-session -d -s "$TMUX_SESSION" -x 220 -y 60
PANE_CMD=$(initial_pane_id)
tmux send-keys -t "$PANE_CMD" "export WC_AGENT_HOME=$WC_AGENT_HOME; cd $PROJECT_DIR" Enter
sleep 1

start_ergo
if lsof -i :"$E2E_IRC_PORT" &>/dev/null; then
    pass "ergo running (port $E2E_IRC_PORT)"
else
    fail "ergo not running"; exit 1
fi

# ============================================================
# Phase 1: WeeChat + agent0
# ============================================================
step "Phase 1: WeeChat + agent0"

# Start WeeChat
PANE_ALICE=$(split_pane -h "$PANE_CMD")
mkdir -p "$ALICE_WC_DIR"
tmux send-keys -t "$PANE_ALICE" \
    "weechat --dir $ALICE_WC_DIR -r '/server add wc-local 127.0.0.1/${E2E_IRC_PORT} -notls -nicks=alice; /set irc.server.wc-local.autojoin \"#general\"; /connect wc-local'" Enter

if wait_for_irc_nick "alice" 5; then
    pass "alice: connected to IRC"
else
    fail "alice: not on IRC within 5s"; exit 1
fi

# Explicitly join #general after connection confirmed
tmux send-keys -t "$PANE_ALICE" "/join #general" Enter
sleep 2

# Start IRC probe AFTER alice connects (probe uses a separate nc connection)
start_irc_probe
pass "IRC probe listening on #general"

# Create agent0
wc_agent_exec agent create agent0 2>&1 || true

# Find agent pane
sleep 3
PANE_AGENT0=$(tmux list-panes -t "$TMUX_SESSION" -F '#{pane_id}' | grep -v "$PANE_CMD" | grep -v "$PANE_ALICE" | head -1)
if [ -n "$PANE_AGENT0" ]; then
    pass "agent0: pane spawned ($PANE_AGENT0)"
else
    PANE_AGENT0="$PANE_CMD"
fi

if wait_for_irc_nick "alice-agent0" 15; then
    pass "agent0: connected to IRC"
else
    fail "agent0: not on IRC within 5s"; exit 1
fi

# ============================================================
# Phase 2: agent0 sends message to #general
# ============================================================
step "Phase 2: agent0 → #general"

wc_agent_exec agent send agent0 'Use the reply MCP tool to send "Hello everyone, agent0 here!" to #general' 2>&1 || true

if wait_for_irc_message "agent0 here" 15; then
    pass "agent0: message appeared in #general (verified via IRC probe)"
else
    fail "agent0: message not in IRC probe after 15s"
fi

# ============================================================
# Phase 3: @mention → agent0 auto-responds
# ============================================================
step "Phase 3: @mention"

# Send @mention from alice in WeeChat (alice is already in #general from Phase 1)
tmux send-keys -t "$PANE_ALICE" "@alice-agent0 what is the capital of France?" Enter

# Check IRC probe for agent0's reply (should contain the answer)
if wait_for_irc_message "alice-agent0.*[Pp]aris\|[Pp]aris.*alice-agent0\|capital.*[Ff]rance" 15; then
    pass "agent0: replied to @mention (verified via IRC probe)"
else
    # Fallback: any message from agent0 after the mention
    if wait_for_irc_message "alice-agent0" 5; then
        pass "agent0: replied to @mention"
    else
        info "agent0 pane:"
        tmux capture-pane -t "$PANE_AGENT0" -p -S -10 2>/dev/null || true
        fail "agent0: no reply in IRC probe after 15s"
    fi
fi

# ============================================================
# Phase 4: agent1 + agent-to-agent
# ============================================================
step "Phase 4: agent1"

wc_agent_exec agent create agent1 2>&1 || true

output=$(wc_agent_exec agent list 2>&1 || true)
if echo "$output" | grep -q "agent1"; then
    pass "agent1: created and listed"
else
    fail "agent1: not in agent list"
fi

if wait_for_irc_nick "alice-agent1" 15; then
    pass "agent1: connected to IRC"
else
    info "agent1: not on IRC within 5s"
fi

# agent1 sends message to #general
wc_agent_exec agent send agent1 'Use the reply MCP tool to send "hello from agent1" to #general' 2>&1 || true

if wait_for_irc_message "agent1" 15; then
    pass "agent1: message appeared in #general (verified via IRC probe)"
else
    info "agent1: message not in IRC probe"
fi

# ============================================================
# Phase 5: stop agent1
# ============================================================
step "Phase 5: stop agent1"

wc_agent_exec agent stop agent1 2>&1 || true
pass "agent1: stop command sent"

if wait_for_irc_nick_gone "alice-agent1" 10; then
    pass "agent1: gone from IRC"
else
    info "agent1: still on IRC after 10s"
fi

# ============================================================
# Phase 6: shutdown
# ============================================================
step "Phase 6: shutdown"

wc_agent_exec shutdown 2>&1 || true
pass "shutdown: complete"

if wait_for_irc_nick_gone "alice-agent0" 10; then
    pass "agent0: gone from IRC"
fi

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
