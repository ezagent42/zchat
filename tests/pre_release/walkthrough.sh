#!/bin/bash
# Pre-release walkthrough — asciinema recording of full zchat lifecycle
#
# Usage:
#   ./tests/pre_release/walkthrough.sh                   # record with uv run (dev)
#   ZCHAT_CMD=zchat ./tests/pre_release/walkthrough.sh   # record with installed binary
#
# Output: tests/pre_release/walkthrough-YYYYMMDD-HHMMSS.cast + .gif
# Play:   asciinema play <cast-file>  or  open <gif-file>
set -euo pipefail

cd "$(dirname "$0")/../.."

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAST_FILE="tests/pre_release/walkthrough-${TIMESTAMP}.cast"
ZCHAT_HOME=$(mktemp -d -t zchat-walkthrough)
SESSION="walkthrough-$$"
PORT=$((16667 + ($$ % 1000)))

export ZCHAT_HOME SESSION PORT
export REPO_ROOT="$(pwd)"
export WALKTHROUGH_PROJECT="wt-test"

cleanup() {
    # Stop ergo started by this walkthrough (match by ZCHAT_HOME temp dir)
    # Only kill ergo processes whose config lives under our temp ZCHAT_HOME
    pgrep -f "ergo run --conf $ZCHAT_HOME" | xargs kill 2>/dev/null || true
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    rm -rf "$ZCHAT_HOME"
}
trap cleanup EXIT

tmux new-session -d -s "$SESSION" -x 160 -y 40

echo "=== Pre-release Walkthrough ==="
echo "Cast:    $CAST_FILE"
echo "Session: $SESSION"
echo "Port:    $PORT"
echo ""

asciinema rec "$CAST_FILE" \
    --command "bash tests/pre_release/walkthrough-steps.sh" \
    --overwrite

GIF_FILE="${CAST_FILE%.cast}.gif"
echo ""
echo "=== Recording saved: $CAST_FILE ==="

if command -v agg &>/dev/null; then
    echo "Generating GIF..."
    agg "$CAST_FILE" "$GIF_FILE"
    echo "GIF: $GIF_FILE"
else
    echo "Install agg to auto-generate GIF: brew install agg"
fi

echo "Play: asciinema play $CAST_FILE"
