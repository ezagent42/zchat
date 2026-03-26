#!/bin/bash
# helpers.sh — Shared utilities for E2E tests (IRC mode)
#
# Each test run uses a unique ID ($$) for:
#   - tmux session name
#   - ergo port (6667 + $$ % 1000)
#   - ergo data dir (/tmp/e2e-ergo-$$/)
#   - weechat dirs (/tmp/e2e-alice-$$, /tmp/e2e-bob-$$)
#   - wc-agent project name
# This prevents collisions between concurrent/leaked test runs.

E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$E2E_DIR/../.." && pwd)"

# Unique per-run IDs
E2E_ID="$$"
TMUX_SESSION="e2e-${E2E_ID}"
TEST_PROJECT="e2e-test-${E2E_ID}"

# Use temp dir for WC_AGENT_HOME — never touch ~/.wc-agent/
export WC_AGENT_HOME="/tmp/e2e-wc-agent-${E2E_ID}"

# Unique ergo port: 16667 + (PID % 1000) to avoid collisions with default 6667
E2E_IRC_PORT=$((16667 + (E2E_ID % 1000)))
E2E_ERGO_DIR="/tmp/e2e-ergo-${E2E_ID}"
E2E_ERGO_PID=""

# Source environment
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"
[ -f "$PROJECT_DIR/claude.local.env" ] && set -a && source "$PROJECT_DIR/claude.local.env" && set +a
[ -f "$PROJECT_DIR/.mcp.env" ] && set -a && source "$PROJECT_DIR/.mcp.env" && set +a

# Claude flags
CLAUDE_FLAGS="--permission-mode bypassPermissions"
CLAUDE_CHANNEL_FLAGS="--dangerously-load-development-channels server:weechat-channel"

# WC_AGENT command — includes WC_AGENT_HOME so tmux panes inherit it
WC_AGENT="WC_AGENT_HOME=$WC_AGENT_HOME uv run --project $PROJECT_DIR/wc-agent python -m wc_agent.cli --project $TEST_PROJECT"

# User directories
ALICE_WC_DIR="/tmp/e2e-alice-${E2E_ID}"
BOB_WC_DIR="/tmp/e2e-bob-${E2E_ID}"

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

    # Create test project with unique port (in temp WC_AGENT_HOME)
    local project_dir="$WC_AGENT_HOME/projects/$TEST_PROJECT"
    mkdir -p "$project_dir"
    cat > "$project_dir/config.toml" << TOMLEOF
[irc]
server = "127.0.0.1"
port = ${E2E_IRC_PORT}
tls = false
password = ""

[agents]
default_channels = ["#general"]
username = "alice"
TOMLEOF
}

start_ergo() {
    # Start ergo on unique port with isolated data dir
    mkdir -p "$E2E_ERGO_DIR"
    rm -f "$E2E_ERGO_DIR/ircd.lock"  # Remove stale lock

    # Copy languages if needed
    local ergo_system_dir="$HOME/.local/share/ergo"
    if [ -d "$ergo_system_dir/languages" ] && [ ! -d "$E2E_ERGO_DIR/languages" ]; then
        cp -r "$ergo_system_dir/languages" "$E2E_ERGO_DIR/"
    fi

    # Generate config for this test's port
    local ergo_conf="$E2E_ERGO_DIR/ergo.yaml"
    ergo defaultconfig > "$ergo_conf" 2>/dev/null

    # Patch: listen on unique port only, remove TLS
    sed -i '' "s|\"127.0.0.1:6667\":|\"127.0.0.1:${E2E_IRC_PORT}\":|" "$ergo_conf"
    sed -i '' '/\[::1\]:6667/d' "$ergo_conf"
    # Remove TLS listener (port 6697 requires certs)
    sed -i '' '/"[^"]*:6697":/,/min-tls-version:/d' "$ergo_conf"

    cd "$E2E_ERGO_DIR" && ergo run --conf "$ergo_conf" &>/dev/null &
    E2E_ERGO_PID=$!
    cd "$PROJECT_DIR"
    sleep 2

    if kill -0 "$E2E_ERGO_PID" 2>/dev/null; then
        info "ergo running (pid $E2E_ERGO_PID, port $E2E_IRC_PORT)"
        return 0
    else
        info "ergo failed to start"
        return 1
    fi
}

cleanup() {
    info "Cleaning up (e2e-${E2E_ID})..."

    # 1. Stop agents via wc-agent
    $WC_AGENT shutdown 2>/dev/null || true

    # 2. Kill weechat processes from THIS test run's dirs
    pkill -9 -f "weechat.*--dir /tmp/e2e-alice-${E2E_ID}" 2>/dev/null
    pkill -9 -f "weechat.*--dir /tmp/e2e-bob-${E2E_ID}" 2>/dev/null

    # 3. Kill THIS test's ergo (by PID, not by name)
    if [ -n "$E2E_ERGO_PID" ]; then
        kill "$E2E_ERGO_PID" 2>/dev/null
        kill -9 "$E2E_ERGO_PID" 2>/dev/null
    fi

    # 4. Kill tmux session
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null

    # 5. Clean temp dirs
    rm -rf "$ALICE_WC_DIR" "$BOB_WC_DIR" "$E2E_ERGO_DIR"
    rm -rf "$WC_AGENT_HOME"

    info "Cleanup done."
}
trap cleanup EXIT

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
