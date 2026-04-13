---
type: eval-doc
id: "eval-doc-002"
status: draft
producer: skill-5
created_at: "2026-04-10T12:00:00Z"
mode: "verify"
feature: "scoped_name 幂等性"
submitter: "yaosh"
related: []
---

# Eval: scoped_name 幂等性

## 基本信息
- 模式：验证
- 提交人：yaosh
- 日期：2026-04-10
- 状态：draft

## 问题概述

`zchat_protocol.naming.scoped_name()` 对已包含 scope 前缀的名字无条件再次拼接 username，导致双重前缀。例如 `scoped_name("alice-helper", "alice")` 返回 `"alice-alice-helper"` 而非预期的 `"alice-helper"`。

## 根因分析

**文件**：`zchat-protocol/zchat_protocol/naming.py:6-11`

当前实现：
```python
def scoped_name(name: str, username: str) -> str:
    return f"{username}{AGENT_SEPARATOR}{name}"
```

函数无条件拼接 `{username}-{name}`，缺少对 name 是否已 scoped 的检查。docstring 甚至将错误行为记录为"预期"。

**预期行为**（根据测试用例）：
- 如果 name 不含分隔符（裸名）→ 添加前缀：`scoped_name("helper", "alice")` → `"alice-helper"`
- 如果 name 已含分隔符（已 scoped）→ 原样返回：`scoped_name("alice-helper", "alice")` → `"alice-helper"`
- 如果 name 包含其他用户前缀 → 原样返回：`scoped_name("bob-helper", "alice")` → `"bob-helper"`

## Testcase 表格

| # | 场景 | 前置条件 | 操作步骤 | 预期效果 | 实际效果 | 差异描述 | 优先级 |
|---|------|---------|---------|---------|---------|---------|--------|
| 1 | 裸名添加前缀 | 无 | `scoped_name("helper", "alice")` | `"alice-helper"` | `"alice-helper"` | 无 | P0 |
| 2 | 已有自身前缀（幂等） | name 已包含 username 前缀 | `scoped_name("alice-helper", "alice")` | `"alice-helper"` | `"alice-alice-helper"` | 双重前缀，name 已 scoped 但被再次拼接 | P0 |
| 3 | 已有其他用户前缀 | name 包含不同用户的前缀 | `scoped_name("bob-helper", "alice")` | `"bob-helper"` | `"alice-bob-helper"` | 覆盖了 bob 的 scope，错误地添加 alice 前缀 | P0 |
| 4 | 分隔符检查 | 无 | `AGENT_SEPARATOR == "-"` | `"-"` | `"-"` | 无 | P0 |

## 影响范围

`scoped_name` 通过 `AgentManager.scoped()` 被以下 CLI 命令调用：
- `zchat agent create` — `agent_manager.py:72`
- `zchat agent stop` — `agent_manager.py:102`
- `zchat agent restart` — `agent_manager.py:115`
- `zchat agent status` — `agent_manager.py:133`
- `zchat agent send` — `agent_manager.py:334`
- 以及 `app.py` 中 6 处 `mgr.scoped(name)` 调用

**实际影响**：当用户传入已包含 scope 的全名（如 `alice-helper`）时，所有 CLI 命令都会产生双重前缀的 IRC nick，导致找不到对应 agent 或创建错误命名的 agent。

## 证据区

### 日志/错误信息

pytest 输出（2/4 测试失败）：

```
FAILED tests/test_naming.py::test_scoped_name_no_double_prefix
  assert scoped_name("alice-helper", "alice") == "alice-helper"
  AssertionError: assert 'alice-alice-helper' == 'alice-helper'

FAILED tests/test_naming.py::test_scoped_name_different_prefix
  assert scoped_name("bob-helper", "alice") == "bob-helper"
  AssertionError: assert 'alice-bob-helper' == 'bob-helper'
```

### 复现环境

- 操作系统：Linux 6.6.87.2-microsoft-standard-WSL2
- Python：3.13.5
- pytest：9.0.2
- zchat-protocol：当前 main 分支

## 分流建议

**建议分类**：疑似 bug

**判断理由**：

1. **测试明确期望幂等行为**：`test_scoped_name_no_double_prefix` 和 `test_scoped_name_different_prefix` 两个测试用例清楚定义了预期——已 scoped 的名字不应再次添加前缀
2. **实现与测试矛盾**：实现无条件拼接，测试要求条件判断，说明实现尚未完成或存在回归
3. **稳定复现**：`uv run pytest tests/test_naming.py -v` 100% 复现，2/4 失败
4. **影响核心功能**：agent 命名是 zchat 协议的基础，错误命名导致 agent 无法正确定位

## 后续行动

- [x] eval-doc 已注册到 .artifacts/eval-docs/
- [ ] 用户已确认 testcase 表格 (status: draft -> confirmed)
- [ ] GitHub issue 已创建（用户明确要求不创建）
