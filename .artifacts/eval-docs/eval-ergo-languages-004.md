---
type: eval-doc
id: eval-ergo-languages-004
status: draft
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
- 状态：draft

## Testcase 表格

| # | 场景 | 前置条件 | 操作步骤 | 预期效果 | 实际效果 | 差异描述 | 优先级 |
|---|------|---------|---------|---------|---------|---------|--------|
| 1 | Homebrew 安装 ergo，执行 `zchat irc daemon start` | WSL2/macOS；ergo 通过 `brew install ergochat/tap/ergo` 安装；`~/.local/share/ergo/languages` 不存在 | `zchat irc daemon start` | ergo 从 brew prefix 找到 languages 目录并正常启动 | `Could not load languages: open languages: no such file or directory`，启动失败 | 当前代码只查找 `~/.local/share/ergo/languages`，Homebrew 安装的 languages 在 `$(brew --prefix ergo)/share/languages`，路径不匹配 | P0 |
| 2 | 手动安装 ergo（非 Homebrew），languages 在 `~/.local/share/ergo/` | Linux 环境；ergo 从 GitHub releases 手动安装 | `zchat irc daemon start` | 从 `~/.local/share/ergo/languages` 找到并正常启动 | 正常（此路径是现有代码唯一支持的路径） | 无差异，但 fix 后此路径仍作为第一优先级保留 | P1 |
| 3 | ergo binary 旁边存在 languages 目录 | 任意安装方式；`$(dirname $(which ergo))/../share/ergo/languages` 存在 | `zchat irc daemon start` | 从 binary 旁找到 languages 并正常启动 | 当前代码不支持此路径 | fix 后新增此候选路径 | P1 |
| 4 | 所有候选路径均不存在 | ergo 安装但 languages 目录完全缺失 | `zchat irc daemon start` | 给出明确错误提示，告知用户 languages 目录位置 | 当前：ergo 启动后自身报错，信息不友好 | fix 后行为待确认（不 copy 时是否有 warning） | P2 |

## 证据区

### 日志/错误信息

```
Could not load languages: open languages: no such file or directory
```

### 复现环境

- 操作系统：WSL2 Ubuntu / macOS
- ergo 版本：2.18.0（Homebrew 安装）
- 安装方式：`brew install ergochat/tap/ergo`
- zchat 版本：当前 feat/clear-branch

### 根本原因（代码层）

`zchat/cli/irc_manager.py:60-66`：

```python
system_ergo = os.path.expanduser("~/.local/share/ergo")
if os.path.isdir(os.path.join(system_ergo, "languages")) and \
   not os.path.isdir(os.path.join(ergo_data_dir, "languages")):
    shutil.copytree(...)
```

只查找一个固定路径，不覆盖 Homebrew 安装场景。

## 分流建议

**建议分类**：疑似 bug

**判断理由**：
- 行为明确违反用户预期：按文档安装 ergo 后，`zchat irc daemon start` 应正常工作
- 问题可稳定复现（Homebrew 安装路径与硬编码路径不匹配）
- 修复方案明确：`9e275fb` 中已实现多路径查找逻辑，经过验证可用
- 影响范围广：macOS 用户几乎全部使用 Homebrew 安装 ergo

## 后续行动

- [ ] eval-doc 已注册到 .artifacts/eval-docs/
- [ ] 用户已确认 testcase 表格 (status: draft → confirmed)
- [ ] Skill 2：生成 test-plan
- [ ] Skill 3：写测试代码
- [ ] Phase 6：cherry-pick `zchat/cli/irc_manager.py`（来自 `9e275fb`）
- [ ] Skill 4：运行测试验证
- [ ] GitHub issue #41 关联此 eval-doc
