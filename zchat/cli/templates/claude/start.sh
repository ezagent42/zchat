#!/bin/bash
set -euo pipefail

# Parse MCP server command (first word = command, rest = args)
read -ra MCP_PARTS <<< "$MCP_SERVER_CMD"
MCP_CMD="${MCP_PARTS[0]}"
MCP_ARGS=("${MCP_PARTS[@]:1}")

mkdir -p .claude
cat > .claude/settings.local.json << 'EOF'
{
  "permissions": {
    "allow": [
      "mcp__zchat-channel__reply",
      "mcp__zchat-channel__join_channel"
    ]
  }
}
EOF

# Build .mcp.json
if [ ${#MCP_ARGS[@]} -gt 0 ]; then
  ARGS_JSON=$(printf '%s\n' "${MCP_ARGS[@]}" | jq -R . | jq -s .)
  ARGS_LINE="\"args\": $ARGS_JSON,"
else
  ARGS_LINE=""
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
        "IRC_TLS": "$IRC_TLS"
      }
    }
  }
}
EOF

exec claude --permission-mode bypassPermissions \
  --dangerously-load-development-channels server:zchat-channel
