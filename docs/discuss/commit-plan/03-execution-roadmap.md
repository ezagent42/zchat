# 03-执行路线图：zchat × AutoService 集成

> 从当前状态到完整产品化的分阶段执行计划，含优先级和预估时间。

## 阶段总览

```
Phase 1 (1-2天)     Phase 2 (3-5天)      Phase 3 (3-5天)       Phase 4 (2-3天)
zchat bug fix    →  zchat 总线改造    →  AutoService 迁移   →  集成测试 + 上线
+ commit 整理       + bridge 框架         + 业务层适配          + 多租户验证
```

总预估：**9-15 天**（一个人全职开发，含 Claude Code 辅助）

---

## Phase 1: zchat 整理 + bug 修复（1-2 天）

**目标**：把 zchat 当前的修改整理干净，形成稳定的 baseline。

### Step 1.1: Commit 整理（0.5 天）

按 `01-pending-changes.md` 的顺序提交 5 个 commit：

| # | Commit | 优先级 |
|---|--------|--------|
| 1 | `fix: ergo TLS config removal` | P0 |
| 2 | `feat: WSL2 proxy auto-rewrite` | P1 |
| 3 | `chore: update ezagent42-marketplace` | P2 |
| 4 | `docs: dev-loop skill specs + E2E test plan` | P2 |
| 5 | `feat: agent DM E2E test + artifacts` | P2 |

### Step 1.2: 已知 bug 修复（0.5-1 天）

| Bug | 来源 | 修复方案 |
|-----|------|---------|
| `test_unreachable_server_raises` WSL2 失败 | bootstrap-report | mock socket.create_connection 替代真实网络调用 |
| `scoped_name` 双前缀 | protocol 测试 | 在 `scoped_name()` 中检测 name 是否已有前缀 |
| E2E MCP 超时（4 个测试） | E2E 基线 | 增加 timeout 到 60s，或改为异步等待 |

### Step 1.3: 验证（0.5 天）

```bash
# 全量测试，确认 0 env error
uv run pytest tests/unit/ -v
uv run pytest tests/e2e/ -v -m e2e
cd zchat-channel-server && uv run pytest tests/ -v
cd zchat-protocol && uv run pytest tests/ -v
```

**Phase 1 完成标准**：所有 commit 已推送，已知 bug 已修复或有明确 workaround，测试全部正常执行。

---

## Phase 2: zchat 消息总线改造（3-5 天）

**目标**：zchat 从"单用户 CLI 工具"升级为"多 agent 消息总线"。

### Step 2.0: Channel-Server MSG_FILTER 改造（0.5 天）

当前 channel-server 只在检测到 `@mention` 时才转发消息给 Claude（`server.py:118`）。多 agent 场景需要不同的过滤模式。

**改动**：在 `on_pubmsg` 中增加 `MSG_FILTER` 环境变量支持：
- `mention`（默认，兼容现有行为）：只转发 @mention 消息
- `all`：转发所有消息（fast-agent、scheduler-agent 使用）
- `silent`：只转发 @mention 和 `__zchat_sys:` 系统消息（admin-agent 使用）

**改动量**：`server.py` 约 10 行 + 对应的模板配置。

**测试**：channel-server 已有 12 个单元测试，新增 3 个测试覆盖 3 种过滤模式。

### Step 2.1: Agent 模板系统（1 天）

新增 4 种 agent 模板，让 `zchat agent create --type fast-response` 直接使用：

```
zchat/cli/templates/
├── claude-channel/          # 现有默认模板
├─�� fast-response/           # 新增
│   ├── template.toml        # model 选择、default_channels
│   ├── soul.md              # 快速响应角色定义
│   ├── .env.example         # API key 模板
│   └── start.sh             # 启动脚本
├���─ deep-thinking/           # 新增
├── scheduler/               # 新增
└── admin-manager/           # 新增
```

**关键修改**：
- `runner.py` / `template_loader.py`：已支持模板机制，只需添加新模板目录
- `agent_manager.py`：`create()` 已接受 `agent_type` 参数
- 无需改代码逻辑，只需添加模板文件

### Step 2.2: Bridge 框架（2 天）

新建 `zchat-bridge/` 模块（可以是 zchat 的子模块或独立仓库）：

```
zchat-bridge/
├── pyproject.toml
├── bridge/
│   ��── __init__.py
│   ├── core.py              # BridgeCore: IRC 连接 + 消息路由
│   ├── channel_mapper.py    # 客户 ID ↔ IRC channel 映射 + 持久化
│   ├── presence.py          # 客户在线状态管理
│   └── adapters/
���       ├── __init__.py
│       ├── base.py          # BaseAdapter 抽象类
│       ├── feishu.py        # Feishu WebSocket adapter
│       └── web.py           # HTTP/WebSocket adapter
└── tests/
    ├── test_core.py
    ├── test_channel_mapper.py
    └── test_feishu_adapter.py
```

**BridgeCore 核心逻辑**（约 200 行）：
```python
class BridgeCore:
    def __init__(self, irc_server, irc_port, nick, adapter):
        self.irc = IRCClient(server, port, nick)
        self.adapter = adapter
        self.mapper = ChannelMapper(db_path)
    
    async def on_customer_message(self, customer_id, text, media):
        channel = self.mapper.get_or_create(customer_id)
        self.irc.join(channel)
        self.irc.privmsg(channel, format_bridge_message(customer_id, text, media))
    
    async def on_irc_message(self, channel, nick, text):
        if is_agent_reply(nick):
            customer_id = self.mapper.get_customer(channel)
            await self.adapter.send(customer_id, text)
```

**Feishu Adapter**（从 AutoService 的 `feishu/channel_server.py` 迁移核心逻辑）：
- 复用 Feishu WebSocket 长连接逻辑
- 复用 lark_oapi SDK 的消息收发
- 去掉 AutoService 特定的路由逻辑（由 zchat agent 的 instructions 处理）

### Step 2.3: Channel 持久化（1 天）

channel_mapper.py 需要持久化：

```python
# SQLite 存储（每个 zchat project 一个 db）
# ~/.zchat/projects/{name}/bridge.db

CREATE TABLE channels (
    customer_id TEXT PRIMARY KEY,
    irc_channel TEXT NOT NULL,
    source TEXT,           -- 'feishu' / 'web' / 'voice'
    status TEXT DEFAULT 'idle',  -- 'active' / 'idle'
    created_at TIMESTAMP,
    last_active TIMESTAMP,
    metadata JSON           -- 渠道特定数据（feishu open_id 等）
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    channel TEXT NOT NULL,
    nick TEXT NOT NULL,
    text TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT             -- 'bridge' / 'agent-fast' / 'agent-deep' / 'admin'
);
```

### Step 2.4: CLI 扩展（0.5 天）

```bash
# 新增 bridge 子命令
zchat bridge start feishu --config feishu.yaml    # 启动 Feishu bridge
zchat bridge start web --port 8080                # 启动 Web bridge
zchat bridge stop feishu                          # 停止
zchat bridge status                               # 查看所有 bridge 状态

# 新增 channel 管理
zchat channel list                                # 列出所有客户 channel
zchat channel history #cust-001 --last 50         # 查看历史
zchat channel status                              # active/idle 统计
```

**Phase 2 完成标准**：
- 4 种 agent 模板可用
- Feishu bridge 可连接 ergo 并转发消息
- channel mapper 正确持久化客户 ↔ channel 映射
- `zchat bridge` CLI 命令可用

---

## Phase 3: AutoService 业务层迁移（3-5 天）

**目标**：AutoService 从自维护基础设施迁移到 zchat 底座。

### Step 3.1: Feishu 渠道迁移（1-2 天）

| AutoService 组件 | 处理 |
|-----------------|------|
| `feishu/channel_server.py` | **删除**。WebSocket 消息路由 → zchat ergo |
| `feishu/channel.py` | **重构** → zchat-bridge feishu adapter |
| `feishu/channel-instructions.md` | **迁移** → agent workspace soul.md |
| `.feishu-credentials.json` | **保留**，bridge adapter 读取 |

核心工作：把 `channel_server.py` 的 Feishu WebSocket 长连接逻辑提取到 `zchat-bridge/bridge/adapters/feishu.py`，去掉路由逻辑。

### Step 3.2: Agent 配置迁移（1 天）

AutoService 当前通过 `autoservice.sh` + tmux 管理 agent。迁移为 zchat project 配置：

```yaml
# tenant-configs/acme/project-config.yaml
# 这个文件描述一个租户的完整配置

project_name: acme
irc:
  server: 127.0.0.1
  port: 6670

agents:
  - name: fast
    type: fast-response
    model: haiku
    channels: ["#general"]
    soul: tenant-configs/acme/souls/fast.md
    mcp_tools: [knowledge_base, product_catalog]
    
  - name: deep
    type: deep-thinking
    model: opus
    channels: ["#general"]
    soul: tenant-configs/acme/souls/deep.md
    mcp_tools: [knowledge_base, crm, pricing_engine]
    
  - name: sched
    type: scheduler
    model: sonnet
    channels: ["#general"]
    soul: tenant-configs/acme/souls/scheduler.md
    
  - name: admin
    type: admin-manager
    model: sonnet
    channels: ["#general", "#admin"]
    soul: tenant-configs/acme/souls/admin.md
    mcp_tools: [message_store, session_manager]

bridges:
  - type: feishu
    config: tenant-configs/acme/feishu-credentials.json
  - type: web
    port: 8080
```

### Step 3.3: 业务插件适配（1 天）

AutoService 的 `plugins/` 系统保持不变，但暴露方式改变：

**之前**：plugin_loader 在 channel.py 中注册 MCP tool
**之后**：plugin_loader 在每个 agent 的 channel-server 中注册 MCP tool

```python
# 每个 agent 的 .claude/settings.local.json 中配置哪些 plugin
{
    "mcpServers": {
        "zchat-channel": { ... },           # zchat channel-server（必须）
        "knowledge-base": { ... },           # 知识库 plugin
        "crm": { ... },                      # CRM plugin（仅 deep/admin）
        "pricing-engine": { ... }            # 定价引擎（仅 deep）
    }
}
```

### Step 3.4: Web 渠道适配（0.5 天）

AutoService 的 `web/app.py`（FastAPI）保留，但通过 web bridge 接入 zchat：

- `web/websocket.py` → 改为连接 zchat web bridge（不再连 channel_server.py）
- `web/app.py` 的 HTTP API 保留（用于管理面板、客户历史查询）
- 管理面板通过 `zchat channel history` 查询数据

**Phase 3 完成标准**：
- AutoService 的 `feishu/channel_server.py` 已删除
- Feishu 消息通过 zchat bridge → ergo → agent 完成闭环
- 4 种 agent 用 zchat 管理，而非 tmux
- Web 前端通过 web bridge 接入

---

## Phase 4: 集成测试 + 多租户验证（2-3 天）

### Step 4.1: 单租户端到端验证（1 天）

```
Feishu 发消息 → bridge → ergo → fast-agent 回复 → bridge → Feishu 收到
                                → scheduler 检测复杂查询 → @deep → deep 回复
                                → admin 记录全部消息
管理员查看历史 → admin-agent 查询 → 返回历史记录
管理员接管 → /hijack → admin 接管 → fast 变副驾驶
```

### Step 4.2: 多租户验证（1 天）

```bash
# 创建两个租户
zchat project create tenant-a --port 6670
zchat project create tenant-b --port 6671

# 各自启动 4 agent + bridge
# 验证：
# - 租户 A 的消息不会到租户 B
# - 两个租户可以同时在线
# - 管理员可以分别查看两个租户的历史
```

### Step 4.3: 性能和稳定性（1 天）

- Bridge 断线重连测试
- Agent 崩溃恢复测试（`zchat agent restart`）
- 高并发消息测试（模拟 10 个客户同时对话）
- Channel 状态管理测试（active → idle → reactivate）

**Phase 4 完成标准**：
- 单租户全流程跑通（Feishu → agent → 回复 → 历史 → 接管）
- 多租户隔离验证通过
- 关键故障场景有恢复机制

---

## 风险和依赖

| 风险 | 影响 | 缓解 |
|------|------|------|
| IRC 512 字节消息限制 | 长消息被截断 | zchat 已有 chunk 机制（`chunk_message` in channel-server） |
| Feishu WebSocket 长连接稳定性 | 消息丢失 | AutoService 已有重连逻辑，迁移到 bridge adapter |
| Claude Code session 冷启动慢 | agent 常驻时不影响，但崩溃重启需要时间 | 监控 + 自动 restart + 占位消息 |
| ergo 内存占用（多租户多 channel） | 服务器资源 | ergo 是 Go 写的，单实例轻量；可监控后决定是否优化 |
| 模型 API 费用（4 agent 常驻） | 运营成本 | 初期用 Haiku/Sonnet 降低成本，Opus 仅 deep-agent |

## 依赖关系

```
Phase 1 (zchat cleanup)
  └→ Phase 2 (zchat 总线改造)
       ├→ Phase 3 (AutoService 迁移) — 依赖 bridge 框架和 agent 模板
       └→ Phase 4 (集成测试) — 依赖 Phase 2 + Phase 3
```

Phase 2 和 Phase 3 有部分可以并行（agent 模板和 Feishu adapter 迁移可以同时做），但 bridge 框架是 Phase 3 的前置。
