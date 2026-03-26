#!/bin/bash
# e2e-test-manual.sh — Create isolated tmux session + test environment
#
# Usage (from any terminal):
#   bash tests/e2e/e2e-test-manual.sh
#
# What it does:
#   1. Creates a new tmux session (e2e-$$) with isolated env vars
#   2. Inside: sets up project, starts ergo, prints guide
#   3. Attaches you to the session (tmux -CC for iTerm2)
#
# The tmux session is self-contained — env vars, ergo, temp dirs
# are all isolated and won't pollute your dev environment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ============================================================
# Generate unique IDs for this test run
# ============================================================

E2E_ID="$$"
E2E_SESSION="e2e-${E2E_ID}"
E2E_IRC_PORT=$((16667 + (E2E_ID % 1000)))
E2E_ERGO_DIR="/tmp/e2e-ergo-${E2E_ID}"
E2E_WC_AGENT_HOME="/tmp/e2e-wc-agent-${E2E_ID}"

echo "╔══════════════════════════════════════╗"
echo "║  WeeChat-Claude Manual Test Setup    ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "  Session:        $E2E_SESSION"
echo "  IRC port:       $E2E_IRC_PORT"
echo "  WC_AGENT_HOME:  $E2E_WC_AGENT_HOME"
echo "  Project dir:    $PROJECT_DIR"
echo ""

# ============================================================
# Sync deps
# ============================================================

echo "Syncing dependencies..."
(cd "$PROJECT_DIR/wc-agent" && uv sync --quiet 2>/dev/null || true)
(cd "$PROJECT_DIR/weechat-channel-server" && uv sync --quiet 2>/dev/null || true)

# ============================================================
# Create test project config
# ============================================================

echo "Creating test project..."
mkdir -p "$E2E_WC_AGENT_HOME/projects/e2e"
cat > "$E2E_WC_AGENT_HOME/projects/e2e/config.toml" << TOMLEOF
[irc]
server = "127.0.0.1"
port = ${E2E_IRC_PORT}
tls = false
password = ""

[agents]
default_channels = ["#general"]
username = "alice"
TOMLEOF
echo "e2e" > "$E2E_WC_AGENT_HOME/default"

# ============================================================
# Start ergo on unique port
# ============================================================

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
cd "$PROJECT_DIR"
sleep 2

if kill -0 "$E2E_ERGO_PID" 2>/dev/null; then
    echo "  ergo running (pid $E2E_ERGO_PID)"
else
    echo "  ERROR: ergo failed to start!"
    exit 1
fi

# ============================================================
# Create tmux session with env vars
# ============================================================

echo "Creating tmux session '$E2E_SESSION'..."
tmux new-session -d -s "$E2E_SESSION" -x 220 -y 60 -c "$PROJECT_DIR"

# Set session-level env vars — all panes in this session inherit these
tmux set-environment -t "$E2E_SESSION" WC_AGENT_HOME "$E2E_WC_AGENT_HOME"
tmux set-environment -t "$E2E_SESSION" E2E_IRC_PORT "$E2E_IRC_PORT"
tmux set-environment -t "$E2E_SESSION" E2E_ID "$E2E_ID"
tmux set-environment -t "$E2E_SESSION" E2E_ERGO_PID "$E2E_ERGO_PID"

# Source proxy env in the initial pane
if [ -f "$PROJECT_DIR/claude.local.env" ]; then
    tmux send-keys -t "$E2E_SESSION" "set -a && source '$PROJECT_DIR/claude.local.env' && set +a" Enter
fi

# Print the guide in the session
tmux send-keys -t "$E2E_SESSION" "clear" Enter
tmux send-keys -t "$E2E_SESSION" "cat << 'GUIDE'
╔══════════════════════════════════════════════════╗
║  Manual Test Environment Ready                   ║
║  Session: $E2E_SESSION                           ║
║  IRC port: $E2E_IRC_PORT                         ║
║  ergo pid: $E2E_ERGO_PID                         ║
╚══════════════════════════════════════════════════╝

All panes in this session have WC_AGENT_HOME set.
Use ./wc-agent.sh for all commands. cd is: $PROJECT_DIR

━━━ Step 1: Start WeeChat ━━━━━━━━━━━━━━━━━━━━━━━
  ./wc-agent.sh irc start

━━━ Step 2: Check status ━━━━━━━━━━━━━━━━━━━━━━━━━
  ./wc-agent.sh irc status

━━━ Step 3: Create agent ━━━━━━━━━━━━━━━━━━━━━━━━━
  ./wc-agent.sh agent create agent0
  # In WeeChat: @alice-agent0 what is the capital of France?

━━━ Step 4: Agent commands ━━━━━━━━━━━━━━━━━━━━━━━
  ./wc-agent.sh agent list
  ./wc-agent.sh agent status agent0
  ./wc-agent.sh agent send agent0 'Reply hello to #general'

━━━ Step 5: Multi-agent ━━━━━━━━━━━━━━━━━━━━━━━━━━
  ./wc-agent.sh agent create helper
  ./wc-agent.sh agent stop helper

━━━ Cleanup ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ./wc-agent.sh shutdown
  # Then close this tmux session:
  exit   (or Ctrl+D, or tmux kill-session -t $E2E_SESSION)

  # If temp files remain:
  rm -rf /tmp/e2e-*-${E2E_ID}
GUIDE" Enter

# ============================================================
# Attach to the session
# ============================================================

echo ""
echo "Attaching to tmux session '$E2E_SESSION'..."
echo "(Close the session when done — ergo + temp files will remain until you clean up)"
echo ""

# iTerm2 native integration if available
if [ "$TERM_PROGRAM" = "iTerm.app" ] || [ "$LC_TERMINAL" = "iTerm2" ] || [ -n "$ITERM_SESSION_ID" ]; then
    exec tmux -CC attach -t "$E2E_SESSION"
else
    exec tmux attach -t "$E2E_SESSION"
fi
