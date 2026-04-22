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

```bash
zchat bot add customer --app-id cli_xxx --app-secret yyy \
    --template fast-agent --lazy        # lazy: 拉新群自动懒创建 channel + agent

zchat bot add admin --app-id cli_zzz --app-secret www \
    --template admin-agent

zchat bot add squad --app-id cli_aaa --app-secret bbb \
    --template squad-agent --supervises customer
```

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
| `zchat up` 部分服务没起 | `zellij attach zchat-prod` 进对应 tab 看红字 |
| agent 不回复客户 | 1) `zchat agent list` 状态  2) `~/.zchat/projects/prod/cs.log` 找 router 日志  3) `bridge-customer.log` 看消息是否进 CS |
| cs-squad 无卡片 | `bridge-squad.log` 看是否收到 message + 是否有 `[supervise] card created` |
| @operator 求助没通知 | `cs.log` grep `help_requested`，应触发 sla plugin emit |
| zellij session 进 EXITED | `zellij delete-session zchat-prod --force` 后重 `zchat up` |
| Claude Code 启动卡确认 | `agent_manager._auto_confirm_startup` 自动按 Enter；如新 prompt 措辞未覆盖手动按一次即可 |

## 关联

- 完整 PRD 测试用例: `006-v6-pre-release-test-plan.md`
- E2E 流程详解: `003-e2e-pre-release-test.md`
- 架构: `001-architecture.md`
