#!/bin/bash
# Pre-release acceptance test runner
# Usage:
#   ./tests/pre_release/run.sh                    # editable install (default)
#   ZCHAT_CMD=zchat ./tests/pre_release/run.sh    # Homebrew binary
#   ./tests/pre_release/run.sh --include-manual    # include auth/self-update tests
set -euo pipefail

cd "$(dirname "$0")/../.."

MARKER="prerelease and not manual"
if [[ "${1:-}" == "--include-manual" ]]; then
    MARKER="prerelease"
    shift
fi

echo "=== Pre-release E2E Tests ==="
echo "ZCHAT_CMD: ${ZCHAT_CMD:-zchat (default)}"
echo "Marker:    $MARKER"
echo ""

exec uv run pytest tests/pre_release/ -v -m "$MARKER" --timeout=120 -p pytest_order --order-scope=module "$@"
