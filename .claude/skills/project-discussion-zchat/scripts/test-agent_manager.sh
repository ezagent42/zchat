#!/bin/bash
set -euo pipefail

# Run unit tests for the agent_manager module.
# Baseline: 25 passed (2026-04-22)

PROJECT="/home/yaosh/projects/zchat"
DRY_RUN=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [--dry-run] [--help]

Run agent_manager module unit tests (test_agent_manager.py + test_agent_focus_hide.py).

Options:
  --dry-run   Show the test command without executing
  --help      Show this help message
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --help) usage ;;
        *) echo "Error: unknown option '$1'. Use --help for usage." >&2; exit 1 ;;
    esac
done

CMD="cd $PROJECT && uv run pytest tests/unit/test_agent_manager.py tests/unit/test_agent_focus_hide.py -v"

if $DRY_RUN; then
    echo "[dry-run] $CMD"
    exit 0
fi

cd "$PROJECT" && uv run pytest tests/unit/test_agent_manager.py tests/unit/test_agent_focus_hide.py -v
