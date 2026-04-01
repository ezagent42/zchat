#!/bin/bash
# Walkthrough steps — executed inside asciinema recording.
# Called by walkthrough.sh with env vars: ZCHAT_HOME, SESSION, PORT, REPO_ROOT, WALKTHROUGH_PROJECT
set -euo pipefail

PROJECT="$WALKTHROUGH_PROJECT"

# CLI wrapper
if [ -n "${ZCHAT_CMD:-}" ]; then
    zchat() { "$ZCHAT_CMD" "$@"; }
else
    zchat() { uv run --project "$REPO_ROOT" zchat "$@"; }
fi
ZP="--project $PROJECT"

section() {
    echo ""
    echo "════════════════════════════════════════"
    echo "  $1"
    echo "════════════════════════════════════════"
}

step() { echo ""; echo ">>> $1"; }

capture_windows() {
    echo "--- tmux windows ---"
    tmux list-windows -t "$SESSION" 2>/dev/null || true
}

capture_pane() {
    local target="$1"
    local label="${2:-$target}"
    echo "--- [$label] pane content ---"
    tmux capture-pane -t "$SESSION:$target" -p 2>/dev/null | tail -15 || echo "pane not found"
}

# Get scoped agent name (e.g., h2oslabs-agent0)
scoped_name() {
    local agent="$1"
    echo "${USERNAME}-${agent}"
}

# Wait for a pattern to appear in a pane (poll with timeout)
wait_pane_content() {
    local target="$1"
    local pattern="$2"
    local timeout="${3:-30}"
    local deadline=$((SECONDS + timeout))
    while [ $SECONDS -lt $deadline ]; do
        if tmux capture-pane -t "$SESSION:$target" -p 2>/dev/null | grep -q "$pattern"; then
            return 0
        fi
        sleep 2
    done
    return 1
}

# ============================================================
section "1. Doctor — environment check"
# ============================================================
step "zchat doctor"
zchat doctor
sleep 0.5

# ============================================================
section "2. Project — create and manage"
# ============================================================
step "zchat project create $PROJECT"
zchat $ZP project create "$PROJECT" \
    --server 127.0.0.1 --port "$PORT" \
    --channels "#general" --agent-type claude --proxy ""
sleep 0.5

step "zchat project show"
zchat $ZP project show "$PROJECT"
# Extract username for scoped agent names
USERNAME=$(zchat $ZP project show "$PROJECT" 2>/dev/null | grep -i nick | awk '{print $NF}')
USERNAME="${USERNAME:-$USER}"
echo "  (detected username: $USERNAME)"
sleep 0.5

step "zchat project list"
zchat $ZP project list
sleep 0.5

step "zchat set tmux.session (bind to test session)"
zchat $ZP set tmux.session "$SESSION"
sleep 0.3

step "zchat set irc.port 9999 (test config update)"
zchat $ZP set irc.port 9999
zchat $ZP project show "$PROJECT"
sleep 0.3

step "zchat set irc.port $PORT (restore)"
zchat $ZP set irc.port "$PORT"
sleep 0.3

step "zchat project create second-proj"
zchat $ZP project create second-proj \
    --server 127.0.0.1 --port 6667 \
    --channels "#test" --agent-type claude --proxy ""
sleep 0.3

step "zchat project list (two projects)"
zchat $ZP project list
sleep 0.3

step "zchat project use second-proj"
zchat $ZP project use second-proj 2>/dev/null || true
sleep 0.3

step "zchat project remove second-proj"
zchat $ZP project remove second-proj
sleep 0.3

step "zchat project list (back to one)"
zchat $ZP project list
sleep 0.5

# ============================================================
section "3. Templates — list, show, create, set"
# ============================================================
step "zchat template list"
zchat $ZP template list
sleep 0.3

step "zchat template show claude"
zchat $ZP template show claude
sleep 0.3

step "zchat template create test-tpl"
zchat $ZP template create test-tpl
sleep 0.3

step "zchat template set test-tpl MY_VAR hello"
zchat $ZP template set test-tpl MY_VAR hello
sleep 0.3

step "zchat template list (now includes test-tpl)"
zchat $ZP template list
sleep 0.5

# ============================================================
section "4. IRC — daemon and WeeChat lifecycle"
# ============================================================
step "zchat irc daemon start"
zchat $ZP irc daemon start
sleep 2

step "zchat irc status (daemon running, weechat stopped)"
zchat $ZP irc status
sleep 0.5

step "zchat irc start (launch WeeChat)"
zchat $ZP irc start
sleep 5

step "zchat irc status (both running)"
zchat $ZP irc status
sleep 0.5

capture_windows

step "Capture WeeChat pane"
capture_pane weechat "WeeChat"
sleep 1

step "zchat irc stop (stop WeeChat)"
zchat $ZP irc stop
sleep 2

step "zchat irc status (weechat stopped)"
zchat $ZP irc status
sleep 0.5

step "zchat irc start (restart WeeChat for agent tests)"
zchat $ZP irc start
sleep 5

# ============================================================
section "5. Agent — full lifecycle"
# ============================================================
step "zchat agent create agent0"
zchat $ZP agent create agent0
sleep 3

step "zchat agent list"
zchat $ZP agent list
sleep 0.5

step "zchat agent status agent0"
zchat $ZP agent status agent0
sleep 0.5

capture_windows
step "Capture agent0 window"
capture_pane "$(scoped_name agent0)" "agent0"
sleep 1

step "Wait for agent0 to be ready (Claude Code init)"
if wait_pane_content "$(scoped_name agent0)" "ready\|Claude\|>" 60; then
    echo "  agent0 appears ready"
else
    echo "  agent0 may still be initializing (continuing anyway)"
fi
capture_pane "$(scoped_name agent0)" "agent0 after wait"
sleep 1

step "zchat agent send agent0 (ask to reply in #general)"
zchat $ZP agent send agent0 'Use the reply MCP tool to send the message walkthrough-test-msg to channel #general'

step "Waiting for message in WeeChat (up to 60s)..."
if wait_pane_content weechat "walkthrough-test-msg" 60; then
    echo "  Message received!"
else
    echo "  Message not seen in 60s (agent may still be processing)"
fi

step "Capture WeeChat pane (check for message)"
capture_pane weechat "WeeChat after send"
sleep 1

step "zchat agent create agent1"
zchat $ZP agent create agent1
sleep 3

step "zchat agent list (two agents)"
zchat $ZP agent list
sleep 0.5

step "zchat agent restart agent1"
zchat $ZP agent restart agent1
sleep 3

step "zchat agent list (after restart)"
zchat $ZP agent list
sleep 0.5

step "zchat agent stop agent1"
zchat $ZP agent stop agent1
sleep 2

step "zchat agent list (agent1 stopped)"
zchat $ZP agent list
sleep 0.5

# ============================================================
section "6. Setup — WeeChat plugin"
# ============================================================
step "zchat setup weechat --force"
zchat $ZP setup weechat --force
sleep 0.5

# ============================================================
section "7. Auth — status check"
# ============================================================
step "zchat auth status"
zchat $ZP auth status 2>/dev/null || true
sleep 0.5

# ============================================================
section "8. Shutdown — stop everything"
# ============================================================
step "zchat irc daemon stop (test direct daemon stop)"
zchat $ZP irc daemon stop
sleep 1

step "zchat irc daemon start (restart for shutdown test)"
zchat $ZP irc daemon start
sleep 2

step "zchat irc start (restart WeeChat for shutdown test)"
zchat $ZP irc start
sleep 3

step "zchat shutdown"
zchat $ZP shutdown
sleep 2

step "zchat irc status (after shutdown)"
zchat $ZP irc status 2>/dev/null || echo "expected: project or daemon not available"
sleep 0.5

capture_windows

section "DONE — all commands exercised"
echo ""
echo "  doctor, project (create/list/show/set/use/remove),"
echo "  template (list/show/create/set),"
echo "  irc (daemon start/stop, start/stop/status),"
echo "  agent (create/list/status/send/restart/stop),"
echo "  setup weechat, auth status, shutdown"
echo ""
sleep 2
