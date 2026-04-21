# 文档拆分与补充设计

**日期**: 2026-03-22
**状态**: Approved

-----

## 1. 背景

PR #1 (`feat-complete-impl`) 完成了 PRD v3.0.0 的全部 12 项 gap 修复，同时产生了大量文档变更：

- README.md/README_zh.md 术语更新 (room→channel, dm→private)
- 新增 design spec (600 行)、implementation plan (1285 行)、manual testing guide
- weechat-channel-server/README.md 组件文档
- CLAUDE.md 更新

当前文档存在以下问题：

1. **README 过载** — 224 行，混合了架构、用法、协议、测试、路线图，一个文件承载所有内容
2. **README 与 PRD 大量重复** — 架构图、topic 层级、命令表、测试流程几乎复制粘贴
3. **受众不分** — 用户和开发者在同一个文件里找各自的信息
4. **新用户门槛高** — 假设读者了解 IRC/WeeChat 概念，没有面向现代 IM 用户的引导
5. **过程文档与正式文档混杂** — spec/plan 与用户文档在同一个 docs/ 目录

## 2. 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 受众 | 用户 + 开发者双线 | 两类受众需求不同，物理隔离 |
| 语言 | 全部中文，技术术语保持英文 | 维护成本低，未来按需加英文版 |
| PRD 定位 | 瘦身为设计决策记录 (design-decisions.md) | 只保留 why，what 分散到各文档 |
| 拆分粒度 | 用户按主题、开发按组件（混合型） | 用户按主题找答案，开发者按组件找代码 |
| 新手引导 | 独立完整入门文档 | 类比 Discord/Telegram/微信，覆盖从未用过 IRC 的用户 |
| 过程文档 | 放在 docs/superpowers/ | 不和正式文档混在一起 |

## 3. 目标文件结构

```
README.md                         # 项目简介 + 导航索引（~50 行，中文）
docs/
├── guide/                        # ── 用户文档 ──
│   ├── getting-started.md        # WeeChat 概念入门（类比 Discord/微信）
│   ├── quickstart.md             # 安装前置、启动、第一次对话
│   ├── usage.md                  # 命令参考 + 使用场景 + 独立部署
│   └── constraints.md            # 已知限制 + 路线图
├── dev/                          # ── 开发文档 ──
│   ├── architecture.md           # 架构 + 消息协议 + Zenoh topic + Signal
│   ├── weechat-zenoh.md          # weechat-zenoh 组件
│   ├── channel-server.md         # channel-server 组件
│   ├── agent.md                  # weechat-agent 组件
│   └── testing.md                # 测试策略 + 手动测试
├── design-decisions.md           # 设计原则、tradeoff、决策记录（PRD 瘦身）
└── superpowers/                  # 过程性文档（spec/plan）
    ├── specs/
    └── plans/
```

## 4. 各文件内容设计

### 4.1 README.md

重写为 ~50 行的中文导航索引：

- 一句话项目描述
- "它能做什么"（3-4 句话）
- 快速导航：用户文档 / 开发文档 / 设计文档 的链接列表
- License

删除 README_zh.md（README 本身已改为中文）。

### 4.2 docs/guide/getting-started.md（概念入门）

目标读者：只用过 Discord/Telegram/微信，没接触过 IRC 或 WeeChat 的用户。

1. **你熟悉的 IM 是怎么工作的** — 用一段话描述 Discord/微信的模型，建立共同语言
2. **WeeChat-Claude 有什么不同** — 概念对比表：

   | 概念 | Discord/微信 | WeeChat-Claude |
   |------|-------------|----------------|
   | 消息传输 | 云端服务器 | Zenoh P2P（本地/局域网） |
   | 频道/群 | #channel | `/zenoh join #channel` (channel buffer) |
   | 私聊 | DM | `/zenoh join @nick` (private buffer) |
   | 在线状态 | 绿点/灰点 | Zenoh liveliness token |
   | 聊天界面 | GUI 窗口 | WeeChat buffer（终端内"标签页"） |
   | AI 助手 | Bot 账号 | Claude Code 实例（同一协议） |

3. **核心概念** — Buffer、Nick、Channel vs Private、Agent 各一句话解释
4. **WeeChat 基本操作速查** — 切换 buffer、输入命令、发消息、看谁在线
5. **下一步** → 链接 quickstart.md

### 4.3 docs/guide/quickstart.md（安装与启动）

1. **前置条件** — 依赖列表 + 每个一句话说明（"uv 是 Python 包管理器，类似 npm"）
2. **一键启动** — `./start.sh` 命令 + 它做了什么（3 步说明）
3. **第一次对话** — 从 WeeChat 到和 agent0 说话的完整流程，附预期输出
4. **停止系统** — `./stop.sh`
5. **下一步** → 链接 usage.md

### 4.4 docs/guide/usage.md（命令参考 + 使用场景）

1. **命令速查表** — `/zenoh` 和 `/agent` 完整命令表（从 README 迁移）
2. **使用场景**（每个附架构图 + 操作步骤）：
   - 场景 1：人 ↔ 人聊天（只用 weechat-zenoh）
   - 场景 2：人 ↔ Agent 对话（weechat-zenoh + channel-server）
   - 场景 3：完整部署（三组件 + tmux）
3. **组件独立使用** — 各组件单独安装使用说明

### 4.5 docs/guide/constraints.md（限制与路线图）

1. **已知限制** — 限制表，每条附 workaround（从 README 迁移）
2. **路线图** — 未来方向列表（从 README 迁移）

### 4.6 docs/dev/architecture.md（架构与协议）

1. **系统架构** — 三组件关系图 + 设计原则：关注点分离、Zenoh topic 约定是唯一耦合点
2. **消息协议** — JSON 消息格式 + type 枚举 (msg/action/join/leave/nick)
3. **Zenoh Topic 层级** — 完整 key expression 设计（从 PRD §3.2 迁移，使用 channel/private 术语）
4. **Signal 约定** — weechat-zenoh 暴露的 signal（从 PRD §3.5 迁移，`buffer` field 格式）
5. **组件间通信流** — 一条消息从用户输入到 Agent 回复的完整数据流

### 4.7 docs/dev/weechat-zenoh.md

1. **定位** — 一句话（从 PRD §3.1）
2. **文件结构** — weechat-zenoh.py + helpers.py
3. **核心模块** — 主要函数/callback 的职责
4. **扩展点** — signal hook 方式、添加新命令
5. **注意事项** — WeeChat callback 不能阻塞、deque + timer async 模式

### 4.8 docs/dev/channel-server.md

1. **定位** — MCP server，Claude Code 子进程，stdio 通信（从 PRD §4.1）
2. **文件结构** — server.py / tools.py / message.py / skills/ 各自职责
3. **关键实现** — low-level MCP Server + notification injection via write_stream、asyncio.Queue bridge
4. **添加 MCP Tool** — 步骤（从 CLAUDE.md 迁移）
5. **独立使用** — 不需要 weechat-agent 的启动方式

### 4.9 docs/dev/agent.md

1. **定位** — Agent 生命周期管理（从 PRD §5.1）
2. **与 weechat-zenoh 的交互** — 通过 WeeChat 命令和 signal，不直接调用 Zenoh API
3. **tmux pane 管理** — pane_id 追踪、stop 定向 kill pane
4. **agent0 特殊性** — start.sh 创建，不可 stop

### 4.10 docs/dev/testing.md

1. **测试架构** — unit (mock Zenoh) vs integration (real Zenoh peer)
2. **运行测试** — 命令
3. **Fixture 说明** — MockZenohSession、integration conftest client mode
4. **手动测试指南** — 合入 PR #1 的 manual-testing.md（四个 phase）
5. **添加测试** — 约定：unit test 位置、integration 标记 `@pytest.mark.integration`

### 4.11 docs/design-decisions.md（PRD 瘦身）

从当前 PRD.md 保留：

- §1 产品概述（一句话描述、问题陈述、设计原则）
- §2 组件总览表格（定位、类型、依赖）
- §9 限制与约束（作为设计决策的约束背景）
- §10 未来演进

删除：§3-8 的详细展开（已迁移到 dev/ 和 guide/）。

术语更新：残留的 room→channel、dm→private、signal field→buffer 全部对齐。

## 5. CLAUDE.md 更新

同步更新路径引用：

- `docs/PRD.md` → `docs/design-decisions.md`，描述改为"设计决策记录"
- 测试相关指向 `docs/dev/testing.md`
- "Adding MCP Tools" 指向 `docs/dev/channel-server.md`
- Zenoh Topics 部分更新为 channel/private 术语

## 6. 迁移来源追踪

| 目标文件 | 内容来源 |
|----------|----------|
| README.md | 重写（原 README.md 内容分散到各文件） |
| guide/getting-started.md | 新写 |
| guide/quickstart.md | README §Prerequisites + §Quick Start |
| guide/usage.md | README §Usage + §Using Components Independently |
| guide/constraints.md | README §Known Constraints + §Roadmap |
| dev/architecture.md | README §Architecture + §Message Protocol + PRD §3.2 + §3.5 |
| dev/weechat-zenoh.md | PRD §3.1 + §3.6 + 代码结构 |
| dev/channel-server.md | PRD §4.1-4.5 + CLAUDE.md "Adding MCP Tools" |
| dev/agent.md | PRD §5.1-5.4 |
| dev/testing.md | README §Testing + PR#1 manual-testing.md + CLAUDE.md §Testing |
| design-decisions.md | PRD §1, §2(表格), §9, §10 |

## 7. 删除清单

| 文件 | 原因 |
|------|------|
| `README_zh.md` | README 本身改为中文 |
| `docs/PRD.md` | 重命名为 design-decisions.md |
| `docs/manual-testing.md`* | 合入 dev/testing.md |
| `docs/specs/`* | 移到 docs/superpowers/specs/ |
| `docs/plans/`* | 移到 docs/superpowers/plans/ |

*标 `*` 的文件仅存在于 PR #1 分支 (feat-complete-impl)，当前 main 分支没有。
