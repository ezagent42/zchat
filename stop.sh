#!/bin/bash
# stop.sh — Stop WeeChat-Claude system
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="${1:-local}"
SESSION="weechat-claude"

WC_AGENT="uv run --project $SCRIPT_DIR/wc-agent python -m wc_agent.cli --project $PROJECT --tmux-session $SESSION"

echo "Stopping session: $SESSION"
$WC_AGENT shutdown 2>/dev/null || true
tmux kill-session -t "$SESSION" 2>/dev/null && echo "  tmux session stopped" || echo "  (not running)"
