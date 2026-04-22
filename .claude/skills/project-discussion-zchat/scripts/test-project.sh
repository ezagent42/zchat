#!/bin/bash
set -euo pipefail

# Run unit tests for the project module (project CRUD + paths + defaults + config_cmd).
# Baseline: 65 passed (2026-04-22)

PROJECT="/home/yaosh/projects/zchat"
DRY_RUN=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [--dry-run] [--help]

Run project module unit tests (test_project* + test_paths + test_defaults + test_config_cmd).

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

CMD="cd $PROJECT && uv run pytest tests/unit/test_project.py tests/unit/test_project_cli_flow.py tests/unit/test_project_create_params.py tests/unit/test_project_use_command.py tests/unit/test_paths.py tests/unit/test_defaults.py tests/unit/test_config_cmd.py -v"

if $DRY_RUN; then
    echo "[dry-run] $CMD"
    exit 0
fi

cd "$PROJECT" && uv run pytest tests/unit/test_project.py tests/unit/test_project_cli_flow.py tests/unit/test_project_create_params.py tests/unit/test_project_use_command.py tests/unit/test_paths.py tests/unit/test_defaults.py tests/unit/test_config_cmd.py -v
