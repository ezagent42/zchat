---
type: test-diff
id: test-diff-003
status: merged
producer: skill-3
created_at: "2026-04-13T15:00:00Z"
updated_at: "2026-04-14T00:00:00Z"
related:
  - test-plan: plan-ergo-languages-005
  - eval-doc: eval-ergo-languages-004
---

# Test Diff: ergo languages 多路径查找单元测试（fix #41）

## 来源
- test-plan: `plan-ergo-languages-005`（TC-01 ~ TC-08）
- 文件: `tests/unit/test_irc_manager_languages.py`

## 测试策略

将 `irc_manager.py` 的 languages copy 逻辑提取为可独立测试的函数 `_run_languages_copy()`，
通过 `unittest.mock.patch` mock `subprocess.run`、`shutil.which`、`os.path.isdir`、`shutil.copytree`，
不依赖真实 ergo 安装或 Homebrew 环境。

## 新增/修改测试

### 文件：`tests/unit/test_irc_manager_languages.py`

| 测试类 | 测试方法 | 覆盖 TC | 状态 |
|-------|---------|---------|------|
| TestTC01LocalShareExists | test_copies_from_local_share | TC-01 | 原有 |
| TestTC02BrewShareExists | test_copies_from_brew_share | TC-02 | 原有 |
| TestTC03BrewAltExists | test_copies_from_brew_alt | TC-03 | 2026-04-14 新增 |
| TestTC04BinaryRelativeExists | test_copies_from_binary_relative | TC-04 | 2026-04-14 新增 |
| TestTC05DestAlreadyExists | test_no_copy_when_dest_exists | TC-05 | 原有 |
| TestTC06NoCandidateExists | test_no_exception_when_no_candidate | TC-06 | 原有 |
| TestTC07BrewTimeout | test_no_exception_on_brew_timeout | TC-07 | 原有 |
| TestTC08FirstMatchOnly | test_only_first_match_is_used | TC-08 | 原有 |

## 运行结果

```
uv run --no-sync pytest tests/unit/test_irc_manager_languages.py -v
8 passed in 0.05s
```

验证时间：2026-04-14，Python 3.13.12
