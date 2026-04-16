#!/bin/bash
set -euo pipefail

# Parse MCP server command (first word = command, rest = args)
read -ra MCP_PARTS <<< "$MCP_SERVER_CMD"
MCP_CMD="${MCP_PARTS[0]}"
MCP_ARGS=("${MCP_PARTS[@]:1}")

# --- Locate channel server plugin ---
# CHANNEL_PKG_DIR is set by zchat agent create (resolves via uv tool dir)
# Fallback to importlib.metadata for non-uv installs (editable dev mode)
if [ -z "${CHANNEL_PKG_DIR:-}" ]; then
  CHANNEL_PKG_DIR=$(python3 -c "
from importlib.metadata import files
for f in files('zchat-channel-server'):
    if f.name == 'server.py':
        print(f.locate().parent)
        break
" 2>/dev/null || echo "")
fi

# Copy plugin into workspace (copies instead of symlinks for reliable plugin detection)
if [ -n "$CHANNEL_PKG_DIR" ] && [ -d "$CHANNEL_PKG_DIR/.claude-plugin" ]; then
  rm -rf .claude-plugin commands
  cp -r "$CHANNEL_PKG_DIR/.claude-plugin" .claude-plugin
  cp -r "$CHANNEL_PKG_DIR/commands" commands
fi

# --- Copy soul.md from template ---
TEMPLATE_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$TEMPLATE_DIR/soul.md" ]; then
  cp "$TEMPLATE_DIR/soul.md" ./soul.md
fi

# --- Claude settings with SessionStart hook ---
mkdir -p .claude
READY_PATH="${ZCHAT_PROJECT_DIR}/agents/${AGENT_NAME}.ready"

jq -n \
  --arg ready_cmd "touch $READY_PATH" \
  '{
    hooks: {
      SessionStart: [{
        matcher: "startup",
        hooks: [{ type: "command", command: $ready_cmd }]
      }]
    },
    permissions: {
      allow: [
        "mcp__zchat-channel__reply",
        "mcp__zchat-channel__join_channel"
      ]
    },
    enabledPlugins: {
      "zchat@ezagent42": true,
      "dev-loop-skills@ezagent42": true
    }
  }' > .claude/settings.local.json

# --- Build .mcp.json ---
if [ ${#MCP_ARGS[@]} -gt 0 ]; then
  ARGS_JSON=$(printf '%s\n' "${MCP_ARGS[@]}" | jq -R . | jq -s .)
  ARGS_LINE="\"args\": $ARGS_JSON,"
else
  ARGS_LINE=""
fi

# Build env object with jq for valid JSON (no trailing comma issues)
ENV_JSON=$(jq -n \
  --arg agent "$AGENT_NAME" \
  --arg server "$IRC_SERVER" \
  --arg port "$IRC_PORT" \
  --arg channels "$IRC_CHANNELS" \
  --arg tls "$IRC_TLS" \
  --arg password "${IRC_PASSWORD:-}" \
  --arg auth_token "${IRC_AUTH_TOKEN:-}" \
  '{
    AGENT_NAME: $agent,
    IRC_SERVER: $server,
    IRC_PORT: $port,
    IRC_CHANNELS: $channels,
    IRC_TLS: $tls,
    IRC_PASSWORD: $password,
    IRC_AUTH_TOKEN: $auth_token
  }')

# Add proxy env if set
if [ -n "${HTTP_PROXY:-}" ]; then
  ENV_JSON=$(echo "$ENV_JSON" | jq --arg v "$HTTP_PROXY" '. + {HTTP_PROXY: $v}')
fi
if [ -n "${HTTPS_PROXY:-}" ]; then
  ENV_JSON=$(echo "$ENV_JSON" | jq --arg v "$HTTPS_PROXY" '. + {HTTPS_PROXY: $v}')
fi

# Build server config object
SERVER_JSON=$(jq -n --arg cmd "$MCP_CMD" --argjson env "$ENV_JSON" '{command: $cmd, env: $env}')

# Add args if present
if [ ${#MCP_ARGS[@]} -gt 0 ]; then
  ARGS_JSON=$(printf '%s\n' "${MCP_ARGS[@]}" | jq -R . | jq -s .)
  SERVER_JSON=$(echo "$SERVER_JSON" | jq --argjson args "$ARGS_JSON" '. + {args: $args}')
fi

# Write .mcp.json
jq -n --argjson srv "$SERVER_JSON" '{"mcpServers": {"zchat-channel": $srv}}' > .mcp.json

exec -a "zchat-claude-agent" claude --permission-mode bypassPermissions \
  --dangerously-load-development-channels server:zchat-channel
