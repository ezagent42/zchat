# 015 · Prod 项目从零重启 Runbook

> 适用：项目状态飘移（routing entry_agent 名字不一致 / agents 假启动 / state.json 残留 / username 漂移）后想 from-scratch 重建，但**沿用既有 credentials + 既有飞书群 chat_id**。
> 不适用：完全没跑过的新机；新机走 `zchat project create` + `zchat bot add` 即可。

## 触发场景

任一现象即可考虑全重启：

- `zchat agent list` 出现两套不同 username 前缀的 agent（如 `yaosh-*` + `yaoshengyue-*` 同时存在）
- agent .ready 文件存在但 `WHOIS <agent>` 看不到 channel list（`319` 缺失） → MCP server 启动崩了
- routing.toml 里 entry_agent 名字跟 `zchat agent list` 实际跑的 nick 对不上
- voice / cs / bridge log 反复 reconnect
- 多次手动改过 routing.toml 不知道当前真相

## 保留的 vs 抹掉的

| 路径 | 行为 |
|---|---|
| `~/.zchat/projects/<name>/credentials/*.json` | **保留**（飞书 app_id/secret + voice JWT secret + Volcengine 凭证）|
| `~/.zchat/projects/<name>/routing.toml` | 备份后**重写**为初始 3 channel + 3 bot |
| `~/.zchat/projects/<name>/state.json` | 备份后清 `.agents = {}` |
| `~/.zchat/projects/<name>/agents/*` | 整体删除（agents 工作区 + .ready marker）|
| `~/.zchat/projects/<name>/log/*` | 清空（避免新旧 log 混 grep）|
| `~/.zchat/auth.json` | **不动**（除非要换 username）|
| ergo IRC server | 不动（端口 6667）|

## SOP（精简版）

```bash
cd ~/projects/zchat
PDIR=~/.zchat/projects/prod      # 改成你的项目名

# ── 1. (可选) 把 username 改成跟 routing.toml entry_agent 前缀一致 ──
# 看现有 routing 用的什么前缀
grep entry_agent $PDIR/routing.toml | head -3
# 改 auth.json 跟它对齐（避免 up 时 silent re-scope）
zchat auth login --method local --username yaosh   # ← 用你 routing 里的前缀

# ── 2. 优雅停 ──
uv run python -m zchat.cli shutdown
sleep 2
pkill -f "channel_server\|feishu_bridge\|voice_bridge" 2>/dev/null
sleep 1
zellij delete-session zchat-prod 2>/dev/null

# ── 3. 端口确认空 ──
ss -tlnp | grep -E ":6667|:9999|:8787" || echo "  ✓ 端口干净"

# ── 4. 备份 + 清 agents/state/log ──
cp $PDIR/routing.toml $PDIR/routing.toml.bak.$(date +%s)
cp $PDIR/state.json $PDIR/state.json.bak.$(date +%s)
rm -rf $PDIR/agents/* $PDIR/log/*
jq '.agents = {}' $PDIR/state.json > /tmp/s.json && mv /tmp/s.json $PDIR/state.json

# ── 5. 重写 routing.toml 为初始 3 channel ──
cat > $PDIR/routing.toml <<'EOF'
[bots.customer]
lazy_create_enabled = true
credential_file = "credentials/customer.json"
default_agent_template = "fast-agent"

[bots.admin]
lazy_create_enabled = false
credential_file = "credentials/admin.json"
default_agent_template = "admin-agent"

[bots.squad]
lazy_create_enabled = false
credential_file = "credentials/squad.json"
default_agent_template = "squad-agent"
supervises = ["customer"]

[channels."#conv-001"]
bot = "customer"
external_chat_id = "oc_4842ab45da4093cc77565fbc23dd360f"   # ← 替换为你 cs-customer 群 chat_id
entry_agent = "yaosh-fast-001"

[channels."#admin"]
bot = "admin"
external_chat_id = "oc_885883b976c16911366a75006d4a8dd6"   # ← 替换为你 cs-admin 群 chat_id
entry_agent = "yaosh-admin-0"

[channels."#squad-001"]
bot = "squad"
external_chat_id = "oc_ee40c7c69521c7a30184b9d5b1ce2736"   # ← 替换为你 cs-squad 群 chat_id
entry_agent = "yaosh-squad-0"
EOF

# ── 6. 起服务 ──
uv run python -m zchat.cli up

# ── 7. 等 agent SessionStart hook (30-60s) ──
sleep 30
ls $PDIR/agents/*.ready
# 应该有 yaosh-fast-001.ready / yaosh-admin-0.ready / yaosh-squad-0.ready

# ── 8. 验证 agent 真的在 IRC channel 里 ──
# ⚠️ ergo 默认 channel +s (secret)，外人发 NAMES 拿不到 → 必须自己 JOIN 才能看
{
  printf 'NICK probe%s\r\n' $RANDOM
  printf 'USER p 0 * :p\r\n'
  sleep 2
  printf 'JOIN #conv-001\r\n'
  sleep 1
  printf 'NAMES #conv-001\r\n'
  sleep 1
  printf 'QUIT\r\n'
} | timeout 6 nc 127.0.0.1 6667 | grep "353"
# 应看到: :ergo.test 353 probe... = #conv-001 :@cs-bot yaosh-fast-001 probe...
# 否则用 WHOIS 也行: WHOIS yaosh-fast-001 → 看 319 channel list

# ── 9. 加 deep 到 conv-001 (可选)──
uv run python -m zchat.cli agent create deep-001 --type deep-agent --channel conv-001

# ── 10. 加 voice (可选，需要 credentials/voice.json)──
# voice 自动起 — 详见 docs/guide/008-voice-setup.md

# ── 11. 完成确认 ──
uv run python -m zchat.cli agent list
# 期望: fast-001 / admin-0 / squad-0 / deep-001 都 running
```

## 常见坑

| 现象 | 真因 | 解 |
|---|---|---|
| `NAMES #channel` 返回空 | ergo channel `+s` mode，外人不能 NAMES | 先 JOIN 再 NAMES，或用 WHOIS |
| `agent.ready` 存在但 WHOIS 无 channel | MCP server 启动崩了（如 `instructions.md` 找不到）| 看 `~/.claude/projects/<agent-workspace>/<session>.jsonl` 末尾 / 标准 stderr |
| `up` 显示 `agent fast-001 started`，但 `zchat agent list` 显示 `yaoshengyue-fast-001` | username 已被 OIDC 改成 `yaoshengyue`，up 自动 re-scope；routing entry_agent 是字面快照不会跟随 | step 1 改 username 跟 routing 对齐 |
| OIDC token 刷新报 SSL 错挂掉 daemon_start | `auth.json` 有过期的 OIDC refresh_token | 走 `--method local`（跳过 OIDC 刷新链路）|
| `up` 后 voice tab `skip (no credentials/voice.json)` | voice config 没放 | 不要 voice 就忽略，要的话拷 voice.json.example 填 secret，详见 008 |
| `voice.log` 报 `unknown key 'portal_url'` | voice.json 是 Phase B 之前的旧 schema | 重写为新 schema，详见 008 |

## 切换本地 ↔ 远程（用同一套飞书 app_id）

飞书 WSS bot 协议同 app_id 只允许一条活动连接，**后连胜出**。两机共享 credentials 时：

```
本地（带 voice）   ←─┐
                    ├── 共用 customer/admin/squad 三套 credentials
远程（无 voice）  ←─┘
```

**操作**：

```bash
# 切到本地（远程飞书桥被自动踢断）
本机 $ uv run python -m zchat.cli up

# 切回远程
远程 $ zchat up
```

零配置切换，无需先 down 对面。详见 014-voice-redesign §"远程切换"段。

## 关联

- voice 接入：`docs/guide/008-voice-setup.md`
- routing.toml 字段规范：`docs/guide/006-routing-config.md`
- 完整架构：`docs/guide/001-architecture.md`
- voice 重设计：`docs/discuss/014-voice-redesign.md`
