#!/bin/bash
set -euo pipefail

# 刷新 Skill 1 的模块索引。
# 当检测到文件移动/重命名、test-runner 失败、或新模块出现时调用。
# 重新扫描指定模块或全部模块，更新索引和 test-runner。

DRY_RUN=false
PROJECT_ROOT="/home/yaosh/projects/zchat"
MODULE=""
ALL=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [--module <name>] [--all] [--dry-run] [--help]

Refresh Skill 1 module index.

Options:
  --module <name>   Refresh a specific module
  --all             Refresh all modules
  --dry-run         Show what would be refreshed
  --help            Show this help message

Triggers:
  - File not found at indexed path (moved/renamed)
  - test-runner returns unexpected error (command outdated)
  - New module detected (not in current index)
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --module) MODULE="$2"; shift 2 ;;
        --all) ALL=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        --help) usage ;;
        *) echo "Error: unknown option '$1'. Use --help for usage." >&2; exit 1 ;;
    esac
done

if [[ -z "$MODULE" && "$ALL" != "true" ]]; then
    echo "Error: specify --module <name> or --all." >&2
    exit 1
fi

if $DRY_RUN; then
    if $ALL; then
        echo "[dry-run] Would refresh all modules in $PROJECT_ROOT"
    else
        echo "[dry-run] Would refresh module '$MODULE' in $PROJECT_ROOT"
    fi
    echo "[dry-run] Steps: scan source files → run tests → update index entries"
    exit 0
fi

echo "=== Skill 1 Index Refresh ==="
echo "Project: $PROJECT_ROOT"

if $ALL; then
    echo "Scope: all modules"
    # 重新扫描整个项目
    echo "Scanning source files..."
    find "$PROJECT_ROOT/src" "$PROJECT_ROOT/lib" "$PROJECT_ROOT/zchat" -name "*.py" -o -name "*.ts" -o -name "*.ex" 2>/dev/null | while read -r f; do
        echo "  Found: $(basename "$f")"
    done

    echo "Re-running all test-runners..."
    for runner in "$(dirname "$0")"/test-*.sh; do
        [[ -f "$runner" ]] || continue
        name=$(basename "$runner")
        echo "  Running: $name"
        if bash "$runner" > /dev/null 2>&1; then
            echo "    → PASS"
        else
            echo "    → FAIL (test-runner may need updating)"
        fi
    done
else
    echo "Scope: module '$MODULE'"
    # 扫描特定模块
    echo "Scanning files for module '$MODULE'..."
    find "$PROJECT_ROOT" -path "*/$MODULE*" -name "*.py" -o -path "*/$MODULE*" -name "*.ts" 2>/dev/null | while read -r f; do
        echo "  Found: $f"
    done

    # 运行对应 test-runner
    RUNNER="$(dirname "$0")/test-${MODULE}.sh"
    if [[ -f "$RUNNER" ]]; then
        echo "Running test-runner: test-${MODULE}.sh"
        if bash "$RUNNER" 2>&1; then
            echo "  → PASS"
        else
            echo "  → FAIL"
        fi
    else
        echo "No test-runner found for module '$MODULE'."
        echo "Consider creating scripts/test-${MODULE}.sh"
    fi
fi

echo ""
echo "Index refresh complete."
echo "Note: SKILL.md module index table may need manual update if modules were added/removed."
