---
type: eval-doc
id: eval-ergo-languages-004
status: confirmed
producer: skill-5
created_at: "2026-04-13T00:00:00Z"
mode: verify
feature: ergo languages 目录多路径查找
submitter: zyli
related:
  - issue: https://github.com/ezagent42/zchat/issues/41
---

# Eval: ergo Homebrew 安装后 languages 目录缺失导致启动失败

## 基本信息
- 模式：验证
- 提交人：zyli
- 日期：2026-04-13
- 状态：confirmed（已确认为 bug，fix 已合并）

## Testcase 表格

| # | 场景 | 前置条件 | 操作步骤 | 预期效果 | 实际效果 | 差异描述 | 优先级 |
|---|------|---------|---------|---------|---------|---------|--------|
| 1 | Homebrew 安装 ergo，执行 `zchat irc daemon start` | WSL2/macOS；ergo 通过 `brew install ergochat/tap/ergo` 安装；`~/.local/share/ergo/languages` 不存在 | `zchat irc daemon start` | ergo 从 brew prefix 找到 languages 目录并正常启动 | `Could not load languages: open languages: no such file or directory`，启动失败 | 当前代码只查找 `~/.local/share/ergo/languages`，Homebrew 安装的 languages 在 `$(brew --prefix ergo)/share/languages`，路径不匹配 | P0 |
| 2 | 手动安装 ergo，languages 在 `~/.local/share/ergo/` | Linux 环境；ergo 从 GitHub releases 手动安装 | `zchat irc daemon start` | 从 `~/.local/share/ergo/languages` 找到并正常启动 | 正常（此路径是原有代码唯一支持的路径）；fix 后此路径仍作为第一优先级保留 | 无差异 | P1 |
| 3 | Homebrew 备选路径（`brew_prefix/languages`）存在时正确 copy | brew prefix/share/languages 不存在，但 brew prefix/languages 存在 | `zchat irc daemon start` | 从备选路径找到并正常启动 | fix 后新增此候选路径 | 已通过单元测试 TC-03 验证 | P1 |
| 4 | binary 旁路径（`$(dirname ergo)/../share/ergo/languages`）存在时正确 copy | 任意安装方式；binary 相对路径存在 languages | `zchat irc daemon start` | 从 binary 旁找到并正常启动 | fix 后新增此候选路径 | 已通过单元测试 TC-04 验证 | P1 |

## 证据区

### 日志/错误信息（修复前）

```
Could not load languages: open languages: no such file or directory
```

### 复现环境

- 操作系统：WSL2 Ubuntu / macOS
- ergo 版本：2.18.0（Homebrew 安装）
- 安装方式：`brew install ergochat/tap/ergo`

### 根本原因（代码层）

`zchat/cli/irc_manager.py`（修复前）：

```python
system_ergo = os.path.expanduser("~/.local/share/ergo")
if os.path.isdir(os.path.join(system_ergo, "languages")) and \
   not os.path.isdir(os.path.join(ergo_data_dir, "languages")):
    shutil.copytree(...)
```

只查找一个固定路径，不覆盖 Homebrew 安装场景。

## 分流结论

**分类**：确认 bug

**判断理由**：
- 按文档 `brew install ergochat/tap/ergo` 安装后 `zchat irc daemon start` 直接失败，违反用户预期
- Homebrew 安装路径结构与硬编码路径完全不匹配，可稳定复现
- macOS 用户几乎全部使用 Homebrew，影响范围广（P0）

## 后续行动

- [x] eval-doc 已注册到 registry.json（eval-doc-005）
- [x] 确认为 bug（status: confirmed）
- [x] 修复代码已合并（commits `f57eb46`、`b30ebd5`）
- [x] code-diff 已注册（code-diff-004）
- [x] test-plan 已生成（plan-ergo-languages-005，Skill 2）
- [x] 测试代码已编写（test_irc_manager_languages.py，8/8 pass，Skill 3）
- [x] test-diff 已注册（test-diff-003）
- [x] 测试报告已生成（e2e-report-003，8/8 green，Skill 4）
- [x] GitHub issue #41 关联此 eval-doc
