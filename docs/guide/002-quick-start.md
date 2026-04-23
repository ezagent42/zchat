# 002 · zchat Quick Start

> 30 分钟内：装好依赖 → 起项目 → 跑通一轮飞书客服对话 → 关停。

## 0. 环境（一次性）

### 0.1 系统依赖

```bash
which uv ergo zellij jq
# 缺哪装哪：
which uv     || curl -LsSf https://astral.sh/uv/install.sh | sh
which ergo   || (cd /tmp && wget https://github.com/ergochat/ergo/releases/download/v2.13.0/ergo-2.13.0-linux-x86_64.tar.gz && tar xzf ergo-*.tar.gz && sudo mv ergo-*/ergo /usr/local/bin/)
which zellij || cargo install --locked zellij
which jq     || sudo apt-get install -y jq
```

### 0.2 安装 zchat

```bash
# 开发版（推荐）
cd ~/projects/zchat
git clone --recurse-submodules https://github.com/ezagent42/zchat.git
uv sync
(cd zchat-channel-server && uv sync)
alias zchat='uv --project ~/projects/zchat run zchat'
echo "alias zchat='uv --project ~/projects/zchat run zchat'" >> ~/.bashrc
```

健康检查：

```bash
zchat doctor
# 必要依赖（5）: uv / python3 / zellij / claude / zchat-channel
# 可选依赖 (ergo / weechat / weechat plugin / pytest / jq)
```

## 1. 创建项目

```bash
zchat project create prod
zchat project use prod
ls ~/.zchat/projects/prod/   # config.toml + 空 routing.toml
```

## 2. 注册 bot（3 个）

去飞书开放平台拿 3 个应用的 app_id / app_secret（customer / admin / squad），各自开通：
- 事件订阅：`im.message.receive_v1`、`im.chat.member.bot.added_v1`、`card.action.trigger`
- 权限：`im:message`、`im:chat`、`im:message.group_at_msg`
- 启用 WSS 长连接

**推荐 V7+ 用法**（先准备 credential 文件再注册，secret 不进 shell history）：

```bash
# 1. 写 credential 文件
mkdir -p ~/.zchat/projects/prod/credentials
cat > ~/.zchat/projects/prod/credentials/customer.json <<'EOF'
{"app_id": "cli_xxx", "app_secret": "yyy"}
EOF
# 同理写 admin.json / squad.json

# 2. 注册 bot（自动检测 credentials/<name>.json）
zchat bot add customer --template fast-agent --lazy   # lazy: 拉新群自动懒创建 channel + agent
zchat bot add admin    --template admin-agent
zchat bot add squad    --template squad-agent --supervises customer
```

**显式指定 credential 路径**：

```bash
zchat bot add customer --credential /path/to/customer.json --template fast-agent --lazy
```

> V7 起 `--app-id`/`--app-secret` 参数已移除。`app_id` 仅从 credential JSON 读取，`routing.toml` 不再写 `app_id` 字段（旧文件残留的 `app_id` 会被静默忽略）。

## 3. 注册 channel

把 3 个 bot 分别拉进对应飞书群，拿群 chat_id（飞书 API 或群信息页）：

```bash
# customer bot 所在群
zchat channel create conv-001 \
    --bot customer \
    --external-chat oc_4842ab45da40abcdef \
    --entry-agent yaosh-fast-001

# admin + squad 群
zchat channel create admin     --bot admin    --external-chat oc_admin_xxx     --entry-agent yaosh-admin-0
zchat channel create squad-001 --bot squad    --external-chat oc_squad_xxx     --entry-agent yaosh-squad-0
```

## 3.5. （可选）Plugin 配置 · `plugins.toml`

V7 起 CS 的 6 个官方 plugin (mode/sla/resolve/audit/activation/csat) 由 `channel_server.plugin_loader` 在启动时 config-driven 自动发现和注册，**无需任何配置开箱即用**。

如需调整 plugin 行为（改 SLA timer 阈值、临时禁用某 plugin、override data_dir），在项目目录下加 `plugins.toml`：

```bash
cat > ~/.zchat/projects/prod/plugins.toml <<'TOML'
[plugins.sla]
takeover_timeout = 180   # /hijack 后自动 /release 超时（秒）
help_timeout = 180       # @operator 求助等待超时（秒）

[plugins.activation]
# enabled = false        # 需要时显式禁用

[plugins.audit]
# data_dir = "/custom/path"   # 覆盖默认 <project>/plugins/audit/
TOML
```

默认 plugin state 落盘 `~/.zchat/projects/<proj>/plugins/<name>/state.json`。详见 `007-plugin-guide.md`。

## 4. 一键启动

```bash
zchat up
```

输出应为：

```
ergo: started
zellij session: zchat-prod
weechat: started
cs: started
bridge-customer: started
bridge-admin: started
bridge-squad: started
agent fast-001: started in #conv-001 (type=fast-agent)
agent admin-0: started in #admin (type=admin-agent)
agent squad-0: started in #squad-001 (type=squad-agent)
up: complete
```

**CS tab 里能看到 plugin loader 日志**（验证 V7 机制生效）：

```
[channel_server.plugin_loader] INFO plugin 'activation' registered
[channel_server.plugin_loader] INFO plugin 'audit' registered
[channel_server.plugin_loader] INFO plugin 'csat' registered
[channel_server.plugin_loader] INFO plugin 'mode' registered
[channel_server.plugin_loader] INFO plugin 'resolve' registered
[channel_server.plugin_loader] INFO plugin 'sla' registered
[channel_server.boot] INFO [boot] registered 6 plugins: [...]
```

## 5. 进入 zellij 监控

```bash
zellij attach zchat-prod
```

### Zellij 速记键位

| 操作 | 键位 |
|---|---|
| 进入 tab 切换模式 | `Ctrl-t` |
| 跳到 tab N（在 tab 模式下） | `1` ~ `9` |
| 跳到具名 tab | `Ctrl-t` 后输入 tab 名前缀 |
| 跳下 / 上一个 tab | `Ctrl-t` 后 `→ / ←` |
| 退出 tab 模式（不离开 zellij） | `Esc` |
| Detach（保留 session 后台运行） | `Ctrl-o` 后按 `d` |
| 完全杀掉 session | `Ctrl-q` |

9 个 tab 应都活着：`chat / ctl / cs / bridge-customer / bridge-admin / bridge-squad / yaosh-fast-001 / yaosh-admin-0 / yaosh-squad-0`。其中 `chat` tab 内含 pane name=weechat；`ctl` 是空 CLI pane。

每个 tab 切进去看：
- **`cs`**: `[boot] joined #conv-001 / #admin / #squad-001`
- **`bridge-*`**: `Feishu WSS connected`
- **`chat`** (pane=weechat): 切到 `#conv-001` (`/buffer 3`) 看 `/names` 应有 `cs-bot + yaosh-fast-001 + 你`

## 6. 跑一轮真实对话

模拟客户在飞书 `cs-customer` 群发：

```
你好，发货时间多久？
```

**预期 ≤3 秒内**：
- WeeChat `#conv-001` tab: `cs-bot → @yaosh-fast-001 __msg:<uuid>:你好...`
- WeeChat: `yaosh-fast-001 → __msg:<uuid>:您好！发货时间是下单后...`
- 飞书 `cs-customer` 群：bot 回复
- 飞书 `cs-squad` 群：自动出现"对话 cs-customer · 进行中" 卡片，thread 内镜像消息

跑复杂查询：

```
帮我查订单 #12345 的物流
```

**预期**（PRD US-2.2 占位 + 委托）：
- fast 立即占位："稍等，正在为您查询..."
- fast 发 side: `__side:@yaosh-deep-001 请查 #12345 的物流，edit_of=<placeholder_uuid>`
- deep 处理后 reply with edit_of → bridge `reply_in_thread` 把答复挂在占位下
- 飞书客户群：占位 + 展开答复（两层 reply 关系，上下文连续）

## 7. 关停

```bash
zchat down
# 或：
zchat shutdown
```

会停所有 agent + bridge + CS + WeeChat + ergo + zellij session。

## 8. 全清重来（保留 credentials）

```bash
zchat down
fuser -k 9999/tcp 6667/tcp 2>/dev/null
zellij delete-session zchat-prod --force 2>/dev/null
mkdir -p /tmp/zchat-creds-backup
cp -r ~/.zchat/projects/prod/credentials/* /tmp/zchat-creds-backup/
rm -rf ~/.zchat/projects/prod
zchat project create prod
mkdir -p ~/.zchat/projects/prod/credentials
cp /tmp/zchat-creds-backup/*.json ~/.zchat/projects/prod/credentials/
# 然后重跑 §2-§4
```

## 9. 常用命令

```bash
zchat agent list                 # 列所有 agent + 状态
zchat agent stop fast-001        # 停某 agent
zchat agent restart fast-001     # 重启
zchat channel list               # 列所有 channel
zchat bot list                   # 列所有 bot
zchat audit status               # 当前对话状态
zchat audit status --json | jq   # 结构化输出
zchat audit report               # 聚合指标 (CSAT / 接管率 / 升级转结案率)
zchat audit report --json | jq
```

## 10. 调试

| 现象 | 看哪里 |
|---|---|
| `zchat up` 输出全绿但进程没起（**假阳性**）| 多半是 zellij session 残留 EXITED。`zellij list-sessions` 若看到 EXITED → `zellij delete-session <name> --force` 清掉，然后 `zchat up` 重跑。详见下方"残留进程排查" |
| `zchat up` 部分服务没起 | `zellij attach zchat-prod` 进对应 tab 看红字 |
| agent 不回复客户 | 1) `zchat agent list` 状态  2) `~/.zchat/projects/prod/cs.log` 找 router 日志  3) `bridge-customer.log` 看消息是否进 CS |
| `zchat agent list` 显示 running 但实际不通 | state.json 残留上次异常退出状态。逐个 `zchat agent restart <name>` 重启即可；或 `zchat down && zchat up` 全量 |
| cs-squad 无卡片 | `bridge-squad.log` 看是否收到 message + 是否有 `[supervise] card created` |
| @operator 求助没通知 | `cs.log` grep `help_requested`，应触发 sla plugin emit |
| zellij session 进 EXITED | `zellij delete-session zchat-prod --force` 后重 `zchat up` |
| `zchat audit status` 返回空但历史有数据 | 如果从 V6 升级来，老 `audit.json` 需迁移到 V7 路径：见下方"V6→V7 迁移" |
| Claude Code 启动卡确认 | `agent_manager._auto_confirm_startup` 自动按 Enter；如新 prompt 措辞未覆盖手动按一次即可 |

### 残留进程彻底清理

`zchat shutdown` / `zchat down` 只做三件事：停 agent → 停 WeeChat+ergo → kill zellij session。遇到以下场景会有残留：

- **异常退出**（Ctrl-Q 关 zellij / SSH 断 / 机器休眠）→ shutdown 根本没跑，`state.json` 里 agent 仍标 "running"
- **zellij session EXITED 但没 delete** → `zchat up` 误以为 session 活着，`new_tab` 静默失败
- **bridge 进程** 不在 zellij tab 里跑时 → `kill_session` 杀不到

手动彻底清理：

```bash
# 1. 停 CLI 管的东西
uv run zchat down 2>/dev/null

# 2. 兜底杀残留进程
pkill -f "feishu_bridge" 2>/dev/null
pkill -f "python.*-m channel_server" 2>/dev/null
pkill -f "ergo run" 2>/dev/null
fuser -k 6667/tcp 9999/tcp 2>/dev/null

# 3. 强删所有 EXITED zellij session
for s in $(zellij list-sessions 2>&1 | grep EXITED | awk '{print $1}'); do
  zellij delete-session "$s" --force
done

# 4. （可选）state.json 强置 offline
# 如果还看到 zchat agent list 有 stale "running"，down + 编辑 state.json 改 status
```

### V6→V7 数据迁移（从 pre-2026-04-22 版本升级来）

V7 起 plugin state 路径从 `<project>/audit.json` + `activation-state.json` 改为 `<project>/plugins/<name>/state.json`。老数据**不会自动迁移**。

```bash
cd ~/.zchat/projects/<proj>
[ -f audit.json ] && mkdir -p plugins/audit && mv audit.json plugins/audit/state.json
[ -f activation-state.json ] && mkdir -p plugins/activation && mv activation-state.json plugins/activation/state.json
```

完事后 `zchat audit status --json` 应能看到历史 channel 数据。

### CLI 命令 cheatsheet

所有命令通过 `uv run zchat <cmd>` 调用（或 alias `zchat='uv --project ~/projects/zchat run zchat'`）。

**日常生产**（最常用）：
- `zchat up / down / shutdown` — 生命周期
- `zchat agent list / restart <n> / stop <n>` — agent 管控
- `zchat audit status / report [--json]` — 运营数据（V7: 读 `plugins/audit/state.json`）
- `zchat doctor` — 环境诊断
- `zchat project create / use / list` — 项目管理
- `zchat bot add / channel create` — routing.toml 配置
- `zchat channel list / bot list` — 配置查询

**偶尔用**：
- `zchat template list / show` — 查看内置 agent template（5 个）
- `zchat config get / set / list` — 全局 config.toml 管理
- `zchat setup weechat` — 安装 WeeChat plugin
- `zchat update / upgrade` — 自升级（Homebrew 用户走 `brew upgrade zchat`）

**不常用**（代码在但生产环境很少走到）：
- `zchat auth login/status/refresh/logout` — OIDC device-code flow，本地 ergo 无密码时用不上
- `zchat template create` — 仅 scaffold（复制 claude 模板），真写 agent 还要手改 soul.md + skills/
- `zchat template set` — 改 template .env override

**特殊**：
- `zchat agent send / focus / hide` — 调试用，直接和 agent tab 交互
- `zchat irc daemon start / stop / status` — 单独起停 ergo 而非跟随 up/down

若 `zchat --help` 显示 "No such command 'up'"，说明用到的是老版本全局 binary（`/home/*/.local/bin/zchat`）。用 `uv run zchat` 或重装 `uv tool install --reinstall zchat`。

## 关联

- 完整 PRD 测试用例: `006-v6-pre-release-test-plan.md`
- E2E 流程详解: `003-e2e-pre-release-test.md`
- 架构: `001-architecture.md`
