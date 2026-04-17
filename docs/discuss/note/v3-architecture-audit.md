# V3 架构审计结论（最终版）

日期: 2026-04-17

## 基础设施原语

```
Project  → 工作空间配置（IRC server + routing 配置）
Channel  → IRC 频道（一个群一个 channel）
Agent    → Claude Code 实例（连接到 channel，有独立 soul.md）
```

## Channel-server = 纯消息转发

Channel-server 只做一件事：**消息进 channel → channel 内广播**。

```
入站 message → 找到 conversation 的 IRC channel → PRIVMSG → channel 内所有人收到
```

不做：
- 不判断角色（customer/operator/admin）
- 不判断可见性（public/side）
- 不过滤消息
- 不决定 Bridge 是否转发

## Gate 属于 Bridge adapter，不属于 channel-server

```
当前（错误）：
  channel-server Gate(mode, role) → visibility → 控制 Bridge 转发
  zchat_protocol/gate.py 在协议层

正确：
  channel-server 不知道 Gate
  IRC channel 中所有消息对所有参与者可见
  Bridge adapter 自己决定哪些消息转发到飞书群
  Gate 逻辑在 feishu_bridge 中
```

Gate 规则包含 operator/agent 角色名——这是业务概念，不属于协议层。

## Mode 的位置

Mode（auto/copilot/takeover）是 conversation 的状态属性，由命令切换。
但 mode 的**含义**（copilot 下 operator 消息不给客户看）是 Bridge 的业务解读。

Channel-server 存储 mode 状态，但不根据 mode 做路由决策。
Bridge adapter 查询 mode → 自己的 Gate 逻辑决定是否转发到飞书群。

## 命令分类

| 命令 | 分类 | 位置 | 说明 |
|------|------|------|------|
| /dispatch agent channel | 基础设施 | channel-server | agent 加入 channel |
| /hijack | 基础设施 | channel-server | mode 切换为 takeover |
| /release | 基础设施 | channel-server | mode 切换为 auto |
| /copilot | 基础设施 | channel-server | mode 切换为 copilot |
| /resolve | 基础设施 | channel-server | 关闭 conversation |
| /abandon | 基础设施 | channel-server | 关闭 conversation |
| /status | 业务 | agent skill | 查看状态 |
| /review | 业务 | agent skill | 查看统计 |
| /assign /reassign /squad | 业务 | agent skill | squad 管理 |

## 配置分层

```
routing.toml（基础设施配置）：
  default_agents             ← 新 conversation 自动 dispatch 谁
  escalation_chain           ← 升级时按什么顺序
  available_agents           ← dispatch 白名单

soul.md（业务指令，per-agent-type）：
  角色定义、沟通风格、行为规则
  不同 agent type 有不同模板

templates/（agent 模板）：
  ~/.zchat/templates/fast-agent/soul.md
  ~/.zchat/templates/deep-agent/soul.md
  ~/.zchat/templates/admin-agent/soul.md     ← 含 /status /review skill
  ~/.zchat/templates/squad-agent/soul.md     ← 含 /assign /squad skill
  创建 project 后手动复制到项目中，后续自动化
```

## 三个仓库改动清单

### zchat-protocol

| 文件 | 动作 |
|------|------|
| gate.py | **删除或移到 feishu_bridge**（Gate 是业务逻辑，不属于协议） |
| event.py | 删除 SLA_BREACH, SQUAD_ASSIGNED, SQUAD_REASSIGNED |
| commands.py | 保留 hijack/release/copilot/resolve/dispatch/abandon；移除 status/review/assign/reassign/squad |

### zchat-channel-server

| 文件 | 动作 |
|------|------|
| engine/command_handler.py | 移除 status/review/assign/reassign/squad 处理；移除 Gate 调用 |
| engine/message_router.py | 移除 Gate 调用——消息直接转发到 IRC channel + Bridge 广播 |
| feishu_bridge/bridge.py | 接管 Gate 逻辑——根据 mode + sender 决定是否转发到飞书群 |
| feishu_bridge/visibility_router.py | Gate 逻辑从 channel-server 移到这里 |
| plugins/sla_app.py | SLA 策略可配置 |

### zchat 主库

| 文件 | 动作 |
|------|------|
| CLI | 新增 `zchat channel create/list` 命令 |
| CLI | 新增 `zchat agent join agent channel` 命令 |
| templates/ | 提供 fast-agent/deep-agent/admin-agent/squad-agent 模板 |

## 执行计划

### Phase 1: Gate 迁移
1. zchat-protocol: gate.py 移到 feishu_bridge/（或删除，在 bridge 中重新实现）
2. channel-server engine/: 移除所有 Gate 调用
3. feishu_bridge: 接管 Gate 逻辑（根据 mode + sender 决定飞书转发）
4. 回归测试

### Phase 2: 命令清理
5. zchat-protocol commands.py: 移除业务命令
6. channel-server command_handler.py: 移除业务命令处理
7. event.py: 移除业务事件

### Phase 3: Channel 管理 + Agent 模板
8. CLI: channel/agent 命令
9. templates/: 多种 agent 模板
10. routing.toml 完善
