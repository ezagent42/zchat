#!/bin/bash
# e2e-cleanup.sh — Clean up manual test environment
#
# Usage: source tests/e2e/e2e-cleanup.sh

if [ -z "$E2E_ID" ]; then
    echo "No e2e environment to clean (E2E_ID not set)."
    return 0 2>/dev/null || exit 0
fi

echo "Cleaning up e2e-${E2E_ID}..."

# Stop agents + weechat
[ -n "$PROJECT_DIR" ] && cd "$PROJECT_DIR"
[ -n "$WC_AGENT_HOME" ] && ./wc-agent.sh shutdown 2>/dev/null || true

# Kill ergo
[ -n "$E2E_ERGO_PID" ] && kill "$E2E_ERGO_PID" 2>/dev/null
lsof -ti :"${E2E_IRC_PORT}" 2>/dev/null | xargs kill 2>/dev/null

# Remove temp dirs
rm -rf "/tmp/e2e-ergo-${E2E_ID}" "$WC_AGENT_HOME"

# Unset env vars
unset E2E_ID E2E_IRC_PORT E2E_ERGO_DIR E2E_ERGO_PID WC_AGENT_HOME

echo "Done."
