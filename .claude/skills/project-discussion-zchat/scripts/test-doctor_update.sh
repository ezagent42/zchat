#!/bin/bash
set -euo pipefail

# Run unit tests for the doctor_update module (doctor + update + audit_cmd).
# Baseline: 43 passed (2026-04-22)

PROJECT="/home/yaosh/projects/zchat"
DRY_RUN=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [--dry-run] [--help]

Run doctor_update module unit tests (test_doctor.py + test_update.py + test_audit_cli.py).

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

CMD="cd $PROJECT && uv run pytest tests/unit/test_doctor.py tests/unit/test_update.py tests/unit/test_audit_cli.py -v"

if $DRY_RUN; then
    echo "[dry-run] $CMD"
    exit 0
fi

cd "$PROJECT" && uv run pytest tests/unit/test_doctor.py tests/unit/test_update.py tests/unit/test_audit_cli.py -v
