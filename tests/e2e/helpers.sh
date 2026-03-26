#!/bin/bash
# helpers.sh — Shared utilities for E2E tests (IRC mode)

E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$E2E_DIR/../.." && pwd)"
TMUX_SESSION="e2e-$$"
TEST_PROJECT="e2e-test-$$"

# Source environment
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"
[ -f "$PROJECT_DIR/claude.local.env" ] && set -a && source "$PROJECT_DIR/claude.local.env" && set +a
[ -f "$PROJECT_DIR/.mcp.env" ] && set -a && source "$PROJECT_DIR/.mcp.env" && set +a

# Claude flags
CLAUDE_FLAGS="--permission-mode bypassPermissions"
CLAUDE_CHANNEL_FLAGS="--dangerously-load-development-channels server:weechat-channel"

# WC_AGENT command — use uv to run the CLI with proper deps
WC_AGENT="uv run --project $PROJECT_DIR/wc-agent python -m wc_agent.cli --project $TEST_PROJECT"

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

setup_test_project() {
    # Sync deps
    (cd "$PROJECT_DIR/wc-agent" && uv sync --quiet 2>/dev/null || true)
    (cd "$PROJECT_DIR/weechat-channel-server" && uv sync --quiet 2>/dev/null || true)

    # Create test project non-interactively by writing config directly
    local project_dir="$HOME/.wc-agent/projects/$TEST_PROJECT"
    mkdir -p "$project_dir"
    cat > "$project_dir/config.toml" << TOMLEOF
[irc]
server = "127.0.0.1"
port = 6667
tls = false
password = ""

[agents]
default_channels = ["#general"]
username = "alice"
TOMLEOF
}

cleanup() {
    info "Cleaning up..."
    $WC_AGENT shutdown 2>/dev/null || true
    # Quit WeeChat instances
    for pane in $(tmux list-panes -t "$TMUX_SESSION" -F '#{pane_index}' 2>/dev/null); do
        cmd=$(tmux display-message -t "$TMUX_SESSION.$pane" -p '#{pane_current_command}' 2>/dev/null)
        if [ "$cmd" = "weechat" ]; then
            tmux send-keys -t "$TMUX_SESSION.$pane" "/quit" Enter 2>/dev/null
        fi
    done
    sleep 2
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null
    pkill -f "ergo.*ergo-test" 2>/dev/null
    rm -rf "$ALICE_WC_DIR" "$BOB_WC_DIR"
    # Remove test project
    rm -rf "$HOME/.wc-agent/projects/$TEST_PROJECT"
}
trap cleanup EXIT

start_ergo() {
    $WC_AGENT irc daemon start 2>/dev/null || true
}

wc_agent() {
    $WC_AGENT "$@"
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
