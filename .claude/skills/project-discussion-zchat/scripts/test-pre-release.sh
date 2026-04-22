#!/bin/bash
set -euo pipefail

# Run the pre-release CLI walkthrough (asciinema recording).
# Manual review: read the produced .cast / .gif files.

PROJECT="/home/yaosh/projects/zchat"
DRY_RUN=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [--dry-run] [--help]

Run the pre-release walkthrough (tests/pre_release/walkthrough.sh).
Needs asciinema + agg installed. Products: .cast + auto-generated .gif.

Options:
  --dry-run   Show the command without executing
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

CMD="cd $PROJECT && ./tests/pre_release/walkthrough.sh"

if $DRY_RUN; then
    echo "[dry-run] $CMD"
    exit 0
fi

cd "$PROJECT" && ./tests/pre_release/walkthrough.sh
