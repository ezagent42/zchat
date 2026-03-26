#!/bin/bash
# start.sh — Start WeeChat-Claude system
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="${1:-$(pwd)}"
PROJECT="${2:-local}"
SESSION="weechat-claude"

echo "╔══════════════════════════════════════╗"
echo "║       WeeChat-Claude Launcher        ║"
echo "╚══════════════════════════════════════╝"
echo "  Workspace: $WORKSPACE"
echo "  Project:   $PROJECT"

# --- Dependency check ---
MISSING=""
for cmd in claude uv weechat tmux; do
  command -v "$cmd" &>/dev/null || MISSING="$MISSING $cmd"
done
if [ -n "$MISSING" ]; then
  echo "Missing:$MISSING"; exit 1
fi

# Ensure deps
echo "  Syncing deps..."
(cd "$SCRIPT_DIR/wc-agent" && uv sync --quiet 2>/dev/null || true)
(cd "$SCRIPT_DIR/weechat-channel-server" && uv sync --quiet 2>/dev/null || true)

WC_AGENT="uv run --project $SCRIPT_DIR/wc-agent python -m wc_agent.cli --project $PROJECT --tmux-session $SESSION"

# Create project if it doesn't exist
if ! $WC_AGENT project show &>/dev/null; then
  echo "  Creating project '$PROJECT'..."
  $WC_AGENT project create "$PROJECT"
fi

# Start IRC + WeeChat + agent0
$WC_AGENT irc daemon start
$WC_AGENT irc start
$WC_AGENT agent create agent0 --workspace "$WORKSPACE"

echo "  Launching tmux session '$SESSION'..."
tmux -CC attach -t "$SESSION" 2>/dev/null || tmux attach -t "$SESSION"
