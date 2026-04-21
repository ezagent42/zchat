# V6 Pre-release 真机测试计划

> 2026-04-20 · V6 架构（routing.toml [bots] + zchat up/down 一键编排）
>
> 配套：`docs/discuss/prd/AutoService-PRD.md` v1.0 + `AutoService-UserStories.md`
>
> **测试者实拥有的飞书环境**：
> - `cs-customer` — 你（模拟客服）+ 另一人（模拟客户）+ customer bot
> - `cs-admin` — 你（admin）+ admin bot
> - `cs-squad` — 你（operator）+ squad bot
> - **测试中再建第 4 个空群** `cs-customer-test`（lazy-create 测试用，先不拉 bot）
>
> **明确不在本次范围**：US-1.x 上线向导 / US-2.4 草稿 / US-3.3 5 分钟告警 / Epic 4 Dream Engine

---

## 0. 一次性环境准备

### 0.1 主机依赖

```bash
which uv ergo zellij jq          # 4 个工具都得有
# 缺哪装哪
which uv     || curl -LsSf https://astral.sh/uv/install.sh | sh
which ergo   || (cd /tmp && wget https://github.com/ergochat/ergo/releases/download/v2.13.0/ergo-2.13.0-linux-x86_64.tar.gz && tar xzf ergo-2.13.0-linux-x86_64.tar.gz && sudo mv ergo-2.13.0-linux-x86_64/ergo /usr/local/bin/)
which zellij || cargo install --locked zellij
which jq     || sudo apt-get install -y jq
```

### 0.2 仓库初始化

```bash
cd ~/projects/zchat
git checkout refactor/v4
git submodule update --init --recursive
uv sync
(cd zchat-channel-server && uv sync)

# alias 让 zchat 命令走 V6 (refactor/v4)，而不是系统 PyPI 旧版
alias zchat='uv --project ~/projects/zchat run zchat'
echo "alias zchat='uv --project ~/projects/zchat run zchat'" >> ~/.bashrc
type zchat              # 应显示 aliased
zchat --help | grep -E "bot|channel|up|audit"   # 应看到这 4 条
```

### 0.3 创建项目

```bash
zchat project create prod
zchat project use prod              # V6: 不启服务，只切默认
ls ~/.zchat/projects/prod/          # 应有 config.toml + 空 routing.toml
```

### 0.4 注册 3 个 bot（一条命令搞定 credentials + routing）

> 飞书后台拿 app_id + app_secret。每个 bot 须开通：
> - 事件订阅：`im.message.receive_v1`、`im.chat.member.bot.added_v1`、`im.chat.disbanded_v1`、`card.action.trigger`
> - 权限：`im:message`、`im:message.group_at_msg`、`im:chat`
> - 启用 WSS 长连接

```bash
# customer bot — 唯一开 lazy_create 的（用于拉新群懒创建）
zchat bot add customer \
    --app-id  cli_a954c9f4d438dcb2 \
    --app-secret 9NPcVUHRfSGBm2xA2QX5mbwlFFMqeMfX \
    --template fast-agent \
    --lazy

# admin bot
zchat bot add admin \
    --app-id  cli_a96ae3ab70211cc5 \
    --app-secret m7bfhVv8YWKVkQVXTgvAzftcpy630a5V \
    --template admin-agent

# squad bot
zchat bot add squad \
    --app-id  cli_a96bbd98fa781cdb \
    --app-secret 0LdyGBJg95ROfnIBYMYdHbPJvGuAgIsG \
    --template squad-agent

zchat bot list
# 期望 3 条
```

### 0.5 拿 3 个群的 chat_id

```bash
uv run python /tmp/list_chats.py
# 输出：每个 bot 在哪些群
# 注意：每个 bot 只应在自己应在的群里（如 customer bot 只在 cs-customer），
# 否则到飞书把不该在的 bot 移出
```

记下三个 chat_id。

### 0.6 注册 3 个 channel + 3 个 entry agent

```bash
# 直接用 chat_id（按你前面拿到的值替换）
OC_CUSTOMER=oc_4842ab45da4093cc77565fbc23dd360f
OC_ADMIN=oc_885883b976c16911366a75006d4a8dd6
OC_SQUAD=oc_ee40c7c69521c7a30184b9d5b1ce2736

zchat channel create conv-001 --bot customer --external-chat $OC_CUSTOMER --entry-agent yaosh-fast-001
zchat channel create admin     --bot admin    --external-chat $OC_ADMIN    --entry-agent yaosh-admin-0
zchat channel create squad-001 --bot squad    --external-chat $OC_SQUAD    --entry-agent yaosh-squad-0

zchat channel list
# 期望 3 条，每条 bot=xxx + ext_chat=oc_xxx + entry=yaosh-xxx 都齐全
```

### 0.7 第 4 个空群（lazy-create 测试用，先不拉 bot）

在飞书新建群 `cs-customer-test`：你 + "客户"那个人。**不拉 customer bot**——TC-PR-LazyCreate 时再拉。

无需在 routing.toml 加任何东西。

---

## 1. 一键启动

```bash
zchat up
# 期望：依次启动
#   ergo:        started
#   cs:          started
#   bridge-customer: started
#   bridge-admin:    started
#   bridge-squad:    started
#   agent yaosh-fast-001: started in #conv-001 (type=fast-agent)
#   agent yaosh-admin-0:  started in #admin (type=admin-agent)
#   agent yaosh-squad-0:  started in #squad-001 (type=squad-agent)
#   up: complete
```

### 1.1 验证全栈

```bash
zchat agent list
# 期望: 3 个 running

zellij list-sessions
# 期望: zchat-prod (current)

# zellij tab 应有：chat / cs / bridge-customer / bridge-admin / bridge-squad
#                + yaosh-admin-0 / yaosh-squad-0 / yaosh-fast-001 = 8 tab
```

### 1.2 进入 zellij 验证

```bash
zellij attach zchat-prod
# 内部按键：
#   Ctrl-t  进 tab 模式
#   数字 1-9  跳到对应 tab
#   Esc      回普通模式
#   Ctrl-o → d  detach（保留 session）
```

切到 `cs` tab，应看到：
```
[boot] joined #conv-001
[boot] joined #admin
[boot] joined #squad-001
```

切到 `bridge-customer/admin/squad`，每个应看到：
```
Feishu WSS connected
```

切到 `chat` (WeeChat) → `/join #conv-001` → `/names` 应有：cs-bot + yaosh-fast-001 + yaosh

### 1.3 一键关闭

```bash
zchat down
# 等同 zchat shutdown：停 agent + 关 zellij session + 关 ergo
```

---

## 2. PRD User Story 测试用例

> 每个 TC 前置：§1 `zchat up` 已跑、`zchat agent list` 三 agent running、bridge log 三个 WSS connected。
>
> 截图 / log 存 `tests/pre_release/evidence/v6-real-feishu/<TC-ID>/`。

---

### TC-PR-2.1 · US-2.1 — C 端客户 3 秒内看到问候

**前置**：cs-customer 群已绑 conv-001 channel；fast-agent 在 channel 内。

**步骤**：
1. 模拟客户在 cs-customer 群发：`你好，请问发货时间是多久？`
2. 同时记 T0 = `date +%s.%N`

**预期**：
- T1 = 客户群 customer bot 回复时间，T1 - T0 ≤ 3s
- bridge-customer log: `received message: chat_id=oc_..., text=你好...`
- cs.log: `[router] inbound ws: channel=conv-001, content=你好...` + `IRC PRIVMSG #conv-001 :@yaosh-fast-001 __msg:<uuid>:你好...`
- yaosh-fast-001 zellij tab: Claude 处理 → 调 `reply` tool

---

### TC-PR-2.2 · US-2.2 — 复杂查询占位 + 编辑替换

**步骤**：
1. 客户发：`帮我查订单 #12345 的物流详细到达时间，还有清关进度`

**预期**：
- ≤1s 内：客户群第一条 `__msg:uuid-A:稍等，正在为您查询...`
- ≤15s 内：**同一条消息被编辑**为完整答复（飞书 UI "已编辑"）
- IRC：先 `__msg:uuid-A:稍等` 后 `__edit:uuid-A:具体内容`
- 客户视角是一条完整消息，不是两条

---

### TC-PR-2.3 · US-2.3 — 客服群卡片 + thread 镜像

**步骤**：
1. 客户在 cs-customer 群发：`想退款`
2. 切到 cs-squad 群

**预期**：
- cs-squad 群出现 `客户对话 #conv-001` interactive card：title / mode 标签 / 接管 + 结案按钮
- 客户每条消息 + agent 每条回复都在 card thread 里镜像
- Mode 变化时卡片状态自动刷新

---

### TC-PR-2.5a · US-2.5（前半） — Agent @人 求助 + 180s timer

**步骤 — 情况 A（operator 在 180s 内回应）**：
1. 客户在 cs-customer 群发：`需要您人工帮忙审核我的退款资质`
2. 观察 yaosh-fast-001 调 `reply(side=true, text="@operator 需要您确认: ...")`（仅 cs-squad thread 可见）
3. 你（cs-squad 群里以 operator 身份）在 60s 内 thread 内回 `__side:好的，同意退款`

**预期**：
- IRC #conv-001 出现 `__side:@operator ...`
- bridge-customer 日志：side → cs-squad thread（不发 cs-customer）
- cs.log sla plugin: `started help timer for conv-001 (180s)`
- operator 回复 → sla: `cancel help timer for conv-001`
- agent 收到 → cs-customer 群发 `好的，已为您办理退款`

**步骤 — 情况 B（180s 超时）**：
重启清空状态，复客户求助场景。**operator 不要回应**，等 180s。

**预期**：
- 180s 后 sla: `help_timeout for conv-001 (operator_no_response)`
- IRC 出现 `__zchat_sys:help_timeout`
- agent 按 soul.md 向客户群发安抚消息

---

### TC-PR-2.5b · US-2.5（后半） — 人工 /hijack 抢单（卡片按钮）

**步骤**：
1. 客户在 cs-customer 群发问题；agent 已开始回复
2. 在 cs-squad 卡片上点 **接管** 按钮

**预期**：
- bridge → CS WS `{channel:"conv-001", content:"/hijack"}`
- mode plugin: `mode_changed copilot → takeover`
- IRC `__zchat_sys:{"type":"mode_changed","data":{"to":"takeover"}}`
- yaosh-fast-001 tab: 收到 sys event → 按 soul.md 退副驾驶
- cs-squad 卡片 UI 刷新为"已接管 by yaosh"
- audit plugin 记录 takeover 次数 +1

**接续 — 主动结案**：
3. 你在 cs-customer 群发：`您好，我是人工小李`（直接回客户，takeover 模式不加 @）
4. 在 cs-squad 卡片点 **结案**

**预期**：
- mode `takeover → resolved` + emit `channel_resolved`

---

### TC-PR-LazyCreate · 拉新群 → 懒创建 + 端到端 + 解散

**前置**：§0.7 已建好空群 `cs-customer-test`（customer bot 不在内）。

**步骤 A — 触发懒创建**：
1. 飞书把 customer bot 拉进 `cs-customer-test`
2. 终端：
   ```bash
   tail -f ~/.zchat/projects/prod/bridge-customer.log &
   tail -f ~/.zchat/projects/prod/cs.log &
   ```

**预期 A**：
- bridge-customer log: `Bot added to group oc_xxx` → `[lazy] creating channel=conv-<8字符> ...` → subprocess `zchat channel create ... --bot customer` 调用
- routing.toml 新增条目（含 `bot = "customer"` + `external_chat_id`）
- ≤2s cs.log: `routing.toml mtime changed, reloading` → `[watcher] joined new channel #conv-<...>`
- ≤30s `zchat agent list` 看到新 fast-agent = running

**步骤 B — 端到端复跑**：
3. 客户在 cs-customer-test 群发 `你好` → 验证 ≤3s 收到 agent 问候（同 TC-PR-2.1 在新群上）
4. 客户发复杂问题 → 验证占位 + edit（同 TC-PR-2.2）
5. cs-squad 卡片应自动出现新 conv 镜像（spec §10.3）

**步骤 C — CSAT + 老客户回访**：
6. 在新群发 `/resolve`（或 cs-squad 卡片点结案）
7. 完成 CSAT 评分（同 TC-PR-CSAT）
8. 等 30s 后客户再发 `又有问题`

**预期 C**：
- activation plugin emit `customer_returned`
- IRC `__zchat_sys:customer_returned` 注入到 fast-agent
- `~/.zchat/projects/prod/activation-state.json` 中该 channel 字段更新

**步骤 D — 解散清理**：
9. 把 customer bot 移出 cs-customer-test 群（或解散群）

**预期 D**：
- bridge 收 `im.chat.disbanded_v1` → subprocess `zchat channel remove conv-<...> --stop-agents`
- routing.toml 该条目被删
- ≤2s cs.log: `parted #conv-<...>`
- 该 fast-agent 进程被停止

---

### TC-PR-3.1 · US-3.1 — CLI 数据层（仪表盘数据源）

**前置**：跑过若干轮 conv-001 对话 + 至少一次 takeover + resolve。

```bash
zchat audit status                        # 全局 + 各 channel
zchat audit status --channel conv-001     # 单 channel 详情
zchat audit report                        # 6 维度聚合
zchat audit report --json | jq            # JSON 格式
```

**预期**：
- `status` 输出 `channels`（state / first_reply_at / takeovers / message_count / csat_score）
- `report` 输出 `total_takeovers / total_resolved / escalation_resolve_rate / csat_mean`

---

### TC-PR-3.2 · US-3.2 — admin 命令链路

**TC-PR-3.2a `/status`**：在 cs-admin 群发 `/status`
- 期望：admin-agent 调 `run_zchat_cli(["audit","status","--json"])` → 格式化为可读文本 → reply
- cs-admin 群收到当前对话列表

**TC-PR-3.2b `/dispatch`**：cs-admin 群发 `/dispatch deep-agent conv-001`
- 期望：admin-agent 调 `run_zchat_cli(["agent","create","yaosh-deep-001","--type","deep-agent","--channel","conv-001"])`
- `zchat agent list` 看到 yaosh-deep-001 = running

**TC-PR-3.2c `/review`**：cs-admin 群发 `/review`
- 期望：admin-agent 调 `run_zchat_cli(["audit","report","--json"])` → 输出聚合数字

---

### TC-PR-CSAT · 评分链路完整闭环

**前置**：conv-001 已 takeover 过至少一次。

**步骤**：
1. cs-squad 卡片点 **结案** 按钮（或 `/resolve`）
2. 模拟客户在 cs-customer 群点 4 星

**预期**：
- mode `→ resolved` + emit `channel_resolved`
- csat plugin emit `csat_request` event
- bridge-customer 在 cs-customer 群发 5 星 interactive card
- 客户点 4 星 → bridge `card.action.trigger` → WS `{channel:"conv-001", content:"__csat_score:4"}`
- csat plugin → audit.record_csat(conv-001, 4)
- audit.json 中 conv-001.csat_score = 4
- `zchat audit report` csat_mean 包含 4

---

### TC-PR-RoutingDynamic · routing.toml 动态修改 → CS 2s reload

**步骤**：
1. 手动编辑 `~/.zchat/projects/prod/routing.toml`，加纯 IRC channel：
   ```toml
   [channels."internal-test"]
   entry_agent = "yaosh-debug"
   ```
2. 等 2-3s，看 cs.log

**预期**：
- cs.log: `routing.toml mtime changed, reloading` → `joined #internal-test`
- 删该条目 → cs.log: `parted #internal-test`

---

### TC-PR-Redline · 红线静态校验（每次 release 前）

```bash
cd ~/projects/zchat/zchat-channel-server
# 红线 1: agent-mcp
grep -rn "from channel_server\|from feishu_bridge" agent_mcp.py        # 期望: 无
# 红线 2: bridge → CS
grep -rn "from channel_server" src/feishu_bridge/ | grep -v __pycache__ | grep -v "^.*\*\*"  # 期望: 无
# 红线 3: CS → bridge / 业务语义
grep -rE "feishu_bridge|admin|squad|customer" src/channel_server/ \
  | grep -v __pycache__ | grep -v "docstring\|comment"               # 期望: 仅 docstring
# 红线 4: routing.toml 写入方
grep -rn "open.*routing\.toml.*['\"]w['\"]" zchat-channel-server/ ../zchat/   # 期望: 仅 zchat/cli/routing.py

# 死代码扫描
grep -rE "is_operator_in_customer_chat|agent_nick_pattern|send_side_message|\
query_status\(\)|query_review\(\)|query_squad\(\)|assign_agent\(\)|reassign_agent\(\)|\
load_config|_bot_id|--bot-id" \
    src/ tests/ ../zchat/ docs/                                        # 期望: 仅文档残留可接受
```

---

### TC-PR-FullSuite · 全量自动化测试

```bash
(cd ~/projects/zchat/zchat-protocol && uv run pytest tests/ -q) | tail -3
# 期望: 32 passed

(cd ~/projects/zchat/zchat-channel-server && uv run pytest tests/unit tests/e2e -q) | tail -3
# 期望: 187 passed

cd ~/projects/zchat
uv run pytest tests/unit -q | tail -3
# 期望: 332 passed

uv run pytest tests/e2e/test_admin_commands_via_cli.py tests/e2e/test_audit_cli_integration.py -q | tail -3
# 期望: 8 passed
```

总计：**559 passed / 0 failed / 0 skipped**

---

## 3. 飞书 SDK 6.3 必测清单

每项真机点过后打勾。

### 3.1 SDK 凭证 / 长连接
- [ ] 三 bridge 都加载凭证不报 auth 错误
- [ ] 三 WSS 长连接稳定（启动 5s 内 log "Feishu WSS connected"）
- [ ] 模拟断网 30s → 网络恢复后自动重连

### 3.2 事件订阅
- [ ] customer bot 收到 `im.message.receive_v1`
- [ ] admin bot 收到 `im.message.receive_v1`
- [ ] squad bot 收到 `im.message.receive_v1`
- [ ] customer bot 收到 `im.chat.member.bot.added_v1`（拉新群）
- [ ] customer bot 收到 `im.chat.disbanded_v1`（解散群）
- [ ] customer bot 收到 `card.action.trigger`（CSAT 评分点击）
- [ ] squad bot 收到 `card.action.trigger`（接管 / 结案）

### 3.3 API 调用
- [ ] `send_text` → cs-customer 群（agent 普通回复）
- [ ] `send_card` → cs-squad 群（对话卡片）
- [ ] `update_message` → cs-customer 群（占位 → 完整，US-2.2）
- [ ] `reply_in_thread` → cs-squad thread（镜像 + side）
- [ ] `update_card` → cs-squad（mode_changed / resolved 时刷新）
- [ ] `send_card` CSAT 5 星 → cs-customer 群（resolve 后）

### 3.4 UI 渲染
- [ ] 对话卡片 title / mode / 接管 / 结案 按钮齐全
- [ ] takeover 后卡片状态变更
- [ ] resolved 后按钮消失
- [ ] CSAT 5 星按钮可点击

### 3.5 降级
- [ ] 网络断开 bridge 不 crash
- [ ] 错误凭证启动 bridge → log 明确报错
- [ ] 飞书 API 429 → bridge 重试不丢消息

---

## 4. 总验收门槛

| 项 | 标准 | 必须 |
|---|------|------|
| TC-PR-2.1 ~ 2.6 | 全过 | ✓ |
| TC-PR-3.1 ~ 3.2c | 全过 | ✓ |
| TC-PR-CSAT | 评分入 audit.json | ✓ |
| TC-PR-LazyCreate | 4 步 ABCD 全过 | ✓ |
| TC-PR-RoutingDynamic | 修改 → 2-5s 自动 reload | ✓ |
| TC-PR-Redline | 4 红线 + 死代码 grep clean | ✓ |
| TC-PR-FullSuite | 559 passed / 0 failed | ✓ |
| 飞书 SDK 6.3 | 全部勾选 | ✓ |

---

## 5. 失败排查速查

| 现象 | 排查 |
|------|------|
| `zchat up` 部分服务没起 | 看 zellij 对应 tab 的报错（Ctrl-t → 切 tab） |
| customer 群 agent 不回复 | `tail -f ~/.zchat/projects/prod/cs.log`；`zchat agent list` 状态 |
| cs-squad 无卡片 | bridge-squad log 看是否收到事件；`get_squad_chat` 返回值 |
| help_timeout 没触发 | sla plugin log；source 不含 operator 标记 |
| /status 无响应 | admin-agent zellij tab；`zchat audit status` 直接跑确认 CLI |
| routing.toml 改了 CS 没动 | watcher 启动 log；vim 默认 atomic write 不会破坏 mtime |
| CSAT 评分丢失 | bridge `_on_card_action` log；`__csat_score:N` 是否到 csat plugin |
| 跨层 import 漏 | `grep "from channel_server" src/feishu_bridge/` 检查 |

---

## 6. 一键全清重来（保留 credentials）

```bash
# 1. 停所有服务
zchat down

# 2. 杀残留 + 关 zellij
fuser -k 9999/tcp 2>/dev/null
fuser -k 6667/tcp 2>/dev/null
pkill -f "channel_server" 2>/dev/null
pkill -f "feishu_bridge" 2>/dev/null
pkill -f weechat 2>/dev/null
for s in $(zellij list-sessions --short 2>/dev/null); do
  zellij delete-session "$s" --force 2>/dev/null
done

# 3. 备份 credentials
mkdir -p /tmp/zchat-creds-backup
cp -r ~/.zchat/projects/prod/credentials/* /tmp/zchat-creds-backup/
ls /tmp/zchat-creds-backup

# 4. 删项目
rm -rf ~/.zchat/projects/prod
rm -f  ~/.zchat/default

# 5. 验证干净
ls ~/.zchat/projects/ 2>&1                  # 空
ss -tlnp | grep -E ':(6667|9999)'           # 无
zellij list-sessions --short                # 无

# 6. 重测时复用 credentials（可选）
# §0.4 跑 `zchat bot add` 时手抄 app_id/app_secret，
# 或：mkdir -p ~/.zchat/projects/prod/credentials &&
#     cp /tmp/zchat-creds-backup/*.json ~/.zchat/projects/prod/credentials/
# 然后用 jq 提取再传给 `zchat bot add`：
#   APP_ID=$(jq -r .app_id /tmp/zchat-creds-backup/customer.json)
#   APP_SECRET=$(jq -r .app_secret /tmp/zchat-creds-backup/customer.json)
#   zchat bot add customer --app-id $APP_ID --app-secret $APP_SECRET --template fast-agent --lazy
```

---

## 7. 完整 V6 启动总流程（cheat sheet）

```bash
# 一次性
alias zchat='uv --project ~/projects/zchat run zchat'
zchat project create prod
zchat project use prod
zchat bot add customer --app-id ... --app-secret ... --template fast-agent --lazy
zchat bot add admin    --app-id ... --app-secret ... --template admin-agent
zchat bot add squad    --app-id ... --app-secret ... --template squad-agent
uv run python /tmp/list_chats.py    # 拿 chat_id
zchat channel create conv-001  --bot customer --external-chat oc_xxx --entry-agent yaosh-fast-001
zchat channel create admin     --bot admin    --external-chat oc_xxx --entry-agent yaosh-admin-0
zchat channel create squad-001 --bot squad    --external-chat oc_xxx --entry-agent yaosh-squad-0

# 每天启动 / 关闭
zchat up
# 测试...
zchat down
```

---

*基于 V6 架构 (routing.toml [bots] + zchat up/down + bot CRUD) + PRD v1.0 + UserStories v1.0。*
