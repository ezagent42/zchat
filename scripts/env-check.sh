#!/bin/bash
# env-check.sh — E2E environment pre-flight check
#
# Checks all dependencies required by the pytest E2E suite (tests/e2e/).
# Outputs structured JSON to stdout and human-readable results to stderr.
#
# Usage:
#   bash scripts/env-check.sh --project-root /path/to/zchat
#   bash scripts/env-check.sh --project-root /path/to/zchat --dry-run
#   bash scripts/env-check.sh --help

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
PROJECT_ROOT=""
DRY_RUN=false

# ── Usage ─────────────────────────────────────────────────────────────────────
usage() {
  cat >&2 <<EOF
Usage: $(basename "$0") --project-root <path> [--dry-run] [--help]

Options:
  --project-root   Path to the zchat project root (required)
  --dry-run        Print what would be checked without running checks
  --help           Show this help message
EOF
  exit 0
}

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root) PROJECT_ROOT="$2"; shift 2 ;;
    --dry-run)      DRY_RUN=true; shift ;;
    --help|-h)      usage ;;
    *) echo "Unknown option: $1" >&2; usage ;;
  esac
done

if [[ -z "$PROJECT_ROOT" ]]; then
  echo "ERROR: --project-root is required" >&2
  usage
fi

PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd)"

# ── State ─────────────────────────────────────────────────────────────────────
declare -a CHECK_NAMES=()
declare -a CHECK_STATUSES=()   # pass | fail | warn
declare -a CHECK_DETAILS=()
declare -a CHECK_LEVELS=()     # hard | soft

HARD_FAIL=0
SOFT_FAIL=0

# ── Helpers ───────────────────────────────────────────────────────────────────
add_result() {
  local name="$1" level="$2" status="$3" detail="$4"
  CHECK_NAMES+=("$name")
  CHECK_LEVELS+=("$level")
  CHECK_STATUSES+=("$status")
  CHECK_DETAILS+=("$detail")
  if [[ "$status" == "fail" && "$level" == "hard" ]]; then
    ((HARD_FAIL++)) || true
  fi
  if [[ "$status" == "fail" && "$level" == "soft" ]]; then
    ((SOFT_FAIL++)) || true
  fi
}

log() { echo "$@" >&2; }

check_cmd() {
  local name="$1" cmd="$2" level="$3" purpose="$4"
  if command -v "$cmd" &>/dev/null; then
    local ver
    ver=$("$cmd" --version 2>&1 | head -1) || ver="(version unknown)"
    add_result "$name" "$level" "pass" "$ver"
  else
    add_result "$name" "$level" "fail" "Not found in PATH — $purpose"
  fi
}

check_port_free() {
  local port="$1"
  if command -v ss &>/dev/null; then
    if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
      return 1
    fi
  elif command -v netstat &>/dev/null; then
    if netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
      return 1
    fi
  fi
  return 0
}

# ── Checks ────────────────────────────────────────────────────────────────────

run_checks() {
  # ── Hard dependencies ────────────────────────────────────────────────────

  # 1. uv (Python runner / dependency manager)
  check_cmd "uv" "uv" "hard" "Required to run pytest and manage dependencies"

  # 2. Python (via uv)
  if command -v uv &>/dev/null; then
    local pyver
    pyver=$(uv run python --version 2>&1) || pyver=""
    if [[ -n "$pyver" ]]; then
      add_result "python" "hard" "pass" "$pyver (via uv)"
    else
      add_result "python" "hard" "fail" "uv run python failed"
    fi
  else
    add_result "python" "hard" "fail" "Cannot check — uv not available"
  fi

  # 3. pytest (via uv)
  if command -v uv &>/dev/null; then
    local pytestver
    pytestver=$(cd "$PROJECT_ROOT" && uv run python -m pytest --version 2>&1 | head -1) || pytestver=""
    if [[ "$pytestver" == *"pytest"* ]]; then
      add_result "pytest" "hard" "pass" "$pytestver"
    else
      add_result "pytest" "hard" "fail" "pytest not importable via uv run — run 'uv sync' first"
    fi
  else
    add_result "pytest" "hard" "fail" "Cannot check — uv not available"
  fi

  # 4. zellij (terminal multiplexer for E2E automation)
  check_cmd "zellij" "zellij" "hard" "E2E tests use Zellij for session/tab management"

  # 5. ergo (IRC server)
  check_cmd "ergo" "ergo" "hard" "E2E tests start a local ergo IRC server"

  # 6. E2E test directory exists and has test files
  local e2e_dir="$PROJECT_ROOT/tests/e2e"
  if [[ -d "$e2e_dir" ]]; then
    local test_count
    test_count=$(find "$e2e_dir" -name 'test_*.py' -type f | wc -l)
    if [[ "$test_count" -gt 0 ]]; then
      add_result "e2e-tests" "hard" "pass" "$test_count test file(s) in tests/e2e/"
    else
      add_result "e2e-tests" "hard" "fail" "tests/e2e/ exists but contains no test_*.py files"
    fi
  else
    add_result "e2e-tests" "hard" "fail" "tests/e2e/ directory not found"
  fi

  # 7. zchat-channel-server submodule present
  local cs_dir="$PROJECT_ROOT/zchat-channel-server"
  if [[ -d "$cs_dir" && -f "$cs_dir/pyproject.toml" ]]; then
    add_result "channel-server" "hard" "pass" "zchat-channel-server/ submodule present"
  else
    add_result "channel-server" "hard" "fail" "zchat-channel-server/ missing — run 'git submodule update --init'"
  fi

  # 8. zchat-protocol submodule present
  local proto_dir="$PROJECT_ROOT/zchat-protocol"
  if [[ -d "$proto_dir" && -f "$proto_dir/pyproject.toml" ]]; then
    add_result "zchat-protocol" "hard" "pass" "zchat-protocol/ submodule present"
  else
    add_result "zchat-protocol" "hard" "fail" "zchat-protocol/ missing — run 'git submodule update --init'"
  fi

  # 9. IRC test port range available (16667-17667)
  local sample_port=16667
  if check_port_free "$sample_port"; then
    add_result "irc-port" "hard" "pass" "Port $sample_port available (E2E uses 16667 + pid%1000)"
  else
    add_result "irc-port" "hard" "fail" "Port $sample_port in use — E2E ergo server may fail to bind"
  fi

  # ── Soft dependencies ────────────────────────────────────────────────────

  # 10. weechat (only needed for WeeChat-specific test phases)
  check_cmd "weechat" "weechat" "soft" "Needed for WeeChat integration tests (test_weechat_connects, etc.)"

  # 11. tmux (used by e2e-setup.sh for manual testing)
  check_cmd "tmux" "tmux" "soft" "Used for manual E2E testing (e2e-setup.sh), not automated pytest"

  # 12. asciinema (evidence capture / pre-release recording)
  check_cmd "asciinema" "asciinema" "soft" "Evidence capture and pre-release walkthrough recording"

  # 13. claude.local.env (proxy/API key env file)
  local env_file="$PROJECT_ROOT/claude.local.env"
  if [[ -f "$env_file" ]]; then
    add_result "env-file" "soft" "pass" "claude.local.env found"
  else
    add_result "env-file" "soft" "fail" "claude.local.env not found — agent tests needing API keys may fail"
  fi

  # 14. uv sync status (dependencies up to date)
  if command -v uv &>/dev/null; then
    local sync_out
    sync_out=$(cd "$PROJECT_ROOT" && uv sync --dry-run 2>&1) || sync_out=""
    if echo "$sync_out" | grep -qi "would install\|would update\|would uninstall"; then
      add_result "uv-sync" "soft" "fail" "Dependencies out of date — run 'uv sync'"
    else
      add_result "uv-sync" "soft" "pass" "Dependencies up to date"
    fi
  else
    add_result "uv-sync" "soft" "fail" "Cannot check — uv not available"
  fi

  # 15. conftest.py exists (test fixtures)
  if [[ -f "$e2e_dir/conftest.py" ]]; then
    add_result "conftest" "soft" "pass" "tests/e2e/conftest.py present"
  else
    add_result "conftest" "soft" "fail" "tests/e2e/conftest.py missing — fixtures unavailable"
  fi
}

# ── Output ────────────────────────────────────────────────────────────────────

print_human() {
  log ""
  log "╔══════════════════════════════════════════════════════════════╗"
  log "║  zchat E2E Environment Check                               ║"
  log "╠══════════════════════════════════════════════════════════════╣"
  log "║  Project: $PROJECT_ROOT"
  log "╚══════════════════════════════════════════════════════════════╝"
  log ""

  local i
  for i in "${!CHECK_NAMES[@]}"; do
    local name="${CHECK_NAMES[$i]}"
    local level="${CHECK_LEVELS[$i]}"
    local status="${CHECK_STATUSES[$i]}"
    local detail="${CHECK_DETAILS[$i]}"

    local icon tag
    case "$status" in
      pass) icon="[PASS]" ;;
      fail)
        if [[ "$level" == "hard" ]]; then
          icon="[FAIL]"
        else
          icon="[WARN]"
        fi
        ;;
      *) icon="[????]" ;;
    esac

    if [[ "$level" == "hard" ]]; then
      tag="(hard)"
    else
      tag="(soft)"
    fi

    printf "  %-6s %-20s %-6s %s\n" "$icon" "$name" "$tag" "$detail" >&2
  done

  log ""
  if [[ $HARD_FAIL -gt 0 ]]; then
    log "  RESULT: BLOCKED — $HARD_FAIL hard dependency failure(s). Fix before running E2E tests."
  elif [[ $SOFT_FAIL -gt 0 ]]; then
    log "  RESULT: READY (with $SOFT_FAIL warning(s)) — E2E tests can run, some features may be limited."
  else
    log "  RESULT: READY — all checks passed."
  fi
  log ""
}

print_json() {
  local overall
  if [[ $HARD_FAIL -gt 0 ]]; then
    overall="blocked"
  elif [[ $SOFT_FAIL -gt 0 ]]; then
    overall="ready_with_warnings"
  else
    overall="ready"
  fi

  echo "{"
  echo "  \"overall\": \"$overall\","
  echo "  \"project_root\": \"$PROJECT_ROOT\","
  echo "  \"hard_failures\": $HARD_FAIL,"
  echo "  \"soft_failures\": $SOFT_FAIL,"
  echo "  \"checks\": ["

  local i last=$((${#CHECK_NAMES[@]} - 1))
  for i in "${!CHECK_NAMES[@]}"; do
    local comma=","
    [[ $i -eq $last ]] && comma=""
    # Escape double quotes in detail string
    local escaped_detail="${CHECK_DETAILS[$i]//\"/\\\"}"
    echo "    {\"name\": \"${CHECK_NAMES[$i]}\", \"level\": \"${CHECK_LEVELS[$i]}\", \"status\": \"${CHECK_STATUSES[$i]}\", \"detail\": \"$escaped_detail\"}$comma"
  done

  echo "  ]"
  echo "}"
}

# ── Main ──────────────────────────────────────────────────────────────────────

if $DRY_RUN; then
  log "DRY RUN — would check the following:"
  log ""
  log "  Hard dependencies:"
  log "    uv, python, pytest, zellij, ergo"
  log "    tests/e2e/ directory, zchat-channel-server/, zchat-protocol/"
  log "    IRC port availability"
  log ""
  log "  Soft dependencies:"
  log "    weechat, tmux, asciinema"
  log "    claude.local.env, uv sync status, conftest.py"
  exit 0
fi

run_checks
print_human
print_json
