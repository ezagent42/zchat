#!/bin/bash
# e2e-test-manual.sh — Set up isolated test environment, then guide manual testing
#
# Usage: source tests/e2e/e2e-test-manual.sh
#   (must be sourced, not executed, so env vars persist in your shell)
#
# What it does:
#   1. Creates isolated temp environment (unique port, temp dirs)
#   2. Sets up WC_AGENT_HOME, PATH, aliases
#   3. Creates a test project
#   4. Starts ergo IRC server
#   5. Prints step-by-step guide for manual testing
#
# After testing, run: e2e-cleanup

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Unique per-run IDs
E2E_ID="${E2E_ID:-$$}"
E2E_IRC_PORT=$((16667 + (E2E_ID % 1000)))
E2E_ERGO_DIR="/tmp/e2e-ergo-${E2E_ID}"

# Isolated WC_AGENT_HOME — never touch ~/.wc-agent/
export WC_AGENT_HOME="/tmp/e2e-wc-agent-${E2E_ID}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"

# Source proxy/env
[ -f "$PROJECT_DIR/claude.local.env" ] && set -a && source "$PROJECT_DIR/claude.local.env" && set +a
[ -f "$PROJECT_DIR/.mcp.env" ] && set -a && source "$PROJECT_DIR/.mcp.env" && set +a

# Alias for convenience
wc-agent() {
    WC_AGENT_HOME="$WC_AGENT_HOME" uv run --project "$PROJECT_DIR/wc-agent" python -m wc_agent.cli "$@"
}
export -f wc-agent

# Cleanup function
e2e-cleanup() {
    echo "Cleaning up e2e environment (id: $E2E_ID)..."
    wc-agent --project e2e shutdown 2>/dev/null || true
    [ -n "$E2E_ERGO_PID" ] && kill "$E2E_ERGO_PID" 2>/dev/null
    rm -rf "/tmp/e2e-ergo-${E2E_ID}" "/tmp/e2e-wc-agent-${E2E_ID}"
    unset WC_AGENT_HOME E2E_ID E2E_IRC_PORT E2E_ERGO_DIR E2E_ERGO_PID
    unset -f wc-agent e2e-cleanup
    echo "Done. Environment variables and aliases removed."
}
export -f e2e-cleanup

# ============================================================
# Auto-setup
# ============================================================

echo "╔══════════════════════════════════════╗"
echo "║  WeeChat-Claude Manual Test Setup    ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "  ID:             $E2E_ID"
echo "  IRC port:       $E2E_IRC_PORT"
echo "  WC_AGENT_HOME:  $WC_AGENT_HOME"
echo "  ergo data:      $E2E_ERGO_DIR"
echo ""

# Sync deps
echo "Syncing dependencies..."
(cd "$PROJECT_DIR/wc-agent" && uv sync --quiet 2>/dev/null || true)
(cd "$PROJECT_DIR/weechat-channel-server" && uv sync --quiet 2>/dev/null || true)

# Create test project
echo "Creating test project 'e2e'..."
mkdir -p "$WC_AGENT_HOME/projects/e2e"
cat > "$WC_AGENT_HOME/projects/e2e/config.toml" << TOMLEOF
[irc]
server = "127.0.0.1"
port = ${E2E_IRC_PORT}
tls = false
password = ""

[agents]
default_channels = ["#general"]
username = "alice"
TOMLEOF
wc-agent project use e2e 2>/dev/null || true

# Start ergo
echo "Starting ergo on port $E2E_IRC_PORT..."
mkdir -p "$E2E_ERGO_DIR"
if [ -d "$HOME/.local/share/ergo/languages" ] && [ ! -d "$E2E_ERGO_DIR/languages" ]; then
    cp -r "$HOME/.local/share/ergo/languages" "$E2E_ERGO_DIR/"
fi
ergo defaultconfig > "$E2E_ERGO_DIR/ergo.yaml" 2>/dev/null
sed -i '' "s|\"127.0.0.1:6667\":|\"127.0.0.1:${E2E_IRC_PORT}\":|" "$E2E_ERGO_DIR/ergo.yaml"
sed -i '' '/\[::1\]:6667/d' "$E2E_ERGO_DIR/ergo.yaml"
sed -i '' '/"[^"]*:6697":/,/min-tls-version:/d' "$E2E_ERGO_DIR/ergo.yaml"

cd "$E2E_ERGO_DIR" && ergo run --conf "$E2E_ERGO_DIR/ergo.yaml" &>/dev/null &
E2E_ERGO_PID=$!
export E2E_ERGO_PID
cd "$PROJECT_DIR"
sleep 2

if kill -0 "$E2E_ERGO_PID" 2>/dev/null; then
    echo "ergo running (pid $E2E_ERGO_PID)"
else
    echo "ERROR: ergo failed to start!"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Environment ready. Run these commands step by step:"
echo ""
echo "  ┌─────────────────────────────────────────┐"
echo "  │ STEP 1: Start WeeChat                   │"
echo "  └─────────────────────────────────────────┘"
echo "  wc-agent irc start"
echo ""
echo "  ┌─────────────────────────────────────────┐"
echo "  │ STEP 2: Check IRC status                │"
echo "  └─────────────────────────────────────────┘"
echo "  wc-agent irc status"
echo ""
echo "  ┌─────────────────────────────────────────┐"
echo "  │ STEP 3: Create agent0                   │"
echo "  └─────────────────────────────────────────┘"
echo "  wc-agent agent create agent0"
echo ""
echo "  Then in WeeChat, type:"
echo "    @alice-agent0 what is the capital of France?"
echo ""
echo "  ┌─────────────────────────────────────────┐"
echo "  │ STEP 4: Agent commands                  │"
echo "  └─────────────────────────────────────────┘"
echo "  wc-agent agent list"
echo "  wc-agent agent status agent0"
echo "  wc-agent agent send agent0 'Use the reply MCP tool to send \"Hello!\" to #general'"
echo ""
echo "  ┌─────────────────────────────────────────┐"
echo "  │ STEP 5: Second agent                    │"
echo "  └─────────────────────────────────────────┘"
echo "  wc-agent agent create helper"
echo "  wc-agent agent send agent0 'Use the reply tool to send \"hello helper\" to \"alice-helper\"'"
echo "  wc-agent agent stop helper"
echo ""
echo "  ┌─────────────────────────────────────────┐"
echo "  │ STEP 6: Cleanup                         │"
echo "  └─────────────────────────────────────────┘"
echo "  wc-agent shutdown      # stop agents + weechat"
echo "  e2e-cleanup             # remove temp dirs + env vars"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
