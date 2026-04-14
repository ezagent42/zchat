#!/bin/bash
set -euo pipefail

# 验证所有脚本的 --help 和 --dry-run 模式。
# 用于确认脚本生成正确。

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PASS=0
FAIL=0
ERRORS=()

usage() {
    cat <<EOF
Usage: $(basename "$0") [--help]

Verify all scripts in the scripts/ directory support --help and --dry-run.

Options:
  --help   Show this help message
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help) usage ;;
        *) echo "Error: unknown option '$1'. Use --help for usage." >&2; exit 1 ;;
    esac
done

check() {
    local script="$1"
    local args="$2"
    local name
    name=$(basename "$script")

    if bash "$script" $args > /dev/null 2>&1; then
        echo "  PASS: $name $args"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $name $args"
        FAIL=$((FAIL + 1))
        ERRORS+=("$name $args")
    fi
}

echo "=== Self-Test: Verifying all scripts ==="
echo ""

# test-runner 脚本：检查 --help 和 --dry-run
echo "--- Test-runner scripts ---"
for script in "$SCRIPT_DIR"/test-*.sh; do
    [[ -f "$script" ]] || continue
    check "$script" "--help"
    check "$script" "--dry-run"
done

# close-issue.sh：需要额外参数
echo ""
echo "--- Tool scripts ---"
check "$SCRIPT_DIR/close-issue.sh" "--help"
check "$SCRIPT_DIR/close-issue.sh" "--issue-url https://example.com/1 --reason test --dry-run"

# refresh-index.sh：需要 --all
check "$SCRIPT_DIR/refresh-index.sh" "--help"
check "$SCRIPT_DIR/refresh-index.sh" "--all --dry-run"

echo ""
echo "=== Results ==="
echo "PASS: $PASS"
echo "FAIL: $FAIL"

if [[ $FAIL -gt 0 ]]; then
    echo ""
    echo "Failed checks:"
    for err in "${ERRORS[@]}"; do
        echo "  - $err"
    done
    exit 1
fi

echo "All checks passed."
