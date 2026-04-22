#!/bin/bash
set -euo pipefail

# Run unit tests for the runner module (template resolution + .env rendering).
# Baseline: 11 passed (2026-04-22)
# Note: runner + templates share test files; test_runner.py does not exist in V6

PROJECT="/home/yaosh/projects/zchat"
DRY_RUN=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [--dry-run] [--help]

Run runner module unit tests (test_template_loader + test_start_sh).

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

CMD="cd $PROJECT && uv run pytest tests/unit/test_template_loader.py tests/unit/test_start_sh.py -v"

if $DRY_RUN; then
    echo "[dry-run] $CMD"
    exit 0
fi

cd "$PROJECT" && uv run pytest tests/unit/test_template_loader.py tests/unit/test_start_sh.py -v
