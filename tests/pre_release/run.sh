#!/bin/bash
# Pre-release acceptance test runner
# Usage:
#   ./tests/pre_release/run.sh                    # editable install (default)
#   ZCHAT_CMD=zchat ./tests/pre_release/run.sh    # Homebrew binary
#   ./tests/pre_release/run.sh --include-manual    # include auth/self-update tests
#   ./tests/pre_release/run.sh --pre-release-report-dir /tmp/pr-reports
#   ./tests/pre_release/run.sh --no-pre-release-report
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
echo "Report:    tests/pre_release/reports/pre-release-report-*.{json,md} (default)"
echo ""

exec uv run pytest tests/pre_release/ -v -m "$MARKER" --timeout=120 -p pytest_order --order-scope=module "$@"
