#!/bin/bash
set -euo pipefail

# Dev-Loop Skills E2E 验证脚本
# 在每个 skill 执行完后运行，独立验证产出物是否真实存在、内容是否合规。
# 不依赖被测 skill 的输出——直接检查磁盘上的文件。

PROJECT_ROOT="/home/yaosh/projects/zchat"
ARTIFACTS="$PROJECT_ROOT/.artifacts"
PASS=0
FAIL=0

usage() {
    cat <<'EOF'
Usage: verify-skill-output.sh <skill-number> [options]

Verify that a skill actually produced what it claimed.

Arguments:
  skill-number    Which skill to verify (1-6, or "chain" for full pipeline)

Options:
  --before <snapshot>   Path to registry.json snapshot taken BEFORE skill ran
  --artifact <path>     Path to specific artifact to verify
  --dry-run             Show what would be checked
  --help                Show this help

Examples:
  # Before running a skill, snapshot registry:
  cp .artifacts/registry.json /tmp/registry-before.json

  # After skill runs, verify:
  ./verify-skill-output.sh 2 --before /tmp/registry-before.json
  ./verify-skill-output.sh 5 --artifact .artifacts/eval-docs/eval-xxx.md
  ./verify-skill-output.sh chain   # verify full Phase 1→5 chain
EOF
    exit 0
}

check() {
    local desc="$1" result="$2"
    if [ "$result" = "true" ]; then
        echo "  ✅ $desc"
        PASS=$((PASS + 1))
    else
        echo "  ❌ $desc"
        FAIL=$((FAIL + 1))
    fi
}

# --- 通用检查 ---

check_file_exists() {
    local path="$1" desc="$2"
    check "$desc: $path exists" "$([ -f "$path" ] && echo true || echo false)"
}

check_yaml_frontmatter() {
    local path="$1"
    local has_fm=$(head -1 "$path" | grep -c '^---' || true)
    check "YAML frontmatter present" "$([ "$has_fm" -gt 0 ] && echo true || echo false)"

    if [ "$has_fm" -gt 0 ]; then
        local has_type=$(sed -n '/^---$/,/^---$/p' "$path" | grep -c '^type:' || true)
        local has_id=$(sed -n '/^---$/,/^---$/p' "$path" | grep -c '^id:' || true)
        local has_status=$(sed -n '/^---$/,/^---$/p' "$path" | grep -c '^status:' || true)
        check "frontmatter has 'type' field" "$([ "$has_type" -gt 0 ] && echo true || echo false)"
        check "frontmatter has 'id' field" "$([ "$has_id" -gt 0 ] && echo true || echo false)"
        check "frontmatter has 'status' field" "$([ "$has_status" -gt 0 ] && echo true || echo false)"
    fi
}

check_registry_changed() {
    local before="$1"
    local after="$ARTIFACTS/registry.json"
    if [ ! -f "$before" ]; then
        echo "  ⚠️  No --before snapshot, skipping registry diff"
        return
    fi
    local before_count=$(grep -c '"id"' "$before" || true)
    local after_count=$(grep -c '"id"' "$after" || true)
    check "registry has new entries ($before_count → $after_count)" \
        "$([ "$after_count" -gt "$before_count" ] && echo true || echo false)"
}

check_file_line_refs() {
    # 从 markdown 文件中提取 file:line 引用，验证源文件中对应行是否存在
    local md_file="$1"
    local ref_count=0
    local valid_count=0

    # 匹配 xxx.py:123 格式
    while IFS= read -r ref; do
        file=$(echo "$ref" | cut -d: -f1)
        line=$(echo "$ref" | cut -d: -f2)
        ref_count=$((ref_count + 1))

        # 尝试在项目中找到文件
        found=$(find "$PROJECT_ROOT" -path "*/$file" -type f 2>/dev/null | head -1)
        if [ -n "$found" ] && [ -n "$line" ] && [ "$line" -gt 0 ] 2>/dev/null; then
            total_lines=$(wc -l < "$found")
            if [ "$line" -le "$total_lines" ]; then
                valid_count=$((valid_count + 1))
            fi
        fi
    done < <(grep -oP '[a-zA-Z_/]+\.py:\d+' "$md_file" 2>/dev/null | sort -u | head -20)

    if [ "$ref_count" -gt 0 ]; then
        check "file:line refs valid ($valid_count/$ref_count)" \
            "$([ "$valid_count" -eq "$ref_count" ] && echo true || echo false)"
    else
        check "contains file:line references" "false"
    fi
}

check_test_actually_ran() {
    # 检查 pytest 是否真的在最近 N 分钟内执行过
    local minutes="${1:-5}"
    local cache="$PROJECT_ROOT/.pytest_cache/v/cache/lastfailed"
    local stepfile="$PROJECT_ROOT/.pytest_cache/v/cache/stepwise"
    local ran=false

    # 检查 .pytest_cache 是否在最近被修改
    if find "$PROJECT_ROOT/.pytest_cache" -mmin "-$minutes" -type f 2>/dev/null | grep -q .; then
        ran=true
    fi
    # 也检查 __pycache__ 时间戳
    if find "$PROJECT_ROOT/tests" -name "*.pyc" -mmin "-$minutes" 2>/dev/null | grep -q .; then
        ran=true
    fi
    check "pytest ran within last ${minutes} minutes" "$ran"
}

# --- Skill 特定检查 ---

BEFORE_SNAPSHOT=""
ARTIFACT_PATH=""
SKILL=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --before) BEFORE_SNAPSHOT="$2"; shift 2 ;;
        --artifact) ARTIFACT_PATH="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --help) usage ;;
        *) SKILL="$1"; shift ;;
    esac
done

if [ -z "$SKILL" ]; then
    echo "Error: specify skill number (1-6) or 'chain'"
    echo "Run with --help for usage"
    exit 1
fi

if $DRY_RUN; then
    echo "[dry-run] Would verify skill $SKILL outputs in $ARTIFACTS"
    exit 0
fi

echo "=== Verify Skill $SKILL Output ==="
echo "Project: $PROJECT_ROOT"
echo "Artifacts: $ARTIFACTS"
echo ""

case "$SKILL" in
    1)
        echo "--- Skill 1: project-discussion-zchat ---"
        echo "验证问答输出是否包含实证"
        if [ -n "$ARTIFACT_PATH" ]; then
            check_file_exists "$ARTIFACT_PATH" "输出文件"
            check_file_line_refs "$ARTIFACT_PATH"
            # 检查输出中是否包含测试运行结果的痕迹
            has_test_output=$(grep -cE '(passed|failed|PASSED|FAILED|test session starts)' "$ARTIFACT_PATH" 2>/dev/null || true)
            check "output contains test execution evidence" \
                "$([ "$has_test_output" -gt 0 ] && echo true || echo false)"
        else
            echo "  ⚠️  Use --artifact <path-to-skill1-output.md> to verify a specific answer"
        fi
        ;;

    2)
        echo "--- Skill 2: test-plan-generator ---"
        echo "验证 test-plan artifact 是否生成"
        if [ -n "$ARTIFACT_PATH" ]; then
            check_file_exists "$ARTIFACT_PATH" "test-plan"
            check_yaml_frontmatter "$ARTIFACT_PATH"
            # 检查 type 是否为 test-plan
            has_type=$(grep -c '^type: test-plan' "$ARTIFACT_PATH" 2>/dev/null || true)
            check "type is 'test-plan'" "$([ "$has_type" -gt 0 ] && echo true || echo false)"
            # 检查是否有 TC- 编号的用例
            tc_count=$(grep -c '^### TC-' "$ARTIFACT_PATH" 2>/dev/null || true)
            check "contains test cases (TC-* format, found $tc_count)" \
                "$([ "$tc_count" -gt 0 ] && echo true || echo false)"
            # 检查是否有统计表
            has_stats=$(grep -c '总用例数' "$ARTIFACT_PATH" 2>/dev/null || true)
            check "contains statistics table" "$([ "$has_stats" -gt 0 ] && echo true || echo false)"
        else
            # 检查 .artifacts/test-plans/ 是否有新文件
            plan_count=$(find "$ARTIFACTS/test-plans" -name "*.md" -type f 2>/dev/null | wc -l)
            check "test-plans/ has files ($plan_count found)" \
                "$([ "$plan_count" -gt 0 ] && echo true || echo false)"
        fi
        [ -n "$BEFORE_SNAPSHOT" ] && check_registry_changed "$BEFORE_SNAPSHOT"
        ;;

    3)
        echo "--- Skill 3: test-code-writer ---"
        echo "验证 E2E 测试代码是否实际写入"
        if [ -n "$ARTIFACT_PATH" ]; then
            check_file_exists "$ARTIFACT_PATH" "test-diff"
            check_yaml_frontmatter "$ARTIFACT_PATH"
        fi
        # 检查 tests/e2e/ 下是否有新的或修改的 .py 文件（最近 10 分钟）
        new_tests=$(find "$PROJECT_ROOT/tests/e2e" -name "test_*.py" -mmin -10 -type f 2>/dev/null | wc -l)
        check "E2E test files created/modified in last 10 min ($new_tests found)" \
            "$([ "$new_tests" -gt 0 ] && echo true || echo false)"
        # 检查新代码是否包含 @pytest.mark.e2e
        if [ "$new_tests" -gt 0 ]; then
            marked=$(find "$PROJECT_ROOT/tests/e2e" -name "test_*.py" -mmin -10 -exec grep -l "pytest.mark.e2e" {} \; 2>/dev/null | wc -l)
            check "new test files have @pytest.mark.e2e ($marked/$new_tests)" \
                "$([ "$marked" -eq "$new_tests" ] && echo true || echo false)"
        fi
        [ -n "$BEFORE_SNAPSHOT" ] && check_registry_changed "$BEFORE_SNAPSHOT"
        ;;

    4)
        echo "--- Skill 4: test-runner ---"
        echo "验证测试是否实际执行 + report 是否生成"
        check_test_actually_ran 10
        if [ -n "$ARTIFACT_PATH" ]; then
            check_file_exists "$ARTIFACT_PATH" "e2e-report"
            check_yaml_frontmatter "$ARTIFACT_PATH"
            has_type=$(grep -c '^type: e2e-report' "$ARTIFACT_PATH" 2>/dev/null || true)
            check "type is 'e2e-report'" "$([ "$has_type" -gt 0 ] && echo true || echo false)"
            # 检查有结果汇总表
            has_summary=$(grep -cE '(passed|failed|新增|回归)' "$ARTIFACT_PATH" 2>/dev/null || true)
            check "report has result summary ($has_summary matches)" \
                "$([ "$has_summary" -gt 2 ] && echo true || echo false)"
        else
            report_count=$(find "$ARTIFACTS/e2e-reports" -name "*.md" -type f 2>/dev/null | wc -l)
            check "e2e-reports/ has files ($report_count found)" \
                "$([ "$report_count" -gt 0 ] && echo true || echo false)"
        fi
        [ -n "$BEFORE_SNAPSHOT" ] && check_registry_changed "$BEFORE_SNAPSHOT"
        ;;

    5)
        echo "--- Skill 5: feature-eval ---"
        echo "验证 eval-doc 是否生成"
        if [ -n "$ARTIFACT_PATH" ]; then
            check_file_exists "$ARTIFACT_PATH" "eval-doc"
            check_yaml_frontmatter "$ARTIFACT_PATH"
            has_type=$(grep -c '^type: eval-doc' "$ARTIFACT_PATH" 2>/dev/null || true)
            check "type is 'eval-doc'" "$([ "$has_type" -gt 0 ] && echo true || echo false)"
            has_mode=$(grep -cE '^mode: "?(simulate|verify)"?' "$ARTIFACT_PATH" 2>/dev/null || true)
            check "has mode field (simulate/verify)" "$([ "$has_mode" -gt 0 ] && echo true || echo false)"
            # 检查有 testcase 表格
            has_table=$(grep -c '|.*场景.*|' "$ARTIFACT_PATH" 2>/dev/null || true)
            check "has testcase table ($has_table rows)" \
                "$([ "$has_table" -gt 0 ] && echo true || echo false)"
        else
            eval_count=$(find "$ARTIFACTS/eval-docs" -name "*.md" -type f 2>/dev/null | wc -l)
            check "eval-docs/ has files ($eval_count found)" \
                "$([ "$eval_count" -gt 0 ] && echo true || echo false)"
        fi
        [ -n "$BEFORE_SNAPSHOT" ] && check_registry_changed "$BEFORE_SNAPSHOT"
        ;;

    6)
        echo "--- Skill 6: artifact-registry ---"
        echo "验证 registry 操作"
        check_file_exists "$ARTIFACTS/registry.json" "registry.json"
        # 验证 JSON 有效
        if command -v jq &>/dev/null; then
            jq_ok=$(jq empty "$ARTIFACTS/registry.json" 2>/dev/null && echo true || echo false)
            check "registry.json is valid JSON" "$jq_ok"
        elif command -v python3 &>/dev/null; then
            py_ok=$(python3 -c "import json; json.load(open('$ARTIFACTS/registry.json'))" 2>/dev/null && echo true || echo false)
            check "registry.json is valid JSON" "$py_ok"
        fi
        artifact_count=$(grep -c '"id"' "$ARTIFACTS/registry.json" 2>/dev/null || true)
        check "registry has entries ($artifact_count)" \
            "$([ "$artifact_count" -gt 0 ] && echo true || echo false)"
        [ -n "$BEFORE_SNAPSHOT" ] && check_registry_changed "$BEFORE_SNAPSHOT"
        ;;

    chain)
        echo "--- Full Pipeline Chain Verification ---"
        echo "验证 Phase 1→5 完整链条"
        echo ""

        # 1. eval-doc 存在
        eval_count=$(find "$ARTIFACTS/eval-docs" -name "*.md" -type f 2>/dev/null | wc -l)
        check "[Phase 1] eval-docs/ has files ($eval_count)" \
            "$([ "$eval_count" -gt 0 ] && echo true || echo false)"

        # 2. test-plan 存在且引用了 eval-doc
        plan_count=$(find "$ARTIFACTS/test-plans" -name "*.md" -type f 2>/dev/null | wc -l)
        check "[Phase 3] test-plans/ has files ($plan_count)" \
            "$([ "$plan_count" -gt 0 ] && echo true || echo false)"
        if [ "$plan_count" -gt 0 ]; then
            latest_plan=$(ls -t "$ARTIFACTS/test-plans/"*.md 2>/dev/null | head -1)
            has_related=$(grep -c 'eval-' "$latest_plan" 2>/dev/null || true)
            check "[Phase 3] latest test-plan references eval-doc" \
                "$([ "$has_related" -gt 0 ] && echo true || echo false)"
        fi

        # 3. test-diff 存在
        diff_count=$(find "$ARTIFACTS/test-diffs" -name "*.md" -type f 2>/dev/null | wc -l)
        check "[Phase 4] test-diffs/ has files ($diff_count)" \
            "$([ "$diff_count" -gt 0 ] && echo true || echo false)"

        # 4. e2e-report 存在
        report_count=$(find "$ARTIFACTS/e2e-reports" -name "*.md" -type f 2>/dev/null | wc -l)
        check "[Phase 5] e2e-reports/ has files ($report_count)" \
            "$([ "$report_count" -gt 0 ] && echo true || echo false)"

        # 5. registry 有完整链条
        total_artifacts=$(grep -c '"id"' "$ARTIFACTS/registry.json" 2>/dev/null || true)
        check "[Registry] total artifacts registered ($total_artifacts)" \
            "$([ "$total_artifacts" -ge 4 ] && echo true || echo false)"

        # 6. 实际测试代码存在
        e2e_files=$(find "$PROJECT_ROOT/tests/e2e" -name "test_*.py" -type f 2>/dev/null | wc -l)
        check "[Code] E2E test files exist ($e2e_files)" \
            "$([ "$e2e_files" -gt 0 ] && echo true || echo false)"

        # 7. pytest 确实跑过
        check_test_actually_ran 30
        ;;

    *)
        echo "Unknown skill: $SKILL"
        echo "Use 1-6 or 'chain'"
        exit 1
        ;;
esac

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -gt 0 ] && exit 1 || exit 0
