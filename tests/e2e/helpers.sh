#!/bin/bash
# helpers.sh — Shared utilities for E2E tests

E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$E2E_DIR/../.." && pwd)"
TMUX_SESSION="e2e-$$"

# Source environment from claude.sh (PATH, proxy, API keys, etc.)
# Replicate the init section without the interactive menu.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"
[ -f "$PROJECT_DIR/claude.local.sh" ] && source "$PROJECT_DIR/claude.local.sh"
[ -f "$PROJECT_DIR/.mcp.env" ] && set -a && source "$PROJECT_DIR/.mcp.env" && set +a

# Claude flags (same as claude.sh interactive mode)
CLAUDE_FLAGS="--permission-mode bypassPermissions"
if [ -f "$PROJECT_DIR/.claude/mcp.json" ]; then
    CLAUDE_FLAGS="$CLAUDE_FLAGS --mcp-config $PROJECT_DIR/.claude/mcp.json"
fi

# User directories
ALICE_WC_DIR="/tmp/e2e-alice-$$"
BOB_WC_DIR="/tmp/e2e-bob-$$"
MCP_CONFIG="/tmp/e2e-mcp-$$.json"

# Pane names (indices assigned after creation)
PANE_ALICE=""   # WeeChat
PANE_BOB=""     # WeeChat
PANE_AGENT0=""  # claude (alice:agent0)
PANE_AGENT1=""  # claude (alice:agent1, created via /agent create)

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
    # Quit WeeChat instances gracefully
    for pane in $(tmux list-panes -t "$TMUX_SESSION" -F '#{pane_index}' 2>/dev/null); do
        cmd=$(tmux display-message -t "$TMUX_SESSION.$pane" -p '#{pane_current_command}' 2>/dev/null)
        if [ "$cmd" = "weechat" ]; then
            tmux send-keys -t "$TMUX_SESSION.$pane" "/quit" Enter 2>/dev/null
        fi
    done
    sleep 2
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null
    rm -rf "$ALICE_WC_DIR" "$BOB_WC_DIR" "$MCP_CONFIG"
}
trap cleanup EXIT

install_weechat_plugins() {
    local wc_dir="$1"
    mkdir -p "$wc_dir/python/autoload"
    cp "$PROJECT_DIR/weechat-zenoh/weechat-zenoh.py" "$wc_dir/python/"
    cp "$PROJECT_DIR/weechat-zenoh/zenoh_sidecar.py" "$wc_dir/python/"
    cp "$PROJECT_DIR/weechat-zenoh/helpers.py" "$wc_dir/python/"
    cp "$PROJECT_DIR/weechat-agent/weechat-agent.py" "$wc_dir/python/"
    ln -sf "../weechat-zenoh.py" "$wc_dir/python/autoload/"
}

create_mcp_config() {
    local agent_name="$1"
    cat > "$MCP_CONFIG" << MCPEOF
{
  "mcpServers": {
    "weechat-channel": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--project", "$PROJECT_DIR/weechat-channel-server", "python3", "$PROJECT_DIR/weechat-channel-server/server.py"],
      "env": { "AGENT_NAME": "$agent_name" }
    }
  }
}
MCPEOF
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

# Split and return the new pane ID
split_pane() {
    local direction="$1" target="$2"
    tmux split-window "$direction" -t "$target" -P -F '#{pane_id}'
}

# Get initial pane ID
initial_pane_id() {
    tmux list-panes -t "$TMUX_SESSION" -F '#{pane_id}' 2>/dev/null | head -1
}
