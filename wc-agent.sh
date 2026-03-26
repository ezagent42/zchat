#!/bin/bash
# wc-agent — CLI wrapper
# Runs the wc-agent Typer CLI with proper uv project context
# Respects WC_AGENT_HOME env var if set (e.g., for testing)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec env ${WC_AGENT_HOME:+WC_AGENT_HOME="$WC_AGENT_HOME"} \
    uv run --project "$SCRIPT_DIR/wc-agent" python -m wc_agent.cli "$@"
