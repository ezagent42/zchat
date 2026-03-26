#!/bin/bash
# helpers.sh — Shared utilities for E2E tests (IRC mode)

E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$E2E_DIR/../.." && pwd)"
TMUX_SESSION="e2e-$$"
TEST_CONFIG="$E2E_DIR/test-config.toml"

# Source environment
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"
[ -f "$PROJECT_DIR/claude.local.sh" ] && source "$PROJECT_DIR/claude.local.sh"
[ -f "$PROJECT_DIR/.mcp.env" ] && set -a && source "$PROJECT_DIR/.mcp.env" && set +a

# Claude flags
CLAUDE_FLAGS="--permission-mode bypassPermissions"
CLAUDE_CHANNEL_FLAGS="--dangerously-load-development-channels server:weechat-channel"

# User directories
ALICE_WC_DIR="/tmp/e2e-alice-$$"
BOB_WC_DIR="/tmp/e2e-bob-$$"

# Pane names
PANE_ALICE=""
PANE_BOB=""
PANE_AGENT0=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

pass() { echo -e "${GREEN}✅ PASS${NC}: $1"; }
fail() { echo -e "${RED}❌ FAIL${NC}: $1"; FAILURES=$((FAILURES + 1)); }
info() { echo -e "${YELLOW}➤${NC} $1"; }
step() { echo -e "\n${CYAN}━━━ $1 ━━━${NC}"; }

FAILURES=0

cleanup() {
    info "Cleaning up..."
    # Stop all agents via wc-agent
    python3 "$PROJECT_DIR/wc-agent/cli.py" --config "$TEST_CONFIG" shutdown 2>/dev/null || true
    # Quit WeeChat instances gracefully
    for pane in $(tmux list-panes -t "$TMUX_SESSION" -F '#{pane_index}' 2>/dev/null); do
        cmd=$(tmux display-message -t "$TMUX_SESSION.$pane" -p '#{pane_current_command}' 2>/dev/null)
        if [ "$cmd" = "weechat" ]; then
            tmux send-keys -t "$TMUX_SESSION.$pane" "/quit" Enter 2>/dev/null
        fi
    done
    sleep 2
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null
    # Stop test ergo
    pkill -f "ergo.*ergo-test" 2>/dev/null
    rm -rf "$ALICE_WC_DIR" "$BOB_WC_DIR"
}
trap cleanup EXIT

start_ergo() {
    if ! pgrep -x ergo &>/dev/null; then
        ergo run --conf "$E2E_DIR/ergo-test.yaml" &>/dev/null &
        sleep 1
    fi
}

wc_agent() {
    python3 "$PROJECT_DIR/wc-agent/cli.py" --config "$TEST_CONFIG" "$@"
}

# Wait for text to appear in a tmux pane
wait_for_pane() {
    local pane="$1" pattern="$2" timeout="${3:-10}"
    for i in $(seq 1 "$timeout"); do
        if tmux capture-pane -t "$pane" -p -S -200 2>/dev/null | grep -q "$pattern"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

pane_contains() {
    tmux capture-pane -t "$1" -p -S -200 2>/dev/null | grep -q "$2"
}

split_pane() {
    local direction="$1" target="$2"
    tmux split-window "$direction" -t "$target" -P -F '#{pane_id}'
}

initial_pane_id() {
    tmux list-panes -t "$TMUX_SESSION" -F '#{pane_id}' 2>/dev/null | head -1
}
