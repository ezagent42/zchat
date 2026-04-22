# 006 · 路由表配置（routing.toml）

> zchat 是 **routing.toml 驱动**的系统：CLI 写入；channel-server 启动加载 + watch reload；bridge 独立读取自己负责的 bot/channel 段。本文给完整字段规范 + 实际数据流。

## 1. 设计哲学

**routing.toml 是 zchat 唯一的"运行时动态持久化"**：
- 不存对话历史（那是 audit.json 的事，由 plugin 写）
- 不存 agent state（那是 `~/.zchat/projects/<name>/state.json`，由 agent_manager 写）
- 不存 bot 凭证（那是 `credentials/<name>.json`，独立文件）
- **只**存"哪些 bot 跑、哪些 channel 存在、哪些 agent 是 entry、哪些 bot 监管哪些 bot"

**严格 single-writer**：只有 zchat CLI 写。CS / bridge 永远只读。

**热加载 ≤2s**：CS 起 watcher 监 mtime，CLI 写完后 CS 自动 reload + 同步 IRC JOIN/PART。

**bridge 独立解析**：每个 bridge 自带 `routing_reader.py`，不 import CS 任何模块（架构红线 2）。

## 2. 字段规范（V6 ground truth）

```toml
# ┌──────────────────────────────────────────────────────────────────┐
# │  [bots."<name>"] — 每个外部平台 bot 一个条目                       │
# │  CS 加载到 RoutingTable.bots                                     │
# │  bridge 通过 routing_reader 读对应 bot 段                          │
# └──────────────────────────────────────────────────────────────────┘

[bots.customer]                                # name 必须 toml 合法 key（建议小写字母数字短横）
app_id = "cli_xxxxxxxxxxxx"                    # ✅ 必填，bridge 注册的逻辑标识
credential_file = "credentials/customer.json"  # 可选，相对 routing.toml 所在目录
default_agent_template = "fast-agent"          # 可选，lazy_create 时使用
lazy_create_enabled = true                     # 默认 false；true = bot_added 事件自动创 channel + agent
supervises = ["customer"]                      # 可选，仅当此 bot 是监管者；只 bridge 端读，CS 不读

# ┌──────────────────────────────────────────────────────────────────┐
# │  [channels."<channel_id>"] — 一个 IRC 频道一个条目                 │
# │  CS 加载到 RoutingTable.channels；router 用 entry_agent           │
# │  bridge 用 bot + external_chat_id 做 chat_id ↔ channel 映射       │
# └──────────────────────────────────────────────────────────────────┘

[channels."#conv-001"]                         # key 可带 '#'，CS load 时 lstrip 归一
bot = "customer"                               # 引用 [bots] 中的 name；不存在则 bridge 不会接收此 channel
external_chat_id = "oc_xxxxxxxxxxxx"           # 外部平台对话 ID，bridge 用做 chat_id ↔ channel 双向映射
entry_agent = "yaosh-fast-001"                 # router 在 copilot/auto 模式下 @ 此 nick；roster 由 IRC NAMES 反映
```

### 2.1 完整字段表

#### `[bots.<name>]`

| 字段 | 类型 | 必填 | 谁读 | 含义 |
|---|---|---|---|---|
| `app_id` | str | ✅ | bridge | bridge 注册时的逻辑 ID；自发回环过滤用 |
| `credential_file` | str | 推荐 | bridge | 相对 `~/.zchat/projects/<name>/` 的凭证文件路径；文件内容 schema **由 bridge 自己定**（feishu_bridge 的实际内容是 `{"app_id": "...", "app_secret": "..."}`，其它平台自己定义） |
| `default_agent_template` | str | 视场景 | CLI lazy_create | 懒创建 agent 时用哪个 template |
| `lazy_create_enabled` | bool | 默认 false | bridge | true 时 `chat_member.bot_added` 事件自动 `zchat channel create + agent create` |
| `supervises` | list[str] | 可选 | bridge (routing_reader) | 该 bot 监管哪些 bot 的 channel；V6 仅支持 bot 名字 |

#### `[channels."<id>"]`

| 字段 | 类型 | 必填 | 谁读 | 含义 |
|---|---|---|---|---|
| `bot` | str | 通常必填 | CS + bridge | 对应 `[bots]` 里的 name；省略则纯 IRC channel 无外部平台映射 |
| `external_chat_id` | str | bot 不为空时推荐 | bridge | 外部平台 chat_id；如飞书的 `oc_xxx` |
| `entry_agent` | str | 推荐 | CS router | router 在 copilot/auto 模式下 `@<entry>` 给该 agent；缺失则 emit `help_requested` 提醒人工 |

### 2.2 supervises 语法（重要）

`supervises` 字段在 `[bots.<name>]` 下，列表元素是**路由匹配规则**，bridge 启动时解析决定要订阅哪些 channel 的事件：

```toml
[bots.squad]
supervises = [
    "customer",              # ✅ V6 已实现：等价于 "bot:customer"
    "bot:customer",          # ✅ V6 已实现：bot 名前缀显式
    "tag:vip",               # ⚠️ V7 计划：按 channel tag 匹配，当前 bridge log warning + skip
    "pattern:conv-vip-*",    # ⚠️ V7 计划：按 channel id glob，当前同上
]
```

**当前 V6 行为**：bridge 启动时遍历 supervises 列表，无前缀 / `bot:` 前缀的归一化为 bot 名匹配；其它前缀打 warning 后跳过。所以**写 `tag:` / `pattern:` 不会报错**，但当前不生效。

## 3. 写入路径（CLI）

zchat CLI 是 routing.toml 唯一合法 writer：

```bash
zchat bot add <name> --app-id X --app-secret Y \
    --template fast-agent --lazy [--supervises a,b]

zchat bot list
zchat bot remove <name>

zchat channel create <id> --bot <bot_name> \
    --external-chat <oc_xxx> [--entry-agent <nick>]

zchat channel list
zchat channel set-entry <id> <nick>
zchat channel remove <id> [--stop-agents]

# agent create --channel 时，若 channel 还没 entry_agent，自动设为该 agent nick
zchat agent create <name> --type <template> --channel <id>
zchat agent join <name> <channel> [--as-entry]
```

后端写函数（`zchat/cli/routing.py`）：

| API | 写什么 |
|---|---|
| `add_bot(...)` | `[bots.<name>]` 段，所有字段 |
| `add_channel(...)` | `[channels.<id>]` 段，bot/external_chat_id/entry_agent |
| `join_agent(channel, nick, *, as_entry=False)` | 仅设 `entry_agent`（首个 agent 自动；as_entry=True 强制覆盖） |
| `set_entry_agent(channel, nick)` | 显式改 `entry_agent` |
| `remove_bot/remove_channel` | 删段 |

`zchat/cli/routing.py` 的注释明确写**不存 channel→agents 列表**：roster 由 IRC NAMES 实时反映；agent 之间发现 peer 用 `list_peers()` MCP tool。

## 4. 读取路径

### 4.1 CS 端（`channel_server/routing.py`）

```python
from channel_server.routing import load
table = load(routing_path)
# table.bots: dict[str, Bot]
# table.channels: dict[str, ChannelRoute]    # key 是 lstrip('#') 归一后的裸名
# table.entry_agent(channel_id) → str | None
```

CS 只读 3 字段：`bot` / `external_chat_id` / `entry_agent`。`supervises` / `lazy_create_enabled` 等 bridge-only 字段被 CS 静默忽略。

### 4.2 bridge 端（`feishu_bridge/routing_reader.py`）

```python
from feishu_bridge.routing_reader import read_bridge_mappings, read_supervised_channels

# 本 bot 直接负责的 channels
own = read_bridge_mappings(routing_path, bot="customer")
# {"oc_4842...": "conv-001", "oc_8858...": "conv-002"}

# 本 bot 监管的其它 bot 的 channels（如 squad supervises customer）
supervised = read_supervised_channels(routing_path, squad_bot="squad")
# {"oc_4842...": "conv-001", ...}
```

bridge 自己解析 toml，**不 import** CS 的 `routing.py`（红线 2）。

## 5. CS watch reload 机制

`channel_server/routing_watcher.py`：
1. 启动时记录 routing.toml 的 mtime
2. 每 N 秒 stat 一次，mtime 变化 → 重新 `load()`
3. diff 新旧 channels 集合 → 对增量 channel `irc_connection.join("#xxx")`，对消失的 `part`
4. `router.update_routing(new_table)` 替换 router 内 RoutingTable 引用

bridge 端不 watch（每次启动只 load 一次）；如果 routing 改了 bot/supervises，要**重启对应 bridge** 才生效。

## 6. 数据流：一次完整写入到生效

```
你: zchat channel create #fake-test --bot customer --external-chat oc_xxx
  │
  ▼
zchat/cli/app.py::cmd_channel_create
  │ 调 routing.add_channel(...)
  ▼
zchat/cli/routing.py::add_channel
  │ load_routing → 修改 dict → save_routing(tomli_w.dump)
  │ routing.toml mtime 更新
  ▼
[2 秒内]
channel_server/routing_watcher.py
  │ stat 检测到 mtime 变化 → load()
  │ diff: +{"fake-test"}, -{}
  │ irc_connection.join("#fake-test")
  │ router.update_routing(new_table)
  ▼
cs.log: [watcher] joined new channel #fake-test
       [watcher] routing reloaded: +1 channels, -0 channels
  │
  ▼
后续客户在该群发消息（如果 bridge 已通过 routing_reader 加载过这 chat_id）
  │ → bridge ws.send → router.@entry → IRC PRIVMSG → agent 处理
```

bridge 那侧的 routing 是**启动时一次性加载**的，所以新 channel 还没在 bridge 生效。两个补救：
- bridge 的 `_external_to_channel` map 在收到 `bot_added` 事件时通过 lazy_create 路径动态更新（`bridge.py::_lazy_create_channel_and_agent` + `_reload_mappings`）
- 或重启 bridge: `zchat down && zchat up`

## 7. 完整真实示例（生产）

`~/.zchat/projects/prod/routing.toml`:

```toml
# ── 3 个飞书 bot ────────────────────────────────────────
[bots.customer]
app_id = "cli_a954c9f4d438dcb2"
credential_file = "credentials/customer.json"
default_agent_template = "fast-agent"
lazy_create_enabled = true        # 拉新群自动 onboard

[bots.admin]
app_id = "cli_a96ae3ab70211cc5"
credential_file = "credentials/admin.json"
default_agent_template = "admin-agent"
lazy_create_enabled = false

[bots.squad]
app_id = "cli_a96bbd98fa781cdb"
credential_file = "credentials/squad.json"
default_agent_template = "squad-agent"
lazy_create_enabled = false
supervises = ["customer"]          # squad 监管 customer bot 的所有 channel

# ── 3 个 channel ────────────────────────────────────────
[channels."#conv-001"]
bot = "customer"
external_chat_id = "oc_4842ab45da4093cc77565fbc23dd360f"
entry_agent = "yaosh-fast-001"

[channels."#admin"]
bot = "admin"
external_chat_id = "oc_885883b976c16911366a75006d4a8dd6"
entry_agent = "yaosh-admin-0"

[channels."#squad-001"]
bot = "squad"
external_chat_id = "oc_ee40c7c69521c7a30184b9d5b1ce2736"
entry_agent = "yaosh-squad-0"
```

## 8. 字段不存在但常被想加（FAQ）

| 字段名（不存在） | 真正应该放哪 |
|---|---|
| `api_endpoint` / `host` | `credentials/<name>.json` 内（bridge 自己读） |
| `app_secret` | `credentials/<name>.json` 内 |
| `agents = {fast = "alice-fast", deep = "alice-deep"}` | **不存** —— V6 起 routing 不存 channel→agents 列表，由 IRC NAMES 反映；agent 用 `list_peers()` MCP tool 查 peer |
| `[operators.alice]` | **不存** —— V6 去 role 化，operator 通过 squad bridge 监管间接接入，不需要单独配置 |
| `default_agents = ["fast", "deep"]` | 删过了 —— V6 用 `default_agent_template` 配合 `lazy_create_enabled` |
| `mode = "copilot"` | 不存 —— mode 是运行时状态，存 mode plugin 内存中（不持久化），通过 `/hijack /release` 命令切换 |
| `csat_score = 4.5` | 不存 —— 运行时聚合在 audit.json |

## 9. 调试

```bash
# 查 routing 当前内容
cat ~/.zchat/projects/<name>/routing.toml

# 查 CS 是否 reload 了
grep -i "routing reloaded\|watcher" ~/.zchat/projects/<name>/cs.log | tail

# 查 bridge 启动时读到了哪些 channel
grep -i "bot=customer\|read_bridge_mappings" ~/.zchat/projects/<name>/bridge-customer.log | tail

# 查 router 真实用的 entry_agent
zchat channel list   # CLI 输出 entry_agent 字段
```

## 10. 反模式

```toml
# ❌ 不存在的字段（会被 CS/bridge 静默忽略，看着像配了但其实没用）
[bots.customer]
api_endpoint = "https://..."           # ❌
default_channels = ["#general"]        # ❌
operators = ["alice", "bob"]            # ❌

# ❌ 不存在的段
[operators.alice]                       # ❌ V6 去 role 化
[hooks]                                 # ❌
[runners.my-runner]                     # ❌ runner 模块的扩展点已删，见 runner.py REMOVED 注释

# ❌ 直接编辑 routing.toml 而不通过 CLI（不会破，但容易错）
# 正确：用 zchat bot add / channel create / channel set-entry
```

## 关联

- 代码: `zchat-channel-server/src/channel_server/routing.py`（CS 端）
- 代码: `zchat-channel-server/src/feishu_bridge/routing_reader.py`（bridge 端）
- 代码: `zchat/cli/routing.py`（CLI 写入端）
- example: `zchat-channel-server/routing.example.toml`
- 架构: `001-architecture.md` §2 (一条消息生命周期含路由查询)
- 迁移: `004-migrate-guide.md` §3 (新平台 bridge 的 routing 配置)
