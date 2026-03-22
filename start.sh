#!/bin/bash
# start.sh — 启动 WeeChat-Claude 完整系统
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="${1:-$(pwd)}"
USERNAME="${2:-$(whoami)}"
SESSION="weechat-claude"

echo "╔══════════════════════════════════════╗"
echo "║       WeeChat-Claude Launcher        ║"
echo "╚══════════════════════════════════════╝"
echo "  Workspace: $WORKSPACE"
echo "  Username:  $USERNAME"

# --- 依赖检查 ---
MISSING=""
for cmd in claude uv weechat tmux zenohd; do
  command -v "$cmd" &>/dev/null || MISSING="$MISSING $cmd"
done
if [ -n "$MISSING" ]; then
  echo "Missing:$MISSING"; exit 1
fi

# --- 确保 zenohd 运行 (localhost only) ---
if ! pgrep -x zenohd &>/dev/null; then
  echo "  Starting zenohd..."
  zenohd -l tcp/127.0.0.1:7447 &>/dev/null &
  sleep 1
  if ! pgrep -x zenohd &>/dev/null; then
    echo "Error: zenohd failed to start"; exit 1
  fi
fi

# --- 确保 channel-server 依赖 ---
echo "  Syncing channel-server deps..."
(cd "$SCRIPT_DIR/weechat-channel-server" && uv sync --quiet 2>/dev/null || uv sync)

# --- 确保 WeeChat Python 能 import zenoh ---
python3 -c "import zenoh" 2>/dev/null || {
  echo "  Installing eclipse-zenoh for system Python..."
  uv pip install --system eclipse-zenoh --quiet
}

# --- 安装 WeeChat 脚本 ---
WC_DIR="${WEECHAT_HOME:-$HOME/.local/share/weechat}"
mkdir -p "$WC_DIR/python/autoload"
cp "$SCRIPT_DIR/weechat-zenoh/weechat-zenoh.py" "$WC_DIR/python/"
cp "$SCRIPT_DIR/weechat-agent/weechat-agent.py" "$WC_DIR/python/"
ln -sf "../weechat-zenoh.py" "$WC_DIR/python/autoload/"
ln -sf "../weechat-agent.py" "$WC_DIR/python/autoload/"

# --- 创建 tmux session ---
tmux kill-session -t "$SESSION" 2>/dev/null || true
tmux new-session -d -s "$SESSION" -x 220 -y 50

# --- Pane 0: Claude Code (agent0) with channel plugin ---
tmux send-keys -t "$SESSION" \
  "cd '$WORKSPACE' && AGENT_NAME='$USERNAME:agent0' claude \
    --dangerously-skip-permissions \
    --dangerously-load-development-channels \
    plugin:weechat-channel" Enter

echo -n "  Waiting for $USERNAME:agent0..."
sleep 5
echo " done"

# --- Pane 1: WeeChat ---
tmux split-window -h -t "$SESSION"
tmux send-keys -t "$SESSION" \
  "weechat -r '\
/set plugins.var.python.weechat-zenoh.nick $USERNAME;\
/set plugins.var.python.weechat-agent.channel_plugin_dir $SCRIPT_DIR/weechat-channel-server;\
/set plugins.var.python.weechat-agent.tmux_session $SESSION;\
/set plugins.var.python.weechat-agent.agent0_workspace $WORKSPACE'" Enter

tmux select-pane -t "$SESSION:0.1"
echo "  Launching tmux session '$SESSION'..."
tmux attach -t "$SESSION"
