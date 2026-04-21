# V7 · Entry-as-Coordinator · 分层与 zchat 边界

> 2026-04-21 · 承接 V6 pre-release 调试观察：fast/deep 分发被 soul.md 硬编码，
> routing.toml `agents` 字段写死不维护。
>
> 本 note 定义 **zchat 的路由职责边界**。真正的多 agent 编排
> （role/scope/flow/commitment）**不在 zchat**，由独立库
> [Socialware](/home/yaosh/projects/Socialwares) 承担。

## 分层

```
+------------------------------------------+
| Socialware (独立库)                      |
|   role / scope / flow / commitment       |
|   多 agent 工作流编排、能力识别、链式调度 |
+------------------^-----------------------+
                   | 接入 agent soul.md
+------------------+-----------------------+
| zchat agent soul.md                      |
|   用 Socialware 定义 workflow            |
|   通过 zchat MCP tool 查 peer / 发 side  |
+------------------^-----------------------+
                   | MCP + IRC
+------------------+-----------------------+
| zchat 基础设施（本 note 作用域）         |
|   - router: @entry + 熔断                |
|   - MCP: list_peers(channel) 原语        |
|   - IRC: 消息传递 / presence              |
+------------------------------------------+
```

## zchat 的两项职责

### 1. Router 层 · 简单 + 熔断

- 正常路径：客户消息 → `@entry_agent <encoded>`（已有）
- 熔断路径：`@entry` 前 check `entry in channel.members`（IRC NAMES）
  - 不在：emit `__zchat_sys:help_requested` + 不尝试 @entry
  - 在：照常 @entry
- **router 不做 role/skill 匹配 / 降级调度** —— 那是 entry agent 借助 Socialware 干的事

### 2. Peer Discovery 原语

新增 MCP tool（agent 可调）：

```python
list_peers(channel: str) -> list[str]
    """返回该 channel 当前 IRC NAMES 里的所有 agent nick（排除 cs-bot 等 service nick）"""
```

- 数据源：IRC NAMES 实时查询（channel-server 代理）
- **不做 skill 元数据维护** —— nick 列表就够，Socialware 从 nick 反查能力
- 不从 `routing.toml` 取（那是写入快照，stale）

可选的简单增强（如果 Socialware 需要）：
- 返回值加 role hint：从 state.json 或启动 template 类型带出（best-effort，不保证准确）
- 若 Socialware 只需要 nick，保持最窄接口

## 配套清理

### `routing.toml` 字段 `agents` 处置

当前：
```toml
[channels."#conv-001".agents]
fast-001 = "yaosh-fast-001"
deep-001 = "yaosh-deep-001"
```

问题：
- router 不读
- `zchat agent stop` 不清理 → stale
- 容易误导 future reader "这是 roster ground truth"

两个选项：
- **A. 删字段**：routing.toml 只保留 bot/external_chat_id/entry_agent
  好处：minimal + 不留迷惑字段  
  代价：CLI 里 "某 channel 有哪些 agent" 的便利查询丢失（但可以走 IRC NAMES / state.json）
- **B. 保留但改语义**：明确这是"历史注册痕迹"而非 ground truth，文档标注
  好处：回溯分析某 agent 是不是曾经在过
  代价：仍有误导风险

**推荐 A**，V6/V7 交界期做。若后续发现真有用再加回来。

### `zchat agent stop` 清理

若保留 agents 字段（选 B），需要 stop 时同步删字段。否则（选 A）无此问题。

## 边界警戒线

明确 **不在 zchat 做** 的事：

- ❌ Skill metadata 注册 / 广播 / 管理
- ❌ role/scope/flow/commitment schema
- ❌ 多 agent workflow 的 DAG 定义 / 执行
- ❌ 能力匹配 / 降级策略算法
- ❌ session/task 级别的长期状态追踪

以上全部交给 Socialware。zchat 继续当"IRC-like 消息总线 + agent 生命周期管理 + 必要 MCP 原语"。

## 实现清单（V7 P?）

| 模块 | 改动 | 工作量 |
|------|------|-------|
| `zchat-channel-server/agent_mcp.py` | 新增 `list_peers(channel)` MCP tool | 0.2d |
| `zchat-channel-server/src/channel_server/router.py` | @entry 前 check NAMES，不在则 emit help_requested | 0.2d |
| `zchat-channel-server/src/channel_server/irc_connection.py` | 暴露 channel members 查询接口 | 0.1d |
| `zchat/cli/routing.py` | 若选 A：删 `agents` 字段 + `join_agent/channel_agents` 相关代码 | 0.2d |
| `routing.toml` 迁移 | 已有的 prod/ 配置清理 `agents` 字段 | 0.05d |
| tests | router NAMES 熔断 + list_peers 返回值验证 | 0.2d |

**合计 ~0.95 人日**。

## 依赖

- 飞书 bridge 不受影响
- Socialware 接入时机：等 Socialware 提供 "列出 peer 后如何决策" 的接口后，再在 zchat agent soul.md
  把工作流从硬编码（"有 deep 就委托 deep"）改成"call Socialware.dispatch(peers, intent)"

## 关联文档

- `v6-help-request-notification-design.md` · help_requested 事件
- `v6-placeholder-card-edit-design.md` · 占位卡片编辑
- `v7-roadmap-supervision.md` · squad supervises 多实例（独立主题）

## 状态

- **设计状态**：confirmed（用户 2026-04-21 明确划定 zchat 边界，不做 skill 管理）
- **实现状态**：待 V6 收尾后启动
- **归属阶段**：V7 初期
