---
type: e2e-report
id: e2e-report-003
status: green
producer: skill-4
created_at: "2026-04-14T00:00:00Z"
related:
  - test-plan: plan-ergo-languages-005
  - test-diff: test-diff-003
  - eval-doc: eval-ergo-languages-004
---

# Test Report: ergo languages 多路径查找验证（fix #41）

## 汇总

| 类型 | 总数 | PASS | FAIL | SKIP |
|------|------|------|------|------|
| 单元测试（自动化） | 8 | 8 | 0 | 0 |

**结论：绿灯 ✅**

## 自动化测试结果

```
uv run --no-sync pytest tests/unit/test_irc_manager_languages.py -v
platform linux -- Python 3.13.12, pytest-9.0.2

tests/unit/test_irc_manager_languages.py::TestTC01LocalShareExists::test_copies_from_local_share PASSED
tests/unit/test_irc_manager_languages.py::TestTC02BrewShareExists::test_copies_from_brew_share PASSED
tests/unit/test_irc_manager_languages.py::TestTC03BrewAltExists::test_copies_from_brew_alt PASSED
tests/unit/test_irc_manager_languages.py::TestTC04BinaryRelativeExists::test_copies_from_binary_relative PASSED
tests/unit/test_irc_manager_languages.py::TestTC05DestAlreadyExists::test_no_copy_when_dest_exists PASSED
tests/unit/test_irc_manager_languages.py::TestTC06NoCandidateExists::test_no_exception_when_no_candidate PASSED
tests/unit/test_irc_manager_languages.py::TestTC07BrewTimeout::test_no_exception_on_brew_timeout PASSED
tests/unit/test_irc_manager_languages.py::TestTC08FirstMatchOnly::test_only_first_match_is_used PASSED

8 passed in 0.05s
```

验证时间：2026-04-14
运行环境：WSL2 (Linux 6.6.87.2-microsoft-standard-WSL2), Python 3.13.12

## 新增 vs 回归

- **新增测试（2026-04-14）**：TC-03（Homebrew 备选路径）、TC-04（binary 旁路径）—— 2 个
- **原有测试**：TC-01、TC-02、TC-05、TC-06、TC-07、TC-08 —— 6 个，全部继续 PASS
- **回归**：无

## Issue 状态

GitHub issue #41 可关闭。修复完整，8/8 测试覆盖所有候选路径场景。
