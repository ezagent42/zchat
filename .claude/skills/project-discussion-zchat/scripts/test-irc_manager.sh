#!/bin/bash
set -euo pipefail

# Run unit tests for the irc_manager module.
# Baseline: 32 passed (2026-04-22)

PROJECT="/home/yaosh/projects/zchat"
DRY_RUN=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [--dry-run] [--help]

Run irc_manager module unit tests (ergo daemon + WeeChat zellij tab + WSL2 proxy).

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

CMD="cd $PROJECT && uv run pytest tests/unit/test_irc_manager_languages.py tests/unit/test_irc_manager_weechat_cmd.py tests/unit/test_irc_check.py tests/unit/test_wsl2_proxy_rewrite.py -v"

if $DRY_RUN; then
    echo "[dry-run] $CMD"
    exit 0
fi

cd "$PROJECT" && uv run pytest tests/unit/test_irc_manager_languages.py tests/unit/test_irc_manager_weechat_cmd.py tests/unit/test_irc_check.py tests/unit/test_wsl2_proxy_rewrite.py -v
