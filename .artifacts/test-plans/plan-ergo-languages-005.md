---
type: test-plan
id: plan-ergo-languages-005
status: executed
producer: skill-2
created_at: "2026-04-13T00:00:00Z"
updated_at: "2026-04-14T00:00:00Z"
related:
  - eval-doc: eval-ergo-languages-004
  - code-diff: code-diff-004
  - test-diff: test-diff-003
  - issue: https://github.com/ezagent42/zchat/issues/41
---

# Test Plan: ergo languages 目录多路径查找（fix #41）

## 来源
- eval-doc: `eval-ergo-languages-004`
- code-diff: `code-diff-004`（commits `f57eb46`、`b30ebd5`）
- 修复代码位置: `zchat/cli/irc_manager.py`（daemon_start 的 languages copy 逻辑）

## 测试范围

修复后的 languages copy 逻辑需覆盖以下候选路径（按优先级）：

1. `~/.local/share/ergo/languages`（手动安装）
2. `$(brew --prefix ergo)/share/languages`（Homebrew 主路径）
3. `$(brew --prefix ergo)/languages`（Homebrew 备选）
4. `$(dirname ergo_binary)/../share/ergo/languages`（binary 相对 share）
5. `$(dirname ergo_binary)/languages`（binary 同级）

## Test Cases

| TC-ID | 场景 | 测试类型 | 优先级 | 前置条件 | 操作 | 断言 |
|-------|------|---------|-------|---------|------|------|
| TC-01 | `~/.local/share/ergo/languages` 存在时正确 copy | unit | P0 | mock fs：只有 local_share 路径存在 | 调用 languages copy 逻辑 | `copytree` 以 local_share 路径调用 |
| TC-02 | Homebrew share 路径存在时正确 copy | unit | P0 | mock brew prefix；只有 brew share 路径存在 | 调用 languages copy 逻辑 | `copytree` 以 brew share 路径调用 |
| TC-03 | Homebrew 备选路径存在时正确 copy | unit | P1 | mock brew prefix；只有 brew alt 路径存在 | 调用 languages copy 逻辑 | `copytree` 以 brew alt 路径调用 |
| TC-04 | binary 旁路径存在时正确 copy | unit | P1 | mock `shutil.which("ergo")`；只有 binary 相对 share 路径存在 | 调用 languages copy 逻辑 | `copytree` 以 binary 相对路径调用 |
| TC-05 | `ergo_data_dir/languages` 已存在时不重复 copy | unit | P0 | dest 已存在 | 调用 languages copy 逻辑 | `copytree` 不被调用 |
| TC-06 | 所有候选路径均不存在时不报错 | unit | P1 | 所有路径均不存在，brew 不可用 | 调用 languages copy 逻辑 | 不抛出异常，静默跳过 |
| TC-07 | `brew --prefix` 超时时降级处理 | unit | P1 | mock `subprocess.run` 抛出 TimeoutExpired | 调用 languages copy 逻辑 | 不抛出异常，继续检查其他路径 |
| TC-08 | 第一个有效路径命中后不继续查找 | unit | P1 | 多个路径同时存在 | 调用 languages copy 逻辑 | `copytree` 只调用一次 |

## 验证结果

所有 8 个单元测试通过（2026-04-14），见 `tests/unit/test_irc_manager_languages.py`。

| TC-ID | 状态 | 备注 |
|-------|------|------|
| TC-01 | PASS | |
| TC-02 | PASS | |
| TC-03 | PASS | 2026-04-14 补充实现 |
| TC-04 | PASS | 2026-04-14 补充实现 |
| TC-05 | PASS | |
| TC-06 | PASS | |
| TC-07 | PASS | |
| TC-08 | PASS | |
