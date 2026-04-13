---
type: test-plan
id: plan-ergo-languages-005
status: draft
producer: skill-2
created_at: "2026-04-13T00:00:00Z"
related:
  - eval-doc: eval-ergo-languages-004
  - issue: https://github.com/ezagent42/zchat/issues/41
---

# Test Plan: ergo languages 目录多路径查找（fix #41）

## 来源
- eval-doc: `eval-ergo-languages-004`
- 修复代码位置: `zchat/cli/irc_manager.py:60-66`（待 cherry-pick 自 `9e275fb`）

## 测试范围

修复后的 `_copy_languages_if_needed`（或等效逻辑）需覆盖以下候选路径：

1. `~/.local/share/ergo/languages`（手动安装）
2. `$(brew --prefix ergo)/share/languages`（Homebrew，主路径）
3. `$(brew --prefix ergo)/languages`（Homebrew，备选）
4. `$(dirname ergo_binary)/../share/ergo/languages`（binary 相对路径）
5. `$(dirname ergo_binary)/languages`（binary 同级）

## Test Cases

| TC-ID | 场景 | 测试类型 | 优先级 | 前置条件 | 操作 | 断言 |
|-------|------|---------|-------|---------|------|------|
| TC-01 | `~/.local/share/ergo/languages` 存在时正确 copy | unit | P0 | mock fs：只有 `~/.local/share/ergo/languages` 存在 | 调用 languages copy 逻辑 | `ergo_data_dir/languages` 被创建，`shutil.copytree` 以正确路径调用 |
| TC-02 | Homebrew prefix 路径存在时正确 copy | unit | P0 | mock `brew --prefix ergo` 返回 `/opt/homebrew/opt/ergo`；只有 `/opt/homebrew/opt/ergo/share/languages` 存在 | 调用 languages copy 逻辑 | `shutil.copytree` 以 brew share 路径调用 |
| TC-03 | Homebrew 备选路径存在时正确 copy | unit | P1 | mock brew prefix；只有 `/opt/homebrew/opt/ergo/languages` 存在 | 调用 languages copy 逻辑 | `shutil.copytree` 以 brew 备选路径调用 |
| TC-04 | binary 旁路径存在时正确 copy | unit | P1 | mock `shutil.which("ergo")` 返回路径；只有 binary 相对 share 路径存在 | 调用 languages copy 逻辑 | `shutil.copytree` 以 binary 相对路径调用 |
| TC-05 | `ergo_data_dir/languages` 已存在时不重复 copy | unit | P0 | `ergo_data_dir/languages` 已存在 | 调用 languages copy 逻辑 | `shutil.copytree` 不被调用 |
| TC-06 | 所有候选路径均不存在时不报错 | unit | P1 | 所有路径均不存在；`brew` 命令不存在（FileNotFoundError） | 调用 languages copy 逻辑 | 不抛出异常，静默跳过 |
| TC-07 | `brew --prefix` 超时时降级处理 | unit | P1 | mock `subprocess.run` 抛出 `TimeoutExpired` | 调用 languages copy 逻辑 | 不抛出异常，继续检查其他路径 |
| TC-08 | 第一个有效路径命中后不继续查找 | unit | P1 | 多个路径同时存在 | 调用 languages copy 逻辑 | `shutil.copytree` 只调用一次（第一个命中路径） |

## 测试文件位置

- 新建：`tests/unit/test_irc_manager_languages.py`
- 复用 fixture：`tests/unit/` 中已有的 mock 模式

## 覆盖说明

- 全部为 unit 测试，不依赖真实 ergo 安装或 Homebrew
- 通过 `unittest.mock.patch` mock `subprocess.run`、`shutil.which`、`os.path.isdir`、`shutil.copytree`
- 不需要 E2E 环境
