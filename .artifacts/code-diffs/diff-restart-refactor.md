---
type: code-diff
id: code-diff-restart-001
status: draft
producer: phase-2
created_at: "2026-04-10"
---
# Code Diff: Agent restart 重构
## 变更文件
- M zchat/cli/agent_manager.py (restart 函数重构)
## 影响模块
- agent_manager
## 改动类型
- 修改：restart 现在先 graceful stop 再 create
