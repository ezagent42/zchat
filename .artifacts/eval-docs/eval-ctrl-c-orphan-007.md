---
type: eval-doc
id: eval-doc-007
status: confirmed
producer: skill-5
created_at: "2026-04-13T00:00:00Z"
mode: verify
feature: agent-create-ctrl-c-cleanup
submitter: zyli
related: []
---

# Eval: Ctrl+C 中断 agent create 导致 Claude Code 孤儿进程 + IRC nick 冲突

## 基本信息
- 模式：验证
- 提交人：zyli
- 日期：2026-04-13
- 状态：confirmed

## 问题描述

在执行 `zchat agent create agent0` 过程中，`_wait_for_ready()` 轮询 `.ready` 文件期间若用户按 Ctrl+C，
`KeyboardInterrupt` 会终止主进程，但 zellij tab 内的 Claude Code 进程继续初始化并连接 IRC。
下次再执行 `zchat agent create agent0` 时，因状态检查只拦截 `status == "running"`（不拦截 "starting"），
会新建第二个 Claude Code 进程，两者争用同一 IRC nick，导致连接异常。

## 根因链路

```
zchat agent create agent0
  └─ _spawn_tab()            → 创建 zellij tab，启动 claude 进程        [agent_manager.py:179]
  └─ _save_state()           → 写入 status="starting"                   [agent_manager.py:90]
  └─ _auto_confirm_startup() → 守护线程启动，监听确认提示                [agent_manager.py:276]
  └─ _wait_for_ready()       → 轮询 .ready 文件（最长 60 秒）            [agent_manager.py:264]
       ↑
       用户按 Ctrl+C → KeyboardInterrupt 抛出
       → create() 无 try/finally → _save_state() 未更新状态             [agent_manager.py:92-97]
       → 守护线程随主进程死亡
       → Claude Code 孤儿进程继续在 zellij tab 内初始化并连上 IRC

下次 create():
  → 检查 status == "running" → False（卡在 "starting"）→ 继续创建      [agent_manager.py:73]
  → 新 Claude Code 启动，尝试以同一 nick 连接 IRC → nick 冲突
```

## Testcase 表格

| # | 场景 | 前置条件 | 操作步骤 | 预期效果 | 实际效果 | 差异描述 | 优先级 |
|---|------|---------|---------|---------|---------|---------|--------|
| 1 | Ctrl+C 中断后 zellij tab 应被清理 | ergo 运行，无同名 agent 存在，agent0 tab 正在初始化 | `zchat agent create agent0` → 等待 `_wait_for_ready` 轮询时按 Ctrl+C | zellij tab 被关闭，Claude Code 进程终止，状态写为 offline | zellij tab 继续存在，Claude Code 继续初始化并连上 IRC，状态卡在 "starting" | `create()` 缺少 KeyboardInterrupt 的 try/finally 清理，`_force_stop()` 未被调用 | P0 |
| 2 | 孤儿进程存在时二次 create 导致 nick 冲突 | TC-1 已执行，孤儿 Claude Code 已以 nick `{user}-agent0` 连上 IRC | 再次执行 `zchat agent create agent0` | 报错提示 "agent 已在运行或处于 starting 状态"，拒绝创建；或先清理旧进程再创建 | 新建第二个 tab，第二个 Claude Code 尝试以同一 nick 连接 IRC，IRC server 拒绝或踢出其中一个 | `agent_manager.py:73` 只拦截 `status == "running"`，不拦截 "starting" | P0 |
| 3 | 状态残留 "starting" 不被拦截 | state 文件中 agent0 的 status = "starting" | `zchat agent create agent0` | 被拦截：提示 "agent exists in starting/unclean state，请先 stop 再 create" | 正常创建（检查通过），导致重复进程 | 守卫条件 `agent_manager.py:73` 范围不足 | P0 |
| 4 | 两个 _auto_confirm_startup 线程竞争发 Enter | 孤儿进程在 tab 内等待确认，新 create 再次启动 | 第二次 `zchat agent create agent0` | 只有一个确认线程活跃 | 两个守护线程同时 dump_screen 并发送 Enter，造成确认指令重复发送 | 线程没有互斥机制，也没有检查 tab 是否已存在 | P1 |
| 5 | Ctrl+C 后状态文件残留 "starting" | 首次 create 被 Ctrl+C 中断 | `cat ~/.local/state/zchat/agents.json` | status 为 offline 或 entry 被删除 | status = "starting"（第一次 `_save_state()` 已写入，后续更新未执行） | `_wait_for_ready()` 返回后的 `_save_state()` 调用 [agent_manager.py:97] 从未到达 | P1 |

## 证据区

### 截图/录屏
{待补充}

### 日志/错误信息

代码证据（静态分析，无需运行）：

```python
# agent_manager.py:65-98
def create(self, name, workspace=None, channels=None, agent_type=None):
    ...
    tab_name = self._spawn_tab(name, agent_workspace, agent_type, channels)

    self._agents[name] = {
        ...
        "status": "starting",   # ← 已持久化
    }
    self._save_state()           # ← 写入 "starting"

    # _auto_confirm_startup 守护线程已启动（在 _spawn_tab 内）

    # ↓ 若此处 KeyboardInterrupt：_force_stop() 不会被调用，状态不会更新
    if self._wait_for_ready(name, timeout=60):
        self._agents[name]["status"] = "running"
    else:
        self._agents[name]["status"] = "error"
    self._save_state()           # ← 永远不会执行
    return self._agents[name]


# agent_manager.py:73 - 守卫条件缺口
if name in self._agents and self._agents[name].get("status") == "running":
    raise ValueError(f"{name} already exists and is running")
# "starting" 状态不在此守卫范围内 → 允许重复创建
```

### 复现环境

- 操作系统：Linux (WSL2)
- 软件版本：zchat（当前 main 分支），ergo IRC server
- 配置：标准本地项目配置，`~/.zchat/projects/local/config.toml`
- 复现性：**必现**（只要在 `_wait_for_ready` 轮询窗口内按 Ctrl+C）

## 分流建议

**建议分类**：疑似 bug

**判断理由**：

1. **行为明确违反用户预期**：用户按 Ctrl+C 的意图是"取消操作"，系统应回到按 Ctrl+C 前的干净状态。当前实现留下了孤儿进程，与取消语义矛盾。

2. **有确定的代码路径**：`create()` 方法在 `_wait_for_ready()` 前后之间没有任何异常处理，`KeyboardInterrupt` 的传播路径清晰且必现。

3. **影响后续操作**：孤儿进程不仅占用 IRC nick，还导致状态文件持续不一致（"starting"），使后续 create/stop/list 行为不可预期。这已超出"体验差"范畴，属于功能性错误。

4. **修复范围明确**：核心修复是在 `create()` 中增加 `try/finally`（约 5 行），并将 line:73 的守卫条件扩展到同时拦截 "starting" 状态（1 行）。没有架构层面的歧义。

## 后续行动

- [x] eval-doc 已注册到 registry.json（eval-doc-007）
- [x] 用户已确认 testcase 表格（status: confirmed）
- [x] 修复代码已合并（commit `689c385`）
- [x] code-diff 已注册（code-diff-006）
- [x] test-plan 已生成（plan-ctrl-c-cleanup-008，Skill 2）
- [x] 测试代码已编写（test_agent_manager.py +6 tests，Skill 3）
- [x] 红灯报告已记录（e2e-report-001，4 FAIL 符合预期）
- [x] test-diff 已注册（test-diff-005）
- [x] 绿灯报告已生成（e2e-report-005，19/19 PASS，Skill 4）
