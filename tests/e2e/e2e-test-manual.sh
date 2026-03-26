#!/bin/bash
# e2e-test-manual.sh — Set up isolated test environment for manual testing
#
# Usage:
#   1. Create a tmux session:
#        tmux -CC new -s test     (iTerm2)
#        tmux new -s test         (standard terminal)
#
#   2. Source this script:
#        source tests/e2e/e2e-test-manual.sh
#
#   3. Follow the steps:
#        ./wc-agent.sh irc start                    # Start WeeChat (new pane)
#        ./wc-agent.sh irc status                   # Verify IRC connected
#        ./wc-agent.sh agent create agent0           # Create agent (new pane)
#        ./wc-agent.sh agent list                    # Check agent status
#        ./wc-agent.sh agent send agent0 'hello'     # Send text to agent pane
#        ./wc-agent.sh agent stop agent0             # Stop agent
#        ./wc-agent.sh shutdown                      # Stop everything
#
#      In WeeChat #general, test @mention:
#        @alice-agent0 what is the capital of France?
#
#   4. In new panes, re-source to get env vars:
#        source tests/e2e/e2e-test-manual.sh
#      (Reuses same E2E_ID, won't restart ergo)
#
#   5. Cleanup:
#        source tests/e2e/e2e-cleanup.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -z "$TMUX" ]; then
    echo "ERROR: Must be inside a tmux session."
    echo ""
    echo "  tmux -CC new -s test   # iTerm2"
    echo "  tmux new -s test       # standard"
    echo ""
    echo "Then: source tests/e2e/e2e-test-manual.sh"
    return 1 2>/dev/null || exit 1
fi

# Unique IDs
export E2E_ID="${E2E_ID:-$$}"
export E2E_IRC_PORT=$((16667 + (E2E_ID % 1000)))
export E2E_ERGO_DIR="/tmp/e2e-ergo-${E2E_ID}"
export WC_AGENT_HOME="/tmp/e2e-wc-agent-${E2E_ID}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"

# Source proxy
[ -f "$PROJECT_DIR/claude.local.env" ] && set -a && source "$PROJECT_DIR/claude.local.env" && set +a

cd "$PROJECT_DIR"

echo "Setting up e2e environment (id: $E2E_ID)..."

# Sync deps
(cd "$PROJECT_DIR/wc-agent" && uv sync --quiet 2>/dev/null || true)
(cd "$PROJECT_DIR/weechat-channel-server" && uv sync --quiet 2>/dev/null || true)

# Create project
mkdir -p "$WC_AGENT_HOME/projects/e2e"
cat > "$WC_AGENT_HOME/projects/e2e/config.toml" << EOF
[irc]
server = "127.0.0.1"
port = ${E2E_IRC_PORT}
tls = false
password = ""

[agents]
default_channels = ["#general"]
username = "alice"
EOF
echo "e2e" > "$WC_AGENT_HOME/default"

# Start ergo
mkdir -p "$E2E_ERGO_DIR"
[ -d "$HOME/.local/share/ergo/languages" ] && [ ! -d "$E2E_ERGO_DIR/languages" ] && \
    cp -r "$HOME/.local/share/ergo/languages" "$E2E_ERGO_DIR/"
ergo defaultconfig > "$E2E_ERGO_DIR/ergo.yaml" 2>/dev/null
sed -i '' "s|\"127.0.0.1:6667\":|\"127.0.0.1:${E2E_IRC_PORT}\":|" "$E2E_ERGO_DIR/ergo.yaml"
sed -i '' '/\[::1\]:6667/d' "$E2E_ERGO_DIR/ergo.yaml"
sed -i '' '/"[^"]*:6697":/,/min-tls-version:/d' "$E2E_ERGO_DIR/ergo.yaml"
(cd "$E2E_ERGO_DIR" && ergo run --conf ergo.yaml &>/dev/null &)
export E2E_ERGO_PID=$!
cd "$PROJECT_DIR"
sleep 2

if ! kill -0 "$E2E_ERGO_PID" 2>/dev/null; then
    echo "ERROR: ergo failed to start"; return 1 2>/dev/null || exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  Ready! Port: $E2E_IRC_PORT  PID: $E2E_ERGO_PID"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "  ./wc-agent.sh irc start"
echo "  ./wc-agent.sh irc status"
echo "  ./wc-agent.sh agent create agent0"
echo "  ./wc-agent.sh agent send agent0 'say hello to #general'"
echo "  ./wc-agent.sh agent list"
echo "  ./wc-agent.sh agent stop agent0"
echo "  ./wc-agent.sh shutdown"
echo ""
echo "  In new panes, run first:"
echo "    source tests/e2e/e2e-test-manual.sh"
echo ""
echo "  Cleanup:"
echo "    source tests/e2e/e2e-cleanup.sh"
echo ""
