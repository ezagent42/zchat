# V5 Pre-release 真机测试 setup note

> 2026-04-20 · 配套 `docs/discuss/plan/v5-pre-release-test-plan.md`
>
> 记录用户实际跑 §0 准备阶段时澄清的几个关键问题。文档 truth 以这里为准（plan 里如有冲突以本 note 最新结论覆盖）。

## 1. 实际飞书环境

| 项 | 值 |
|----|----|
| cs-customer 群 | `oc_4842ab45da4093cc77565fbc23dd360f`（用户 + "客户"角色 + customer bot） |
| cs-admin 群 | `oc_885883b976c16911366a75006d4a8dd6`（用户 + admin bot） |
| cs-squad 群 | `oc_ee40c7c69521c7a30184b9d5b1ce2736`（用户作为 operator + squad bot） |
| customer bot | `cli_a954c9f4d438dcb2` |
| admin bot | `cli_a96ae3ab70211cc5` |
| squad bot | `cli_a96bbd98fa781cdb` |

凭证存 `~/.zchat/projects/prod/credentials/{customer,admin,squad}.json`。

## 2. §0 步骤顺序修正

原 plan 顺序错（先填 credentials 再 `zchat project create`），已纠正：

1. §0.1 主机依赖（uv / ergo / zellij）
2. §0.2 仓库初始化
3. **§0.3 `zchat project create prod`**（先建项目骨架）
4. §0.4 写 credentials/ 三份 json
5. §0.5 用 `/tmp/list_chats.py` 一键列出每个 bot 所在群 + chat_id
6. §0.6 写 bridges/ 三份 yaml
7. §0.7a 建第 4 个空群 `cs-customer-test`（lazy create 测试用）
8. §0.7 `zchat channel create` 三条预初始化 routing.toml

## 3. 多 bridge 进程的设计

**当前方案**：每个 bot 一个 bridge 进程（3 进程）。

理由：
- `BridgeConfig` 单 `app_id` schema → 一份配置一条 WSS
- 一个 bot 崩溃不影响其他俩
- 日志 / 缓存 / token 自然隔离

**没采用的方案**：
- multi-tenant 单 process（省 2 个解释器但要重写 bridge 引入 bot_id 分桶 → V5 范围外）
- per-operator 多 app_id（误解，见下）

## 4. type 匹配机制澄清

> 用户问："type 字段在哪里？lazy create 时怎么知道要建什么 agent？"

**没有 type 字段。bot ↔ agent 类型的映射 = bridge 进程 ↔ yaml 配置。**

```
飞书事件 im.chat.member.bot.added_v1 → 按 app_id 分发到对应 bridge 进程
  ↓
该 bridge 读自己 yaml 里 lazy_create.entry_agent_template
  ↓
subprocess: zchat agent create <nick> --type <template> --channel <id>
```

| bot | 对应 bridge yaml | entry_agent_template |
|-----|------------------|----------------------|
| customer | customer.yaml | fast-agent（lazy_create=true） |
| admin | admin.yaml | admin-agent（lazy_create=false 默认安全） |
| squad | squad.yaml | squad-agent（lazy_create=false 默认安全） |

routing.toml / channel-server **完全不知道** customer/admin/squad 这些业务概念（spec §2.2 红线 3）。

### 三个 lazy_create 都开会怎样

完全可以，事件按 app_id 分发不冲突。当前默认只开 customer 是**安全策略**：
- admin/squad 群是固定的，开了用不上
- 防止误把 admin bot 拖进客户群污染 routing.toml

如果要开，只改 yaml 不改代码。

## 5. squad 监管多客户群的机制（澄清）

> 用户问："supervises 是不是要动态？squad 怎么看到所有 customer 群的卡片？"

**已经动态。我之前自编了一个 `supervises:` yaml 字段，schema 根本没有，已删除。**

实际机制：

1. `bridge.py:_reload_mappings()` 启动时 + lazy create 后从 `routing.toml` 读所有 `bot_id == customer_app_id` 的 channel
2. 这些 channel 全部进 `_channel_chat_map`
3. `group_manager.get_squad_chat(conversation_id)` 当前 hardcode 返回 `squad_chats[0].chat_id`
4. 所以**所有客户 conv 的卡片自动打到唯一的 squad 群**

squad.yaml 只需要：
```yaml
groups:
  squad_chats:
    - chat_id: oc_ee40c7c69521c7a30184b9d5b1ce2736
```

新建 conv-002 / conv-003 等懒创建出来的客户群，会自动出现在 cs-squad 群里。**无需改 yaml，无需重启 bridge。**

### 多客服多团队的场景（V5 范围外）

| 模式 | 实现 | V5 状态 |
|------|------|---------|
| A 单 squad 群所有客服共享 | 当前 | ✓ |
| B 按团队分多个 squad 群 | 需在 routing.toml 加 `squad_chat_id` + 改 `get_squad_chat()` | ❌ V6 半天工 |
| C 多 squad bot 完全隔离 | 多 bot 多进程 | ❌ 无业务必要 |

每个客服**不需要**自己的 app_id。app_id 是飞书"应用"维度，operator 用各自的飞书账号身份在群里聊就行（事件里 `sender.open_id` 区分人）。

## 6. cs-customer 群 chat_id 变更

用户清理了 customer bot 在 cs-admin / cs-squad 的 join 关系（之前误加），过程中 cs-customer 的 chat_id 也变了：

- 旧：`oc_3e33d9eddc980a800c3eefa01c6ca0f7`（已废）
- 新：`oc_4842ab45da4093cc77565fbc23dd360f`（当前）

bridges/customer.yaml 已用新值。

## 7. zellij vs tmux

V5 plan 草稿一度写成 tmux，**实际 zchat 全用 zellij**：
- `zchat/cli/zellij.py` wrapper
- `zchat/cli/agent_manager.py:243` `zellij.new_tab(...)`
- `zchat/cli/layout.py` KDL 布局

启动 cs / bridge 用 `zellij action new-tab --name X -- bash -c "..."`（plan §1 已纠正）。

## 8. 已知 CLI gap（不阻塞测试）

| Gap | 现状 | 影响 |
|-----|------|------|
| 无 `zchat cs daemon start` | 手动 zellij + python -m channel_server | 首次多一步 |
| 无 `zchat bridge start <name>` | 同上手动起 3 tab | 同上 |
| 单 bridge 多 bot | 需重构 BridgeConfig | 非紧急 |

→ post-V5 可补一个一键 wrapper（plan §5 列出来了）。

## 9. 操作步骤进度

- [x] §0.1 主机依赖
- [x] §0.2 仓库
- [x] §0.3 `zchat project create prod`
- [x] §0.4 三份 credentials json
- [x] §0.5 chat_id 用 list_chats.py 拿到
- [x] §0.6 三份 bridge yaml
- [ ] §0.7a 建 cs-customer-test 空群
- [ ] §0.7 `zchat channel create` 三条
- [ ] §1 启动服务（ergo / weechat / cs / 3 bridge / 3 agent）
- [ ] §2 TC 用例

## 10. 配置体验问题（pre-release 暴露的工程化债务）

> 跑 §0 时积累的"操作很麻烦"列表。每条都是真痛点，要在 V5+ 收口。

### 10.1 三套 app_id / app_secret 散在 N 处

当前散落点：
- `credentials/{customer,admin,squad}.json`（实际值）
- `bridges/{customer,admin,squad}.yaml`（重复一遍）
- 测试用 env vars `BOT_*_APP_ID / BOT_*_APP_SECRET / OC_*`
- `routing.toml` 又写一遍 bot_id

→ 同一个 app_id 在 4 处出现，改一个要改 4 个文件，极易不一致。

### 10.2 chat_id 获取麻烦

- 飞书 UI 不直观显示 chat_id（applink 链接 token 不解密）
- 当前靠 `/tmp/list_chats.py`（临时脚本，不在仓库）
- 用户拉 customer bot 进 cs-admin/cs-squad 想测试 → 立刻污染 list

### 10.3 三个 bridge 进程 + 三个 zellij tab 手起

- 没有 `zchat cs daemon start` / `zchat bridge start <name>`
- 用户要手敲 `zellij action new-tab --cwd ... -- bash -c "uv run python -m feishu_bridge --config ..."` 三次
- 出错排查要切三个 tab 看 log

### 10.4 jq 是个隐形依赖

- env var 用 `$(jq -r .app_secret ...)` 自动读 credentials
- 没装 jq 的机器要先装
- 不必要的工具链耦合

### 10.5 routing.toml 三条 channel create 是"对号入座"

- 已存在的 3 个群（不会触发 lazy create）必须手动 `zchat channel create` 三条
- 命令参数 `--external-chat $OC_CUSTOMER --bot-id $BOT_CUSTOMER_APP_ID --entry-agent yaosh-fast-001` 一个不能错

### 10.6 没有"setup wizard"或一键脚本

PRD US-1.x（自助上线向导）是 OOS，但**测试者自己**也是用户，没向导就只能逐步抄命令。

### → 整改方向（V5+，按 ROI 排序）

| 优先级 | 整改 | 工作量 | 收益 |
|--------|------|--------|------|
| P0 | `zchat doctor --feishu` 一键查 credentials/bridges/routing 一致性 | 1d | 高 |
| P0 | `tests/pre_release/v5-feishu-up.sh` 一键起 ergo + cs + 3 bridge + 3 agent | 0.5d | 高 |
| P0 | 把 `/tmp/list_chats.py` 收进仓库 `tools/feishu_chat_list.py` + `zchat doctor` 调用 | 0.3d | 中 |
| P1 | bridge.yaml 用 `${env_var}` 替换 → credentials 不必复制 | 0.5d | 中 |
| P1 | 单 source: 让 bridge 直接读 `credentials/*.json` 文件，删除 yaml 里 `feishu.app_id/app_secret` 字段 | 0.5d | 高 |
| P2 | `zchat cs daemon start` / `zchat bridge start <name>` CLI 命令 | 1d | 中 |
| P2 | `zchat setup feishu` 交互式 wizard（凭证 + chat_id + routing 一次配齐） | 2d | 高（user-facing） |
| P3 | bridge 多 bot 单 process（按 bot_id 分桶） | 3d | 中（运维省 2 进程） |

### 10.7 系统装的 zchat 是旧版本，无 V5 新命令

**症状**：
```
$ zchat channel create admin --external-chat $OC_ADMIN ...
Error: No such command 'channel'.
```

**原因**：`/home/yaosh/.local/bin/zchat` 装的是 PyPI/旧版 `0.3.1.dev125`，没有 V5 新增的 `channel` / `audit` 子命令；`uv run zchat`（在 `~/projects/zchat` 仓库根）才是 refactor/v4 的完整 V5 版本。

**测试期间的解法**（已采纳：方案 C alias）：
```bash
alias zchat='uv --project ~/projects/zchat run zchat'
echo "alias zchat='uv --project ~/projects/zchat run zchat'" >> ~/.bashrc
```

**长期解法**（V5 上线后）：
```bash
cd ~/projects/zchat
uv tool install --force --reinstall --editable .
# 之后 ~/.local/bin/zchat 直接是 V5 editable，改代码自动生效
```

**整改建议**（已加进 §10 大表）：
- `zchat doctor` 应显式报告"当前 zchat 二进制版本 vs 仓库 HEAD"是否一致，并给出修复命令
- pre-release 一键脚本 `v5-feishu-up.sh` 第一步先校验 zchat 版本

### 10.8 真 BUG：4 个 V5 agent 模板缺 `.env.example`

**症状**：
```
$ zchat agent create admin-0 --type admin-agent --channel admin
/home/yaosh/projects/zchat/zchat/cli/templates/admin-agent/start.sh: line 37:
ZCHAT_PROJECT_DIR: unbound variable
```

**根因**：
- `template_loader.render_env(template_name, context)` 通过解析 `<template>/.env.example` + 替换 `{{placeholder}}` 来产出 env dict
- 4 个 V5 模板（admin-agent / fast-agent / squad-agent / deep-agent）由 `d60e34f` 引入时**只复制了 soul.md / start.sh / template.toml**，漏掉 `.env.example`
- `render_env` 找不到 `.env.example` → 返回空 dict
- start.sh 用 `set -u` 严格模式 → 引用 `$ZCHAT_PROJECT_DIR / $AGENT_NAME / $MCP_SERVER_CMD` 全 unbound → 炸

**修复**（V5 plan 已遗漏，需追加）：
```bash
for dir in admin-agent fast-agent squad-agent deep-agent; do
  cp zchat/cli/templates/claude/.env.example "zchat/cli/templates/$dir/.env.example"
done
```

**追加到 Phase 12 / V5 hotfix**，提交时带：
- `feat(templates): V5 hotfix — 补齐 4 个 agent 模板缺失的 .env.example`
- 同步在 `tests/unit/test_template_loader.py` 加 case：每个 built-in 模板 `.env.example` 都存在

**整改**（已加进 §10 大表 P0）：
- `zchat doctor --templates` 校验每个 built-in 模板的必需文件齐全（`soul.md / start.sh / template.toml / .env.example`）
- pre-release 一键脚本第一步先跑此校验

### 10.9 真 BUG：`channel remove --stop-agents` 调了不存在的方法

**症状**：
```
$ zchat channel remove admin --stop-agents
Channel '#admin' removed from routing.toml.
Warning: failed to stop agent 'yaosh-admin-0':
  'AgentManager' object has no attribute 'stop_agent'
```

**根因**：`zchat/cli/app.py:1360` 调 `mgr.stop_agent(agent_name)`，但 `AgentManager` 的实际方法是 `stop(name)`（`agent_manager.py:130`）。命名不一致，单元测试漏了 `--stop-agents` 路径。

**修复**：`mgr.stop_agent(agent_name)` → `mgr.stop(agent_name)`

**整改**：
- 加 `tests/unit/test_channel_cmd.py::test_channel_remove_stop_agents` 覆盖此路径
- ralph-loop 应该 grep `mgr\.stop_agent` 检查方法名一致

### 10.10 `routing.toml` 末尾空的 `[operators]` section

**症状**：channel create 后 routing.toml 末尾出现空 section：
```toml
[operators]
```

**根因**：`zchat/cli/routing.py` 的默认 schema 包含 `operators` dict，加载时 `setdefault("operators", {})`，但 **V5 全代码无人写入**。spec v5 也没提及。

历史推测：早期设计想做 operator open_id ↔ IRC nick 映射，后简化为"飞书账号即 operator"放弃。schema 残留。

**影响**：零。CS / bridge / agent 都不读。

**整改**（V5+ 选）：
- A 删 schema reservation（`routing.py` 三处去掉 operators）
- B 真实现 `zchat operator add` + sla plugin 用此映射判定"谁是 operator"
- C 当 reservation 留着（**当前**）

非紧急，pre-release 不需要处理。

### 10.11 `channel_server` 没有 CLI args，纯 env var 驱动

**症状**：plan §1.2 让我跑 `python -m channel_server --routing X --ws-port Y ...`，全被忽略。第一次跑：
- 输出 `routing config not found: routing.toml` （它读相对路径）
- 9999 被旧进程占用 → 直接挂

**根因**：`__main__.py:26-46` 配置全走 env：
```
IRC_SERVER, IRC_PORT, IRC_TLS, IRC_PASSWORD, CS_NICK
WS_HOST, WS_PORT
CS_ROUTING_CONFIG
```

CLI args 完全不解析，跟 v5-pre-release-plan §1.2 说的不一致。

**修复 plan §1.2**：（已在对话里给出新版命令，把 plan 同步刷新即可）
```bash
zellij ... -- bash -c "
  export IRC_SERVER=127.0.0.1
  export IRC_PORT=6667
  export WS_HOST=127.0.0.1
  export WS_PORT=9999
  export CS_ROUTING_CONFIG=$PROJECT/routing.toml
  export CS_NICK=cs-bot
  uv run python -m channel_server 2>&1 | tee $PROJECT/cs.log
"
```

**整改**（V5+）：
- 给 `__main__.py` 加 typer / argparse，让 CLI args 作为 env 的 override
- 或至少 `--help` 列出所有 env vars
- pre-release plan 文档改成 env-var 形式

### 10.12 真 BUG：channel name 双 `#` 导致 CS 静默不 join

**症状**：CS 启动正常，但 `joined #admin` 等 log 没出现。bridges 没收到任何消息。

**根因**：CLI `zchat channel create admin` 把 routing.toml 的 channel key 写成 `"#admin"`（带 `#`）：
```toml
[channels."#admin"]   # 注意 key 已经带 #
```

但 CS `__main__.py:114` 和 `routing_watcher.py:55/81/88` 又拼一次 `#`：
```python
irc_conn.join(f"#{ch_id}")    # → ##admin
```

IRC server 收到 `JOIN ##admin` 当成不同 channel（实际可能直接静默扔），CS 永远不在真正的 `#admin` 里。

**修复**：在 CS 端 `lstrip("#")` 兼容两种 key 格式：
```python
irc_conn.join(f"#{ch_id.lstrip('#')}")
```

改了 `__main__.py` 1 处 + `routing_watcher.py` 3 处。

**根本整改**（V5+）：CLI `routing.add_channel` 应在写入前 normalize：
```python
ch_id = ch_id.lstrip("#")  # 永远存裸名，CS/CLI/log 自己加 #
```
保持 routing.toml 是单一表示形式。

**测试**：缺 `tests/unit/test_channel_cmd.py::test_channel_name_normalized_to_strip_hash` —
当前不管用户传 `admin` 还是 `#admin`，routing.toml 都应只存 `admin`。

### 10.13 真 BUG：CS 在 IRC welcome 之前发 JOIN 被静默拒绝

**症状**：CS log 显示 `connected as cs-bot`，但**没有** `joined #...`，bridges 永远收不到消息（路由 dead end）。

**根因**：`__main__.py:108-117` 顺序：
```python
await ws_server.start()
irc_conn.connect()       # 立即返回，IRC welcome 还未完成
for ch_id in routing.channels:
    irc_conn.join(...)   # ← 在 NICK/USER/welcome 协商完成前发 JOIN
                          #   ergo 收到 JOIN 但状态 = pre-welcome → 静默丢
```

**修复**：在 join 前等 `irc_conn._connection.is_connected()` + 缓冲 0.5s：
```python
import time as _time
_deadline = _time.time() + 5.0
while _time.time() < _deadline and not irc_conn._connection.is_connected():
    await asyncio.sleep(0.1)
await asyncio.sleep(0.5)
for ch_id in routing.channels:
    irc_conn.join(f"#{ch_id.lstrip('#')}")
```

并加 `log.info("[boot] joined #%s", normalized)` 让启动可观察。

**根本整改**（V5+）：
- `IRCConnection` 加 `connect_and_wait(timeout)` 方法，封装 welcome 等待
- 或改 `irc_conn.connect()` 本身就是 async + 内部 await welcome event
- 测试：加 `tests/unit/test_irc_connection.py::test_join_after_welcome_only` mock 验证

### 10.14 真 BUG：`feishu_bridge/__main__.py` 不初始化 logging

**症状**：3 个 bridge 启动后 log 完全空白（只有 uv 自己的 venv warning），看似全挂了。前台跑也一样。

**根因**：`__main__.py` 全文：
```python
def main():
    parser = argparse.ArgumentParser(...)
    args = parser.parse_args()
    config = load_config(args.config)
    bridge = FeishuBridge(config)
    bridge.start()
```
**没有 `logging.basicConfig`** → `log.info(...)` 默认 WARNING 级被过滤 → bridge 运行时全程哑火，对运维致命。

对比 CS：`channel_server/__main__.py:32-35` 正确做了 basicConfig。

**修复**：加进 `feishu_bridge/__main__.py`：
```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
```

**整改**（V5+）：
- 加 unit `tests/unit/test_feishu_bridge_main.py::test_logging_configured` 验证 INFO 级输出
- pre-release 一键脚本应启动后立刻 grep log，3s 内无任何输出 → fail-fast

### 10.15 真 BUG：`agent create --channel X` 不让 agent JOIN `#X`

**症状**：3 agent 都 running，但 WeeChat `/join #conv-001` 后只看到 `cs-bot` 和自己；agent 全部 JOIN 在 `#general` 里，跟 routing.toml 完全错位。

**根因**：CLI 有两个相似参数（不兼容）：
| 参数 | 作用 |
|------|------|
| `--channel <id>` 单数 | 写 routing.toml 注册（`channel_id`） |
| `--channels x,y,z` 复数 | 设 agent 进程的 `IRC_CHANNELS` env，决定 JOIN 哪些 IRC channel |

`cmd_agent_create` 实现：
```python
ch = [c.strip() for c in channels.split(",")] if channels else None
info = mgr.create(name, channels=ch, ...)
# 没传 --channels → ch=None → mgr 用默认 default_channels()=["#general"]
```

所以执行 `zchat agent create admin-0 --type admin-agent --channel admin`：
- routing.toml ✓（admin channel + admin-0 agent）
- IRC_CHANNELS = `#general`（默认）→ agent JOIN `#general`，**不在 #admin 里**

`cs-bot` 在 `#admin`、agent 在 `#general` → 永远收不到 router 的 `@yaosh-admin-0` mention。

**修复**：`cmd_agent_create` 在 `--channel` 给出 + `--channels` 没给时，自动用前者：
```python
if ch is None and channel_id:
    ch = [channel_id.lstrip("#")]
```

**根本整改**（V5+）：
- 直接合并：让 `--channel` 同时驱动 routing 注册 + IRC_CHANNELS（删 `--channels`）
- 因为 99% 用例 agent 只 JOIN 一个 channel；多 channel 是边缘场景，可后续 `zchat agent join <agent> <channel>` 命令处理
- 加 `tests/unit/test_channel_cmd.py::test_agent_create_channel_drives_irc_join`

### → 临时缓解（pre-release 测试期间）

把这段塞进 `~/.zchat/projects/prod/.env`，每次 `source` 即可：

```bash
export BOT_CUSTOMER_APP_ID=cli_a954c9f4d438dcb2
export BOT_ADMIN_APP_ID=cli_a96ae3ab70211cc5
export BOT_SQUAD_APP_ID=cli_a96bbd98fa781cdb
export BOT_CUSTOMER_APP_SECRET=$(jq -r .app_secret ~/.zchat/projects/prod/credentials/customer.json)
export BOT_ADMIN_APP_SECRET=$(jq -r .app_secret ~/.zchat/projects/prod/credentials/admin.json)
export BOT_SQUAD_APP_SECRET=$(jq -r .app_secret ~/.zchat/projects/prod/credentials/squad.json)
export OC_CUSTOMER=oc_4842ab45da4093cc77565fbc23dd360f
export OC_ADMIN=oc_885883b976c16911366a75006d4a8dd6
export OC_SQUAD=oc_ee40c7c69521c7a30184b9d5b1ce2736
```

## 11. 改动清单 + 完整启动步骤 + 清理流程（2026-04-20 测试中段总结）

### 11.1 已修改的文件（带修复）

| 文件 | 改动 | 对应 §note |
|------|------|-----------|
| `zchat/cli/templates/{admin,fast,squad,deep}-agent/.env.example` | 新建 4 文件，从 claude 模板复制 | 10.8 |
| `zchat/cli/app.py` `cmd_channel_remove` | `mgr.stop_agent` → `mgr.stop` | 10.9 |
| `zchat/cli/app.py` `cmd_agent_create` | `--channel X` 时自动设 IRC_CHANNELS=`[X]` | 10.15 |
| `zchat-channel-server/src/channel_server/__main__.py` | `lstrip("#")` + 等 IRC welcome + log [boot] joined | 10.12, 10.13 |
| `zchat-channel-server/src/channel_server/routing_watcher.py` | 3 处 `lstrip("#")` | 10.12 |
| `zchat-channel-server/src/feishu_bridge/__main__.py` | 加 `logging.basicConfig(INFO)` | 10.14 |

### 11.2 未修改（仅记录，留待 V5+ 收口）

| 项 | 影响 | §note |
|----|------|-------|
| `[operators]` 空 section 残留 schema | 0（无功能影响） | 10.10 |
| `channel_server` 不接 CLI args，纯 env var | 文档要持续靠 env var | 10.11 |
| routing.toml 写入时 normalize 该删 `#`（当前用 lstrip workaround） | 仅样式 | 10.12 末尾 |
| `IRCConnection.connect()` 应改为 async + 内部 await welcome | 当前用 sleep 5s 凑合 | 10.13 末尾 |
| 系统 zchat 不是 V5（用 alias 临时绕） | 测试期间 alias 即可 | 10.7 |
| 散在 4 处的 app_id / app_secret / chat_id | 高 | 10.1 ~ 10.6 |

### 11.3 完整从 0 启动步骤（按当前修复后状态）

```bash
# ───────── 一次性环境（如已做可跳过）─────────
which uv ergo zellij jq      # 4 个工具都得有

# 仓库 + 依赖
cd ~/projects/zchat
git checkout refactor/v4
git submodule update --init --recursive
uv sync
(cd zchat-channel-server && uv sync)

# zchat alias（V5 命令）
alias zchat='uv --project ~/projects/zchat run zchat'
echo "alias zchat='uv --project ~/projects/zchat run zchat'" >> ~/.bashrc

# ───────── 项目骨架 + credentials + bridges ─────────
zchat project create prod
zchat project use prod

mkdir -p ~/.zchat/projects/prod/credentials
# 把 customer.json / admin.json / squad.json 复制进去
# 格式: {"app_id":"cli_xxx","app_secret":"yyy"}

# .env 持久化
cat > ~/.zchat/projects/prod/.env <<'EOF'
export BOT_CUSTOMER_APP_ID=cli_a954c9f4d438dcb2
export BOT_ADMIN_APP_ID=cli_a96ae3ab70211cc5
export BOT_SQUAD_APP_ID=cli_a96bbd98fa781cdb
export BOT_CUSTOMER_APP_SECRET=$(jq -r .app_secret ~/.zchat/projects/prod/credentials/customer.json)
export BOT_ADMIN_APP_SECRET=$(jq -r .app_secret ~/.zchat/projects/prod/credentials/admin.json)
export BOT_SQUAD_APP_SECRET=$(jq -r .app_secret ~/.zchat/projects/prod/credentials/squad.json)
export OC_CUSTOMER=oc_4842ab45da4093cc77565fbc23dd360f
export OC_ADMIN=oc_885883b976c16911366a75006d4a8dd6
export OC_SQUAD=oc_ee40c7c69521c7a30184b9d5b1ce2736
EOF
source ~/.zchat/projects/prod/.env

# 三份 bridge yaml（已写好，复制即可，§0.6 模板）
mkdir -p ~/.zchat/projects/prod/bridges
# customer.yaml / admin.yaml / squad.yaml  ← 之前已写

# ───────── routing.toml 预初始化 + 启动 ─────────
zchat channel create admin     --external-chat $OC_ADMIN    --bot-id $BOT_ADMIN_APP_ID    --entry-agent yaosh-admin-0
zchat channel create squad-001 --external-chat $OC_SQUAD    --bot-id $BOT_SQUAD_APP_ID    --entry-agent yaosh-squad-0
zchat channel create conv-001  --external-chat $OC_CUSTOMER --bot-id $BOT_CUSTOMER_APP_ID --entry-agent yaosh-fast-001

# ergo + WeeChat（zchat 已封装；启动 zellij session "zchat-prod"）
zchat irc daemon start
zchat irc start

# 拿 SESSION 名给后续手动 tab 用
SESSION=$(zellij list-sessions --short | grep zchat-prod | awk '{print $1}')
PROJECT=~/.zchat/projects/prod
CS_DIR=~/projects/zchat/zchat-channel-server

# ───────── 启动 channel-server tab ─────────
zellij --session "$SESSION" action new-tab --name cs --cwd "$CS_DIR" -- \
  bash -c "
    export IRC_SERVER=127.0.0.1
    export IRC_PORT=6667
    export WS_HOST=127.0.0.1
    export WS_PORT=9999
    export CS_ROUTING_CONFIG=$PROJECT/routing.toml
    export CS_NICK=cs-bot
    uv run python -m channel_server 2>&1 | tee $PROJECT/cs.log
  "
sleep 6
grep "joined #" $PROJECT/cs.log    # 期望 3 行

# ───────── 启动 3 个 bridge tab ─────────
for B in customer admin squad; do
  zellij --session "$SESSION" action new-tab --name "bridge-$B" --cwd "$CS_DIR" -- \
    bash -c "uv run python -u -m feishu_bridge --config $PROJECT/bridges/$B.yaml 2>&1 | tee $PROJECT/bridge-$B.log"
done
sleep 5
for B in customer admin squad; do
  echo "=== bridge-$B ==="
  grep "WSS\|connected" $PROJECT/bridge-$B.log | tail -3
done

# ───────── 启动 3 个 agent（fix 已让 --channel 同时驱动 IRC_CHANNELS）─────────
zchat agent create admin-0  --type admin-agent  --channel admin
zchat agent create squad-0  --type squad-agent  --channel squad-001
zchat agent create fast-001 --type fast-agent   --channel conv-001
zchat agent list

# ───────── 收尾验证 ─────────
cat $PROJECT/state.json | grep -A1 '"channels"'    # 应是 ["admin"]/["squad-001"]/["conv-001"]
# WeeChat 内验证: /join #conv-001 → /names → 应有 cs-bot + yaosh-fast-001 + yaosh
```

### 11.4 一键全清重来（保留 credentials）

```bash
# 1. 停所有 agent + 关 zellij session + ergo
zchat agent list 2>/dev/null | awk '{print $1}' | grep -v '^$' | while read a; do
  zchat agent stop "${a#yaosh-}"  2>/dev/null
done
zchat shutdown 2>/dev/null
zchat irc daemon stop 2>/dev/null

# 2. 杀残留进程 + 占用端口
fuser -k 9999/tcp 2>/dev/null
fuser -k 6667/tcp 2>/dev/null
pkill -f "python -m channel_server" 2>/dev/null
pkill -f "python -m feishu_bridge"  2>/dev/null
pkill -f weechat 2>/dev/null

# 3. 关 zellij session（所有名字带 zchat-prod 或 prerelease 的）
for s in $(zellij list-sessions --short 2>/dev/null | awk '{print $1}'); do
  case "$s" in
    zchat-*|prerelease*|e2e-*) zellij delete-session "$s" --force 2>/dev/null ;;
  esac
done

# 4. 备份 credentials
mkdir -p /tmp/zchat-creds-backup
cp -r ~/.zchat/projects/prod/credentials/* /tmp/zchat-creds-backup/
ls /tmp/zchat-creds-backup    # 确认 3 个 json 都在

# 5. 删项目（routing.toml / agents/ / state.json / bridges/ / .env / cs.log / bridge-*.log 全清）
rm -rf ~/.zchat/projects/prod
rm -rf ~/.zchat/projects/prerelease-test 2>/dev/null
rm -f  ~/.zchat/default

# 6. 验证已干净
ls ~/.zchat/projects/ 2>&1                    # 应空
ss -tlnp | grep -E ':(6667|9999)'             # 应无输出
zellij list-sessions --short                  # 不该有 zchat-prod
```

之后从 §11.3 第一行开始重跑。

### 11.5 重新测试时直接复用 credentials

```bash
# 上面 §11.3 跑到 "mkdir -p ~/.zchat/projects/prod/credentials" 时，
# 不复制 ~/.zchat/projects/prod/credentials/*.json，改成：
cp /tmp/zchat-creds-backup/*.json ~/.zchat/projects/prod/credentials/
```

## 12. 下次复测起手式

```bash
cd ~/projects/zchat && uv run python /tmp/list_chats.py    # 验三 bot 各只在一群
zellij list-sessions                                       # 看是否有残留 zchat session
zchat agent list                                           # 看是否有残留 agent
ls ~/.zchat/projects/prod/{config.toml,routing.toml,bridges/,credentials/}
```
