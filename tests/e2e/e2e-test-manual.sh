#!/bin/bash
# e2e-test-manual.sh — Create isolated tmux session for manual testing
#
# Usage: bash tests/e2e/e2e-test-manual.sh
#
# Creates a new tmux session with everything set up.
# All panes inherit WC_AGENT_HOME via env file auto-sourced by shell.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

E2E_ID="$$"
E2E_SESSION="e2e-${E2E_ID}"
E2E_IRC_PORT=$((16667 + (E2E_ID % 1000)))
E2E_ERGO_DIR="/tmp/e2e-ergo-${E2E_ID}"
E2E_WC_AGENT_HOME="/tmp/e2e-wc-agent-${E2E_ID}"
E2E_ENV_FILE="/tmp/e2e-env-${E2E_ID}.sh"

echo "╔══════════════════════════════════════╗"
echo "║  WeeChat-Claude Manual Test Setup    ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "  Session:  $E2E_SESSION"
echo "  IRC port: $E2E_IRC_PORT"
echo ""

# ============================================================
# Sync deps
# ============================================================
echo "Syncing dependencies..."
(cd "$PROJECT_DIR/wc-agent" && uv sync --quiet 2>/dev/null || true)
(cd "$PROJECT_DIR/weechat-channel-server" && uv sync --quiet 2>/dev/null || true)

# ============================================================
# Create test project
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
# Start ergo
# ============================================================
echo "Starting ergo on port $E2E_IRC_PORT..."
mkdir -p "$E2E_ERGO_DIR"
[ -d "$HOME/.local/share/ergo/languages" ] && [ ! -d "$E2E_ERGO_DIR/languages" ] && \
    cp -r "$HOME/.local/share/ergo/languages" "$E2E_ERGO_DIR/"

ergo defaultconfig > "$E2E_ERGO_DIR/ergo.yaml" 2>/dev/null
sed -i '' "s|\"127.0.0.1:6667\":|\"127.0.0.1:${E2E_IRC_PORT}\":|" "$E2E_ERGO_DIR/ergo.yaml"
sed -i '' '/\[::1\]:6667/d' "$E2E_ERGO_DIR/ergo.yaml"
sed -i '' '/"[^"]*:6697":/,/min-tls-version:/d' "$E2E_ERGO_DIR/ergo.yaml"

cd "$E2E_ERGO_DIR" && ergo run --conf ergo.yaml &>/dev/null &
E2E_ERGO_PID=$!
cd "$PROJECT_DIR"
sleep 2

if ! kill -0 "$E2E_ERGO_PID" 2>/dev/null; then
    echo "ERROR: ergo failed to start!"; exit 1
fi
echo "  ergo running (pid $E2E_ERGO_PID)"

# ============================================================
# Write env file — sourced by every pane
# ============================================================
cat > "$E2E_ENV_FILE" << ENVEOF
# E2E test environment (auto-generated, id: $E2E_ID)
export WC_AGENT_HOME="$E2E_WC_AGENT_HOME"
export E2E_ID="$E2E_ID"
export E2E_IRC_PORT="$E2E_IRC_PORT"
export E2E_ERGO_PID="$E2E_ERGO_PID"
export PATH="/opt/homebrew/bin:/usr/local/bin:\$HOME/.npm-global/bin:\$HOME/.local/bin:\$PATH"
[ -f "$PROJECT_DIR/claude.local.env" ] && set -a && source "$PROJECT_DIR/claude.local.env" && set +a
cd "$PROJECT_DIR"
ENVEOF

# Write cleanup script
cat > "/tmp/e2e-cleanup-${E2E_ID}.sh" << 'CLEANEOF'
#!/bin/bash
source ENVFILE
echo "Cleaning up e2e-$E2E_ID..."
./wc-agent.sh shutdown 2>/dev/null || true
kill $E2E_ERGO_PID 2>/dev/null
lsof -ti :${E2E_IRC_PORT} 2>/dev/null | xargs kill 2>/dev/null
rm -rf "/tmp/e2e-ergo-${E2E_ID}" "$WC_AGENT_HOME" "/tmp/e2e-env-${E2E_ID}.sh" "/tmp/e2e-cleanup-${E2E_ID}.sh"
echo "Done. Run 'exit' to close this tmux session."
CLEANEOF
sed -i '' "s|ENVFILE|$E2E_ENV_FILE|" "/tmp/e2e-cleanup-${E2E_ID}.sh"
chmod +x "/tmp/e2e-cleanup-${E2E_ID}.sh"

# ============================================================
# Create tmux session — initial shell sources the env file
# ============================================================
echo "Creating tmux session '$E2E_SESSION'..."

# Create session
# NOTE: Do NOT use set-option default-command — it pollutes the tmux server globally
tmux new-session -d -s "$E2E_SESSION" -x 220 -y 60

# set-environment is session-scoped and safe — new panes inherit these env vars
tmux set-environment -t "$E2E_SESSION" WC_AGENT_HOME "$E2E_WC_AGENT_HOME"
tmux set-environment -t "$E2E_SESSION" E2E_ENV_FILE "$E2E_ENV_FILE"

# Source full env in initial pane (proxy, cd, PATH — not just WC_AGENT_HOME)
tmux send-keys -t "$E2E_SESSION" "source '$E2E_ENV_FILE'" Enter
sleep 1
tmux send-keys -t "$E2E_SESSION" "cat << 'GUIDE'

╔══════════════════════════════════════════════════╗
║  Manual Test Environment Ready                   ║
║  Session: $E2E_SESSION  |  Port: $E2E_IRC_PORT          ║
╚══════════════════════════════════════════════════╝

Use ./wc-agent.sh for commands.
New panes: WC_AGENT_HOME is set. For proxy+cd: source \$E2E_ENV_FILE

━━━ Step 1: Start WeeChat ━━━━━━━━━━━━━━━━━━━━━━━
  ./wc-agent.sh irc start

━━━ Step 2: Check status ━━━━━━━━━━━━━━━━━━━━━━━━━
  ./wc-agent.sh irc status

━━━ Step 3: Create agent ━━━━━━━━━━━━━━━━━━━━━━━━━
  ./wc-agent.sh agent create agent0
  (In WeeChat: @alice-agent0 what is the capital of France?)

━━━ Step 4: Agent commands ━━━━━━━━━━━━━━━━━━━━━━━
  ./wc-agent.sh agent list
  ./wc-agent.sh agent status agent0
  ./wc-agent.sh agent send agent0 'Reply hello to #general'

━━━ Step 5: Multi-agent ━━━━━━━━━━━━━━━━━━━━━━━━━━
  ./wc-agent.sh agent create helper
  ./wc-agent.sh agent stop helper

━━━ Cleanup ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ./wc-agent.sh shutdown
  bash /tmp/e2e-cleanup-${E2E_ID}.sh
  exit
GUIDE" Enter

# ============================================================
# Attach
# ============================================================
echo ""
echo "Attaching..."

if [ -n "$TMUX" ]; then
    # Already inside tmux — switch to new session (no nesting)
    exec tmux switch-client -t "$E2E_SESSION"
elif [ "$TERM_PROGRAM" = "iTerm.app" ] || [ "$LC_TERMINAL" = "iTerm2" ] || [ -n "$ITERM_SESSION_ID" ]; then
    exec tmux -CC attach -t "$E2E_SESSION"
else
    exec tmux attach -t "$E2E_SESSION"
fi
