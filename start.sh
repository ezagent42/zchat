#!/bin/bash
# start.sh — Start WeeChat-Claude system (ergo IRC + agent0 + WeeChat)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="${1:-$(pwd)}"
CONFIG="${2:-$SCRIPT_DIR/weechat-claude.toml}"
SESSION="weechat-claude"

echo "╔══════════════════════════════════════╗"
echo "║       WeeChat-Claude Launcher        ║"
echo "╚══════════════════════════════════════╝"
echo "  Workspace: $WORKSPACE"
echo "  Config:    $CONFIG"

# --- Dependency check ---
MISSING=""
for cmd in claude uv weechat tmux; do
  command -v "$cmd" &>/dev/null || MISSING="$MISSING $cmd"
done
if [ -n "$MISSING" ]; then
  echo "Missing:$MISSING"; exit 1
fi

# --- Read config ---
IRC_SERVER=$(python3 -c "import tomllib; c=tomllib.load(open('$CONFIG','rb')); print(c['irc']['server'])")
IRC_PORT=$(python3 -c "import tomllib; c=tomllib.load(open('$CONFIG','rb')); print(c['irc']['port'])")
IRC_NICK=$(python3 -c "import tomllib,os; c=tomllib.load(open('$CONFIG','rb')); print(c.get('agents',{}).get('username','') or os.environ.get('USER','user'))")

# --- Start ergo if local and available ---
if [ "$IRC_SERVER" = "127.0.0.1" ] || [ "$IRC_SERVER" = "localhost" ]; then
  if command -v ergo &>/dev/null; then
    if ! pgrep -x ergo &>/dev/null; then
      echo "  Starting ergo IRC server..."
      ERGO_DATA_DIR="${ERGO_DATA_DIR:-$HOME/.local/share/ergo}"
      mkdir -p "$ERGO_DATA_DIR"
      (cd "$ERGO_DATA_DIR" && ergo run --conf "$SCRIPT_DIR/ergo.yaml" &>/dev/null &)
      sleep 1
    fi
  else
    echo "  Warning: ergo not found, assuming IRC server is already running"
  fi
fi

# --- Sync channel-server deps ---
echo "  Syncing channel-server deps..."
(cd "$SCRIPT_DIR/weechat-channel-server" && uv sync --quiet 2>/dev/null || uv sync)

# --- Create tmux session ---
tmux kill-session -t "$SESSION" 2>/dev/null || true
tmux new-session -d -s "$SESSION" -x 220 -y 50

# --- Start agent0 via wc-agent ---
echo "  Starting agent0..."
python3 "$SCRIPT_DIR/wc-agent/cli.py" --config "$CONFIG" start --workspace "$WORKSPACE"

# --- WeeChat pane ---
tmux split-window -h -t "$SESSION"
tmux send-keys -t "$SESSION" \
  "weechat -r '/server add wc-local $IRC_SERVER/$IRC_PORT -notls -nicks=$IRC_NICK; /connect wc-local; /join #general'" Enter

tmux select-pane -t "$SESSION:0.1"
echo "  Launching tmux session '$SESSION'..."
tmux attach -t "$SESSION"
