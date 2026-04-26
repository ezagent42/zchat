# 014 · Voice 接入重设计 — 工具化 + 删 plugin + JWT 内化

> **状态**：✅ Phase A-D 全部实施（commits bcc3adc / b5d6ed7 / 1ae9875 / dfd16ad）
> **取代**：013-voice-overlay.md §6/§7/§8（plugin 模型、分开 ASR/TTS、Phase 切片）
> **保留**：013 §1 设计立场（voice 是 channel overlay，非独立实体）/ §4 延迟预算 / §5 三级测试模型
> **触发**：本轮架构 review 发现 plugin 红线违规 + ticket/JWT 模型权衡 + AutoService 同期工作的对比启示

## 1. 背景与问题

013 落地后跑通了端到端，但暴露三个架构裂缝：

| # | 现状 | 违规 / 不洁 |
|---|---|---|
| A | `voice_portal` plugin 读 `credentials/voice.json` 拿 `jwt_secret + portal_url` | 违反 [007§8.3](../guide/007-plugin-guide.md) plugin 不读 credentials/ 红线 |
| B | `jwt_secret` 在 `credentials/voice.json` + `plugins.toml` 都需要 | 同一 secret 落两份 → rotate 痛、解耦弱 |
| C | ASR (sauc.duration) + TTS (tts/ws_binary) 分两条上游 WS | 首字延迟约 1-2s，连接数 ×2，协议帧两套 |
| D | `voice_portal` plugin 90% 代码只做"调 issue_token + emit event" | plugin 价值低；命令分派可由 agent MCP tool 替代 |

并行参考：AutoService 在 `feat/voice-native-integrated` 把 voice 做成同源 `/asr` `/tts` 两个 stateless 工具端点（`channels/web/voice/`），用 Doubao **realtime/dialogue** 一体接口 — 协议简、延迟低。这条路对 zchat 不能直接照搬（zchat 是多 channel 总线，AutoService 是单 webapp），但**协议层和"voice 不参与业务"的思路**值得借鉴。

## 2. 新形态：voice_bridge 是 web-voice-bridge

### 2.1 类比定位

```
feishu_bridge        : 飞书平台  ←→ IRC 总线
voice_bridge (新)    : web 浏览器 ←→ IRC 总线（语音变种）
```

voice_bridge 就是"web 平台的 voice 通道桥"，和 feishu_bridge 平级。两者都：
- 接外部平台（飞书 / 浏览器）
- 把外部消息译成 `ws_messages.build_message(...)` 进 CS
- 收 CS broadcast 翻译成外部平台输出

差别只在**外部平台形态**（飞书 webhook vs 浏览器 WS）和**消息载体**（卡片 / 文本 vs 音频）。

### 2.2 三个端点（voice_bridge 唯一对外）

```
HTTPS / WSS server (单端口)
├── POST /issue                  签 JWT 返回 URL（agent / 外部业务调用）
│       request:  {channel, customer, ttl_seconds?}
│       response: {url: "https://…/ws?t=<JWT>", expires_at}
├── WS   /ws?t=<JWT>             浏览器音频双向通道（验 JWT → 建 session）
└── GET  /health                 ok
```

> 不再有 `/`、`/call`、`/static/*` 的 fallback 页面 —— 浏览器集成由调用方提供，voice_bridge 不管 UI。
> dev 调试需要 demo 页面时，用 standalone 文件直接打开（file://）或反代到 voice_bridge。

### 2.3 入口：agent MCP tool（取代 plugin）

```python
# agent_mcp 新增（中性 utility，非业务）
def voice_link(channel: str, customer: str, ttl_seconds: int = 300) -> str:
    """生成给客户的语音通话链接。
    返回完整 URL；agent 可以拿去 reply 给客户。
    """
    resp = httpx.post(VOICE_BRIDGE_ISSUE_URL, json={
        "channel": channel, "customer": customer, "ttl_seconds": ttl_seconds,
    }, timeout=3)
    return resp.json()["url"]
```

agent 用 LLM 自己识别"打电话 / 给我语音 / call me"等意图，不需要 IRC 命令硬码。voice_portal plugin **整个删除**。

`VOICE_BRIDGE_ISSUE_URL` 通过 agent 启动 env 注入（`zchat agent create` 时由 CLI 写到 agent 的 settings/env，不进 routing.toml）。

### 2.4 凭证布局（无跨层、无双份）

| 文件 | 内容 | 谁读 |
|---|---|---|
| `credentials/voice.json` | `{volcengine: {app_id, access_token, ...}, jwt_secret}` | **voice_bridge only** |
| `plugins.toml` | (无 voice 段) | — |
| `routing.toml` | (无 voice 段) | — |
| `config.toml` | `[voice] enabled / listen_host / listen_port / credentials_file` | `zchat up`（决定要不要起 voice_bridge tab）|
| agent env | `VOICE_BRIDGE_ISSUE_URL=http://127.0.0.1:8787/issue` | agent_mcp 的 voice_link tool |

**红线复查**：
- ✅ plugin 不读 credentials（plugin 已删，无人读）
- ✅ routing.toml 不动（voice 不是 bot/channel/supervisor）
- ✅ `jwt_secret` 只在 voice_bridge 一处持有
- ✅ 业务术语：voice_bridge 在 bridge 层（允许业务命名），core/protocol 不变

### 2.5 公网部署的 JWT 必要性

- localhost demo / 内网：JWT 形式上仍走，但 secret rotation 无关紧要
- **公网 demo**：voice_bridge 暴露在公网 → 没 JWT 就是任何人都能开 session（白嫖语音 + 占用上游 Doubao 配额 + 进入业务 channel 发消息）
- 这里 ticket 模型不行（要 voice_bridge 的 `/issue` 也暴露公网，没 secret 任何人能签 ticket）；JWT secret 内化在 voice_bridge 自己后，唯一能签的就是它自己 → agent 走 HTTP 调 `/issue` 时 voice_bridge 验内网来源（127.0.0.1 或 mTLS）

**安全边界**（公网部署）：
```
公网:  /ws?t=<JWT>     # 浏览器入口，有 JWT 才能进 session
内网:  /issue          # agent / 业务系统调用，绑 127.0.0.1 或 mTLS
内网:  /health         # k8s probe
```

实现：voice_bridge 的 BrowserWSServer 拆两个 `serve(...)` —— `/issue` 绑 `bind_internal_host`（默认 127.0.0.1），`/ws` 绑 `bind_public_host`（默认 0.0.0.0）。或共享端口在 `process_request` hook 里按 source IP 拒 `/issue`。

### 2.6 不进 routing.toml 的理由

复盘讨论结论：voice 不是 bot（无 app_id 凭证维度），不是 channel（不 1:1 绑），不是 supervisor。
[006§1](../guide/006-routing-config.md) 设计哲学："只存哪些 bot 跑、哪些 channel 存在、哪些 agent 是 entry、哪些 bot 监管哪些 bot"。voice 不属于这四类。
[006§10](../guide/006-routing-config.md) 反模式：把"想加但不在路由维度"的东西塞进 routing.toml 是 anti-pattern。

voice session 是 **ephemeral 内存态**，TTL ≤ 通话时长，进程重启即清。不写盘、不持久化。

## 3. 协议升级（可选，强推）：Doubao realtime/dialogue

### 3.1 凭证已验证可用

实测 prod 项目 `credentials/voice.json` 的 `volcengine.app_id + access_token` 直接连：

```
URL:         wss://openspeech.bytedance.com/api/v3/realtime/dialogue
Headers:     X-Api-App-ID: <app_id>
             X-Api-Access-Key: <access_token>
             X-Api-Resource-Id: volc.speech.dialog
             X-Api-App-Key: PlgvMymc7f3tQnJ6  ← AutoService hardcoded（Doubao 公共 product key）
             X-Api-Connect-Id: <uuid>
结果:        HTTP 101 + StartConnection (event=1) → ConnectionStarted (event=50)
            session_id: aec7be12-…  X-Tt-Logid: 20260425…
```

**结论：现有 access_token 同时支持 sauc.duration / volcano_tts / volc.speech.dialog 三个资源**。无需额外开通。

### 3.2 改造范围

| 现状 | 改造后 |
|---|---|
| `voice_bridge/asr/volcengine.py` (sauc.duration WS, ~250 行) | 删除 |
| `voice_bridge/tts/volcengine.py` (tts/ws_binary WS, ~200 行) | 删除 |
| `voice_bridge/_volc_proto.py` 帧编解码 | 改为 dialog 协议（一套 frame schema，事件 ID 见 `protocol.py`）|
| `voice_bridge/bridge.py` ASR/TTS 各开一条上游 | 一条上游 dialog WS 同时承载 ASR + TTS |
| Filler / barge-in | dialog 协议自带 ChatTTSText / ClientInterrupt 事件，不再自己拼帧 |

工作量估算：~1 天（参照 AutoService `channels/web/voice/asr_client.py` + `tts_client.py` 已写好的 E2E-adapter 模式直接搬）。

### 3.3 风险

- realtime/dialogue 是较新接口，文档相对少；好在 AutoService 已经有跑通的 client 代码可以借鉴
- 要在 START_SESSION 时塞 `dialog.bot_name / system_role / speaking_style` 即使我们不用 Doubao 内置 LLM（"E2E-adapter" 模式 — 借 dialog 接口的连接复用，绕过 LLM 部分）
- 切换中需要并存调试期：保留 `--volc-mode {legacy,dialog}` 切换 flag，验证稳定后删 legacy

## 4. 端到端数据流（新版）

```
1. customer 在飞书群说"想打电话"
   │
2. feishu_bridge → CS → IRC → agent (entry_agent of #conv-001)
   │
3. agent LLM 识别意图 → 调 MCP tool voice_link("#conv-001", "ou_xxx", 300)
   │
4. agent_mcp 内部 POST http://127.0.0.1:8787/issue
       {channel:"#conv-001", customer:"ou_xxx", ttl_seconds:300}
   │
5. voice_bridge:
       - 签 JWT (内部 secret) {channel, customer, exp, nonce}
       - 返回 {"url": "https://voice.zchat.example/ws?t=<JWT>"}
   │
6. agent reply IRC: "请点链接通话：https://…"
   │
7. feishu_bridge 把 reply 转飞书卡片 → 客户看到链接
   │
8. 客户点链接 → 浏览器 → WS /ws?t=<JWT>
   │
9. voice_bridge:
       - 验 JWT → 解出 channel + customer → register session（内存）
       - 开 Doubao dialog WS（一条）
       - 浏览器 mic → ASR → final text → ws_messages.build_message → CS
       - CS broadcast → voice_bridge 收回（按 channel 过滤 session）→ TTS → 浏览器
       - 飞书 channel 同步看到所有文本（既文字又语音的 transcript 在飞书可见）
   │
10. 客户挂断 / TTL 过 / 浏览器关 → session 内存清除
```

## 5. 实施切片

每片独立 commit，可独立测试。

### Phase A · 删 voice_portal plugin、改 agent MCP tool（1 天）

- [ ] agent_mcp 加 `voice_link(channel, customer, ttl_seconds)` tool
- [ ] CLI 在 `zchat agent create` 时写入 `VOICE_BRIDGE_ISSUE_URL` 到 agent env（如果 voice 启用）
- [ ] voice_bridge 加 `POST /issue` HTTP 端点（签 JWT 返回 URL）
- [ ] 删 `src/plugins/voice_portal/`
- [ ] 删 plugins.toml 的 `[plugins.voice_portal]` 段（项目级清理）
- [ ] 测试：`agent.voice_link(...)` 返回有效 URL；浏览器用此 URL 能进 session

### Phase B · 凭证清理（半天）

- [ ] `credentials/voice.json` 保持 `jwt_secret` + `volcengine.*`，删 `portal_url`
- [ ] `config.toml` 加 `[voice] enabled / listen_host / listen_port / credentials_file`
- [ ] `zchat up` 改为读 `[voice].enabled` 决定起 voice_bridge tab（替代"检测 credentials/voice.json 是否存在"）
- [ ] voice_bridge 删 `--channel` CLI arg（dev mode 也走 JWT，由 CLI 起进程时签 dev token）

### Phase C · 公网安全边界（1 天）

- [ ] voice_bridge 拆 `/issue` 和 `/ws` 监听：默认 `/issue` 绑 127.0.0.1，`/ws` 绑 0.0.0.0
- [ ] 加 `[voice].public_host / internal_host` 配置
- [ ] 文档化部署形态：localhost / 内网 / 公网三档
- [ ] 测试：从 LAN 直接 POST `/issue` 应被拒；从 localhost 应通

### Phase D · Doubao realtime/dialogue 切换（1 天，可选）

- [ ] 从 AutoService `channels/web/voice/{protocol,doubao_client,asr_client,tts_client,config}.py` 移植
- [ ] `voice_bridge/bridge.py` 增加 dialog mode（ASR/TTS 共享一条 dialog WS）
- [ ] 加 `[voice].engine_mode = "legacy" | "dialog"` 配置
- [ ] 端到端延迟对比测试（首字延迟 + 完整 round-trip）
- [ ] 稳定后删 legacy ASR/TTS 模块

### Phase E · 文档同步（半天）

- [ ] 更新 `docs/guide/001-architecture.md` 加 voice_bridge 在 bridge 层的位置
- [ ] 新建 `docs/guide/008-voice-integration.md`（用户视角的 voice 接入指南）
- [ ] 更新 `docs/guide/006-routing-config.md` 在 §8 FAQ 加一行"voice 不在 routing.toml"
- [ ] 标记 `013-voice-overlay.md` 为部分被 014 取代

## 6. 与 013 的关系

| 013 章节 | 014 处理 |
|---|---|
| §1 设计立场（overlay / 升级模态 / 低延迟）| **保留** |
| §2 架构图 voice_bridge 形态 | **保留**，仅细化为 web-voice-bridge |
| §3 voice_bridge 进程结构 | 保留主体，删除 portal 分发 URL 路径 |
| §4 延迟预算 | **保留** |
| §5 三级测试 (L0/L1/L2) | **保留** |
| §6 JWT Token 方案（"MCP tool 签发 + plugin 分发"）| **取代**：MCP tool 不签发，调 voice_bridge `/issue` |
| §7 ASR/TTS 选型 | 选项 D：Doubao realtime/dialogue 加入并设为 V8 默认 |
| §8 MVP 切片 | 已完成 Phase 1-3；Phase 4-5 由 014 切片取代 |

## 7. 用户需决定

- [ ] **公网部署确认**：voice_bridge `/ws` 是否要直接暴露公网？是 → Phase C 必做。
- [ ] **realtime/dialogue 是否切换**：是 → Phase D 加入；否 → 跳过（继续用现有 sauc + tts/ws_binary）。
- [ ] **agent MCP tool 命名**：`voice_link` 还是 `request_voice` 还是 `give_call_url`？倾向 `voice_link`（短 + 描述返回值）。
- [ ] **dev 模式调试页面**：voice_bridge 删 `/static/*` 后，dev 怎么测试？方案：保留 `tests/voice/manual/call.html` 作为本地文件（file:// 打开），通过 query 参数手动指定 ws URL。

## 关联

- 上一版设计：`013-voice-overlay.md`
- 实测脚本：`/tmp/test_doubao_dialog.py`（验证 prod 凭证可连 realtime/dialogue）
- AutoService 参考实现：`~/projects/AutoService` `origin/dev` `channels/web/voice/`
- 红线依据：`docs/guide/006-routing-config.md` / `docs/guide/007-plugin-guide.md` / `docs/guide/001-architecture.md` §4
