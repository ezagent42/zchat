# 008 · Voice 通话接入

> 给 zchat channel 加临时语音通话能力。客户在飞书群说"打电话" → fast-agent 调 `voice_link` MCP tool → 浏览器点链接接通 → 实时语音对话，文字转录同步进飞书群。

## 1. 形态速览

```
                                              voice_bridge (port 8787)
                                                ├── GET /issue       签 JWT 给 agent
                                                ├── WS  /ws?t=<JWT>  浏览器音频通道
                                                └── Doubao realtime/dialogue (云上 ASR + TTS)

  飞书客户群                        agent
  ──────────                        ─────
  "我想打电话" ──→ feishu_bridge ─→ fast-agent ──→ voice_link tool ──→ /issue → URL
  ←── 链接 ──── feishu_bridge ←─── (reply)

  浏览器接通 URL → /ws → 麦克风 PCM → ASR → IRC msg → fast-agent reply → TTS → 浏览器
```

特性：
- voice_bridge 跟 feishu_bridge 平级 — 都是"web-voice-bridge"形态的桥
- jwt_secret 内化在 voice_bridge，agent 不持有任何 secret
- voice 短命（默认 180s TTL，nonce 一次性），不进 routing.toml

详细架构 / 决策依据：`docs/discuss/014-voice-redesign.md`。

## 2. 配置 — 镜像 bot 凭证流程

zchat 不自动生成 voice 凭证（同 `zchat bot add` 一样，用户放文件 → 系统检测）。三步：

### Step 1 · 拷模板 + 生 jwt_secret

```bash
PROJECT=prod   # 改成你的项目名
PDIR=~/.zchat/projects/$PROJECT

mkdir -p $PDIR/credentials

# 拷模板 + 自动注入随机 jwt_secret
SECRET=$(openssl rand -base64 32)
sed "s|REPLACE_WITH_RANDOM.*|$SECRET|" \
  zchat-channel-server/voice.json.example > $PDIR/credentials/voice.json
chmod 600 $PDIR/credentials/voice.json
```

### Step 2 · 填 Volcengine 凭证

编辑 `$PDIR/credentials/voice.json`，把这两个字段替换成你的 Volcengine 控制台值：

```json
"volcengine": {
  "app_id": "REPLACE_WITH_VOLC_APP_ID",       // ← 你的 app_id
  "access_token": "REPLACE_WITH_VOLC_ACCESS_TOKEN",  // ← 你的 access_token
  ...
}
```

要求：access_token 已开通 `volc.speech.dialog` 资源（一般默认开通；如未开通联系火山支持）。

### Step 3 · 启动验证

```bash
zchat up                                         # voice tab 自动启
curl http://127.0.0.1:8787/health                # → ok
curl 'http://127.0.0.1:8787/issue?channel=conv-001&customer=test' | jq
# → {"url":"ws://...","expires_at":...}
```

不出预期 → 看 `~/.zchat/projects/$PROJECT/log/voice.log`。

## 3. voice.json schema

| 字段 | 必填 | 默认 | 含义 |
|---|---|---|---|
| `jwt_secret` | ✅ | — | HS256 签 JWT 用；至少 32 字节随机 |
| `volcengine.app_id` | ✅ | — | Volcengine app_id |
| `volcengine.access_token` | ✅ | — | Volcengine access_token，须含 `volc.speech.dialog` 权限 |
| `volcengine.tts_voice` | | `zh_female_vv_jupiter_bigtts` | dialog API 兼容的 speaker ID（**不能用** `BV700_streaming` 等老 ws_binary voice ID）|
| `volcengine.asr_language` | | `zh-CN` | ASR 语言（自动识别 zh/en 混合）|
| `listen_host` | | `127.0.0.1` | voice_bridge 绑的网卡。LAN/公网部署改 `0.0.0.0` |
| `listen_port` | | `8787` | |
| `cs_url` | | `ws://127.0.0.1:9999` | 上游 channel_server WS |
| `serve_static` | | `true` | 是否服务 `/`、`/call`、`/static/*` demo 页面（自家 web 集成时关）|
| `issue_loopback_only` | | `true` | `/issue` 只接 127.0.0.1 来源（agent_mcp 同主机时安全）。跨主机部署 false + 自己加 access control |
| `public_ws_url_template` | | 空（用请求 Host 头）| `/issue` 返回的 WS URL 模板。**公网 wss 部署务必设**：`"wss://voice.example.com/ws?t=%s"` |
| `asr_engine` | | `volcengine` | `stub`（loopback 测试）/ `volcengine` |
| `tts_engine` | | `volcengine` | 同上 |

## 4. fast-agent 自动得到 voice_link tool

fast-agent 模板 `.env.example` 里有：
```
VOICE_BRIDGE_ISSUE_URL=http://127.0.0.1:8787/issue
```

agent_mcp 启动时检测到此 env → 自动注册 `voice_link` MCP tool（其他 template 没此 env，看不到 tool）。

soul.md 已含使用指引：客户说"打电话/语音/call/通话" → agent 调 voice_link → 把返回的 `ws://X/ws?t=...` 改写成 `http://X/?t=...` 再 reply 给客户。

## 5. 部署形态

### Localhost demo（默认）

如上。客户 = 你自己，浏览器和 voice_bridge 同主机。

### LAN（手机 / 同事访问）

1. `voice.json`: `listen_host: "0.0.0.0"`
2. agent reply 的 URL 改用 `<服务器 LAN IP>:8787`（手动改 prompt 或加 `public_ws_url_template`）
3. 防火墙开 8787

### 公网

1. 反代 / Cloudflare Tunnel / ngrok 把 8787 暴露成 https
2. `voice.json`: `public_ws_url_template: "wss://voice.example.com/ws?t=%s"`
3. `issue_loopback_only` 保持 `true`（agent_mcp 同主机调 /issue），别开 false
4. 浏览器拿到的 URL 走公网 wss，agent_mcp → voice_bridge 走内网

## 6. 故障速查

| 现象 | 看哪 | 多半是 |
|---|---|---|
| voice tab `skip (no credentials/voice.json)` | — | Step 1 没做 |
| voice.log 启动后崩，`unknown key 'portal_url'` warning | voice.log | voice.json 还是旧 schema（含 portal_url）— 用 voice.json.example 重写 |
| ASR 出 `loopback-text` | voice.log | voice.json 缺 `asr_engine`/`tts_engine` 字段 → 默认 stub。补上 `"asr_engine": "volcengine", "tts_engine": "volcengine"` |
| TTS 报 `speaker id=BV700_streaming is invalid` | voice.log | tts_voice 是老 ws_binary voice ID。改 `zh_female_vv_jupiter_bigtts` |
| `/issue` 返回 503 | — | `jwt_secret` 为空 |
| `/issue` 返回 403 | — | 不是 loopback peer（用 `127.0.0.1`，不要 LAN IP）|
| Agent 说"voice_link 未在 MCP 暴露" | agent zellij tab | `.zchat-env` 没 VOICE_BRIDGE_ISSUE_URL → 重新创建 agent。或 fast-agent template 的 start.sh 不是新版 — 检查 `.mcp.json` env 段是否含 VOICE_BRIDGE_ISSUE_URL |
| 浏览器接通后说话有 ASR final 但听不到 agent 回复 | voice.log 看 `[voice-out]` + 是否长期 `speaker_muted=True` | barge-in mute 死锁。已修：ASR final 自动 unmute（commit XXX）|
| 浏览器接通后立刻 1008 unauthorized | voice.log | JWT 已过期（180s TTL）；或 nonce 已用过（一次性） — 重新让 agent 调 voice_link 拿新 URL |

## 关联

- 设计：[`docs/discuss/014-voice-redesign.md`](../discuss/014-voice-redesign.md)
- 上一版（部分 superseded）：[`docs/discuss/013-voice-overlay.md`](../discuss/013-voice-overlay.md)
- 模板：`zchat-channel-server/voice.json.example`
- 代码：`zchat-channel-server/src/voice_bridge/`
