#!/bin/bash
set -euo pipefail

# Parse MCP server command (first word = command, rest = args)
read -ra MCP_PARTS <<< "$MCP_SERVER_CMD"
MCP_CMD="${MCP_PARTS[0]}"
MCP_ARGS=("${MCP_PARTS[@]:1}")

# --- Locate channel server plugin ---
CHANNEL_PKG=$(python3 -c "
from importlib.metadata import files
for f in files('zchat-channel-server'):
    if f.name == 'server.py':
        print(f.locate().parent)
        break
" 2>/dev/null || echo "")

# Symlink plugin into workspace if found
if [ -n "$CHANNEL_PKG" ] && [ -d "$CHANNEL_PKG/.claude-plugin" ]; then
  ln -sfn "$CHANNEL_PKG/.claude-plugin" .claude-plugin
  ln -sfn "$CHANNEL_PKG/commands" commands
fi

# --- Claude settings ---
mkdir -p .claude
cat > .claude/settings.local.json << 'EOF'
{
  "permissions": {
    "allow": [
      "mcp__zchat-channel__reply",
      "mcp__zchat-channel__join_channel"
    ]
  },
  "enabledPlugins": {
    "zchat@ezagent42": true
  }
}
EOF

# --- Build .mcp.json ---
if [ ${#MCP_ARGS[@]} -gt 0 ]; then
  ARGS_JSON=$(printf '%s\n' "${MCP_ARGS[@]}" | jq -R . | jq -s .)
  ARGS_LINE="\"args\": $ARGS_JSON,"
else
  ARGS_LINE=""
fi

# Build proxy env entries if set
PROXY_ENV=""
if [ -n "${HTTP_PROXY:-}" ]; then
  PROXY_ENV="${PROXY_ENV}\"HTTP_PROXY\": \"$HTTP_PROXY\","
fi
if [ -n "${HTTPS_PROXY:-}" ]; then
  PROXY_ENV="${PROXY_ENV}\"HTTPS_PROXY\": \"$HTTPS_PROXY\","
fi

cat > .mcp.json << EOF
{
  "mcpServers": {
    "zchat-channel": {
      "command": "$MCP_CMD",
      ${ARGS_LINE}
      "env": {
        "AGENT_NAME": "$AGENT_NAME",
        "IRC_SERVER": "$IRC_SERVER",
        "IRC_PORT": "$IRC_PORT",
        "IRC_CHANNELS": "$IRC_CHANNELS",
        "IRC_TLS": "$IRC_TLS",
        "IRC_PASSWORD": "${IRC_PASSWORD:-}",
        "IRC_SASL_USER": "${IRC_SASL_USER:-}",
        "IRC_SASL_PASS": "${IRC_SASL_PASS:-}",
        ${PROXY_ENV}
        "placeholder_": ""
      }
    }
  }
}
EOF

# Clean up trailing comma workaround: remove placeholder_ line
sed -i '' '/"placeholder_"/d' .mcp.json 2>/dev/null || sed -i '/"placeholder_"/d' .mcp.json

exec claude --permission-mode bypassPermissions \
  --dangerously-load-development-channels server:zchat-channel
