# 04-用户旅程与交互原型

> 每个skill在实际使用中的交互流程。目标：用户看到这份文档就知道每个skill用起来是什么体验。

## 角色定义

| 角色 | 说明 | 主要使用的skill |
|------|------|----------------|
| **开发者（你）** | 项目owner，接入新项目、开发新功能、管理pipeline | Skill 0, 1, 2, 3, 4 |
| **产品经理** | 提出新需求、验证功能效果 | Skill 5（模拟模式） |
| **测试人员/用户** | 使用产品、发现问题、提交反馈 | Skill 5（验证模式） |
| **新人/协作者** | 刚接触项目，需要了解代码 | Skill 1 |

---

## 旅程1：接入新项目（开发者 × Skill 0）

### 场景
你接手了zchat项目，代码已经写了60%+，有一些pytest测试但没有操作E2E。

### 交互流程

```
开发者: 我需要接入一个新项目，建立开发闭环。项目在 ~/workspace/zchat

Claude (Skill 0): 收到。我会开始完整的bootstrap流程。

Step 1/8: 扫描项目结构...
→ 发现语言: Python
→ 发现框架: pytest, asyncio
→ 发现测试目录: tests/unit (18文件), tests/e2e (2文件), tests/pre_release (8模块)
→ 发现测试工具: IrcProbe, Zellij helpers

Step 2/8: 通读源代码...
→ 扫描 src/ 下 47 个文件
→ 识别 9 个核心模块: auth, agent, irc, project, layout, template, migrate, update, config

Step 3/8: 按模块运行已有测试...
→ unit tests: 100/100 passed (2.1s)
→ e2e tests: 11/13 passed, 2 skipped (需要ergo) (4.2s)
→ pre_release: 跳过 (需要完整环境)

Step 4/8: 生成覆盖矩阵...
→ 代码测试覆盖: 9/9 模块有单元测试
→ 操作E2E覆盖: 2/15 用户流程有E2E (WeeChat连接、Agent消息)
→ E2E缺口: 13个用户流程无操作E2E (私聊DM、系统消息、start.sh、配置迁移...)

Step 5/8: 生成Skill 1...
→ 创建 project-discussion/SKILL.md
→ 创建 9 个模块测试脚本
→ 创建索引 index.md

Step 6/8: 初始化artifact空间...
→ 创建 .artifacts/registry.json
→ 注册 coverage-matrix (13个E2E缺口)

Step 7/8: 安装Skill 1到Claude Code...
→ Done

Step 8/8: Bootstrap完成。

总结：
- Skill 1 已就绪，可以开始问答
- 覆盖矩阵显示 13 个用户流程缺少操作E2E
- 建议下一步: 运行 Skill 2 生成第一批E2E测试计划

开发者: 好的，先看看Skill 1能不能回答问题。zchat的agent创建流程是什么？

Claude (Skill 1): agent创建流程涉及3个模块：
- AgentManager (src/agent_manager.py): 负责 scoped_name 生成、workspace 创建、.ready 检测
- IrcManager (src/irc_manager.py): 负责 IRC 连接
- Layout (src/layout.py): 负责 Zellij tab 创建

运行验证：
$ bash test-runners/test-agent-lifecycle.sh
→ test_agent_create: PASSED
→ test_agent_scoped_name: PASSED
→ test_agent_workspace: PASSED
→ 3/3 passed

具体流程：
1. 用户执行 `zchat agent create <name>`
2. AgentManager.create() 生成 scoped_name
3. 创建 workspace 目录
4. IrcManager 连接到 IRC server
5. Layout 在 Zellij 中创建 agent tab
6. 等待 .ready 文件出现，标记 agent 在线
```

---

## 旅程2：产品提新需求（产品经理 × Skill 5 模拟模式）

### 场景
产品经理想给zchat加一个"agent间私聊"功能。

### 交互流程

```
产品经理: 我想给zchat加一个agent间私聊功能。agent A可以直接给agent B发私信，
         不经过公共频道。

Claude (Skill 5, simulate): 好，我来帮你整理这个需求并模拟效果。

请确认以下testcase是否覆盖你的预期：

## Eval Document: agent间私聊

| # | 场景 | 前置条件 | 操作步骤 | 预期效果 |
|---|------|---------|---------|---------|
| 1 | 基本私聊 | agent_a和agent_b都在线 | agent_a发送DM给agent_b | agent_b收到消息，公共频道不可见 |
| 2 | 离线私聊 | agent_b离线 | agent_a发送DM给agent_b | 消息排队，agent_b上线后收到 |
| 3 | 不存在的agent | agent_c不存在 | agent_a发送DM给agent_c | 返回错误提示 |
| 4 | 私聊历史 | 之前有过私聊 | 查看私聊历史 | 显示时间排序的消息列表 |

需要调整吗？

产品经理: 第2个场景不需要，先不做离线排队。加一个场景：私聊时对方能收到通知。

Claude (Skill 5): 更新后的eval文档：

[更新后的表格，去掉场景2，加上通知场景]

现在我模拟实现效果：

| # | 场景 | 预期效果 | 模拟实际效果 |
|---|------|---------|-------------|
| 1 | 基本私聊 | agent_b收到消息，公共频道不可见 | ✅ agent_b的IRC session收到PRIVMSG，#general无此消息 |
| 2 | 不存在的agent | 返回错误提示 | ✅ 返回 "agent_c is not online or does not exist" |
| 3 | 私聊历史 | 显示时间排序的消息列表 | ⚠️ 当前架构channel-server不持久化DM，需要新增存储 |
| 4 | 私聊通知 | 对方收到通知 | ✅ 通过IRC NOTICE发送通知 |

发现1个实现风险: 场景3需要新增存储层，当前channel-server无DM持久化。

确认后我会生成eval-doc并注册到artifact空间。

产品经理: 场景3先降优先级，其他确认。

Claude (Skill 5): 
→ 生成 eval-doc: .artifacts/eval-docs/eval-agent-dm-001.md
→ 注册到registry (status: draft, type: eval-doc)
→ 文档已准备好交给研发。
```

---

## 旅程3：开发+测试循环（开发者 × Skill 1/2/3/4）

### 场景
拿到上面的eval-doc，开始开发agent间私聊功能。

### 交互流程

```
--- Phase 2: 开发 ---

开发者: 根据 eval-agent-dm-001 开发agent间私聊功能。

Claude (Skill 1 context): 基于项目索引：
- DM逻辑需要改 channel-server 的消息路由
- IRC协议已有PRIVMSG支持，需要在 channel-server 中区分频道消息和DM
- 涉及模块: channel-server, agent_manager, irc_manager

[Claude开发代码...]

→ 生成 code-diff: .artifacts/code-diffs/diff-agent-dm-001.md
→ 注册到registry


--- Phase 3: 测试计划 ---

开发者: 生成测试计划。

Claude (Skill 2): 从registry读取:
- code-diff: diff-agent-dm-001 (改了channel-server消息路由 + agent_manager DM接口)
- coverage-matrix: 当前E2E覆盖中"私聊DM"标记为❌未覆盖
- eval-doc: eval-agent-dm-001 (4个testcase，场景3低优先级)

测试计划 summary:

| # | 场景 | 来源 | 优先级 | 说明 |
|---|------|------|--------|------|
| 1 | agent间基本DM | eval-doc #1 | P0 | 新功能核心路径 |
| 2 | DM给不存在的agent | eval-doc #2 | P1 | 错误处理 |
| 3 | DM通知 | eval-doc #4 | P1 | 通知机制 |
| 4 | DM不泄漏到公共频道 | code-diff分析 | P0 | 安全回归 |
| 5 | 已有@mention功能不受影响 | 回归 | P0 | 消息路由改动可能影响 |

请确认。

开发者: 确认。

Claude (Skill 2):
→ test-plan confirmed
→ 注册 .artifacts/test-plans/plan-agent-dm-001.md (status: confirmed)


--- Phase 4: 编写E2E ---

Claude (Skill 3): 从registry读取 plan-agent-dm-001。
从Skill 1获取项目E2E格式: pytest + IrcProbe + Zellij helpers。

追加到 tests/e2e/test_e2e.py:
- Phase 10: test_agent_dm_basic (IrcProbe发送PRIVMSG，验证接收)
- Phase 11: test_agent_dm_nonexistent (验证错误返回)
- Phase 12: test_agent_dm_notification (验证NOTICE)
- Phase 13: test_agent_dm_no_leak (验证#general无DM消息)

追加到 tests/e2e/conftest.py:
- dm_probe fixture (专门用于DM测试的IRC客户端)

→ 注册 .artifacts/test-diffs/diff-e2e-agent-dm-001.md
→ 4个新case已写入项目E2E套件


--- Phase 5: 执行E2E ---

Claude (Skill 4): 执行完整E2E套件...

新增case (4个):
  ✅ Phase 10: test_agent_dm_basic - PASSED
  ✅ Phase 11: test_agent_dm_nonexistent - PASSED
  ✅ Phase 12: test_agent_dm_notification - PASSED
  ✅ Phase 13: test_agent_dm_no_leak - PASSED

回归case (13个):
  ✅ Phase 1-9: 全部PASSED
  ✅ test_zellij_lifecycle: PASSED

→ 生成 .artifacts/e2e-reports/report-agent-dm-001.md
→ 更新 coverage-matrix: 私聊DM ❌→✅
→ 全部通过，可以部署。
```

---

## 旅程4：用户发现问题（测试人员 × Skill 5 验证模式）

### 场景
部署后，测试人员在使用私聊功能时发现：DM消息中如果包含@符号，会被错误识别为@mention。

### 交互流程

```
测试人员: 我在使用agent私聊时发现一个问题。

Claude (Skill 5, verify): 我来帮你记录。请按以下步骤描述：

1. 你做了什么操作？
测试人员: 让agent_a给agent_b发私信，内容是"请联系 @carol 确认"

2. 你期望看到什么？
测试人员: agent_b收到完整的消息文本

3. 实际发生了什么？
测试人员: agent_b没收到DM，反而carol收到了一条@mention消息

4. 有截图或日志吗？
测试人员: [粘贴了IRC日志截图]

Claude (Skill 5):

## Eval Document (验证模式)

| 场景 | 预期效果 | 实际效果 | 差异 |
|------|---------|---------|------|
| DM中包含@符号 | agent_b收到"请联系 @carol 确认" | @carol收到mention，agent_b未收到DM | DM中的@被错误路由为mention |

分流建议: **疑似bug** — DM的消息路由没有正确区分私信内容中的@符号和频道中的@mention。

→ 生成 .artifacts/eval-docs/eval-dm-mention-bug-001.md
→ 创建 GitHub issue: "DM中@符号被错误识别为@mention"
→ 添加 watcher: @开发者
→ 注册到registry

--- Phase 8: 和 Skill 1 讨论分流 ---

开发者: 这个DM中@符号的问题，帮我分析一下是不是bug？

Claude (Skill 1): 我来查代码和测试。

1. 查代码:
   channel-server/src/mention.py:15 的 detect_mention 函数
   对所有 PRIVMSG 统一做 @mention 检测，没有区分消息来源（频道 vs DM）
   → file:line 引用: mention.py:15-28

2. 跑测试验证:
   $ bash scripts/test-mention-detection.sh
   → 6 cases passed，但都是频道场景，没有DM场景的测试

3. 查已有知识:
   → 查询 .artifacts/ 中 archived eval-doc，无相关驳回记录
   → 这是首次报告此问题

结论: **确认是 bug**。detect_mention 应该检查消息来源类型，DM 消息不应触发 mention。

开发者: 同意，是bug。

Claude (Skill 1):
→ issue 保持 open
→ eval-doc (eval-dm-mention-bug-001) 进入 Phase 3
→ Skill 2 将生成 test-plan，包含 "DM中@不触发mention" 这个 case
→ 修复后这个 case 永久加入 E2E 套件
```

### 如果结论是"不是 bug"

```
开发者: 帮我看看这个问题是不是bug？[某个其他issue]

Claude (Skill 1): [查代码+跑测试+查已有知识后]
结论: 这不是 bug，是设计限制。原因是...

开发者: 同意，不是bug。

Claude (Skill 1):
→ 关闭 GitHub issue（附结论说明）
→ eval-doc 状态更新为 archived + rejection_reason
→ git commit 追踪变更
→ 下次有人问同类问题时，我会引用这条驳回记录
```

---

## 旅程5：新人接手项目（协作者 × Skill 1）

### 场景
一个新同事需要了解zchat项目，给他分发了Skill 1。

### 交互流程

```
新人: zchat的消息链路是怎么走的？从用户发消息到agent回复。

Claude (Skill 1): 消息链路涉及4个模块，完整路径：

1. WeeChat (IRC客户端) → 用户输入消息
2. ergo (IRC server) → 消息路由
3. channel-server → 检测@mention，分发给对应agent
4. Agent (Claude Code session) → 处理消息，生成回复
5. channel-server → 回复路由回IRC
6. WeeChat → 显示回复

运行验证:
$ bash test-runners/test-message-chain.sh
→ test_weechat_to_irc: PASSED
→ test_mention_detection: PASSED
→ test_agent_reply: PASSED
→ 3/3 passed

新人: channel-server是怎么检测@mention的？

Claude (Skill 1): channel-server/src/mention.py 中的 detect_mention 函数：
- 解析消息文本，匹配 `@agent_name` 模式
- 支持 scoped_name 格式: `@alice-agent0`
- 去除前缀后传递给agent

运行验证:
$ bash test-runners/test-mention-detection.sh
→ test_detect_mention: PASSED (6 cases)
→ test_clean_mention: PASSED (4 cases)

注意已知边界: DM中的@符号会被错误检测为mention（参见issue #XX，已有修复计划）。
```

---

## 交互原型：Skill间artifact流转

以下是一个完整循环中artifact的流转可视化。每个artifact在registry中都有唯一id和状态。

```
eval-agent-dm-001 (eval-doc, draft)
    ↓ 产品确认
eval-agent-dm-001 (eval-doc, confirmed)
    ↓ Skill 2 消费
plan-agent-dm-001 (test-plan, draft)
    ↓ 开发者确认
plan-agent-dm-001 (test-plan, confirmed)
    ↓ Skill 3 消费
diff-e2e-agent-dm-001 (test-diff, executed)
    ↓ Skill 4 消费
report-agent-dm-001 (e2e-report, executed)
    ↓ 全部通过，部署
    ↓ 用户发现bug
eval-dm-mention-bug-001 (eval-doc, confirmed)
  + issue-dm-mention-001 (issue, open)
    ↓ 确认是bug，回到Skill 2
plan-dm-mention-fix-001 (test-plan, confirmed)
    ↓ ... 循环继续
```

每个artifact的`related`字段记录了上下游关系，可以在registry中追溯完整链条。
