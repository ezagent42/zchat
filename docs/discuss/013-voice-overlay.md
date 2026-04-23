# 013 · Voice Overlay — 给 zchat channel 加临时语音通话能力

> **状态**：draft，等拍板后动代码
> **分支**：`feat/voice-bridge`
> **目标**：达到 cc-openclaw 的"打电话的感觉" — 客户点链接进浏览器，<1s 端到端延迟的实时语音对话；同一段对话在飞书群文字 transcript 同步可见；不依赖飞书即可独立测试。

## 1. 设计立场

### 1.1 Voice 是 channel 上的一次性 overlay，不是独立实体

- **IRC channel** 是持久总线（例：`#conv-001`，归属飞书群 `oc_xxx`）
- **飞书群** 持久 external（feishu_bridge 管，写在 routing.toml）
- **语音 session** 短命 overlay（客户点链接→浏览器→讲完挂掉），不进 routing.toml
- voice_bridge 作为 WS 客户端连 CS，**零 routing schema 变动**，任何消息在 IRC 出现就同时被 voice_bridge 和 feishu_bridge 听到

### 1.2 升级模态，不是替换

- 客户先在飞书群文字提问（feishu_bridge 处理）
- 某个时刻 agent 调 MCP tool `voice.issue_link` 生成带 JWT 的 URL
- agent 把 URL 发进飞书群
- 客户点链接 → 浏览器 → voice_bridge → WS 绑 `#conv-001`
- voice / 飞书文字 / agent 三路消息在同一 IRC channel 汇流

### 1.3 低延迟是第一级目标

> "打电话的感觉" = **<800ms 端到端**（customer 说完一句 → customer 听到 agent 回复的第一个字），**支持 barge-in**（customer 能打断）

技术选型首轮：优先能达到这个数字的方案。

## 2. 架构

```
  客户浏览器                                         飞书群 (oc_xxx)
  ┌────────────┐                                  ┌──────────────┐
  │ <audio>     │◄─TTS chunks────┐                │              │
  │ MediaRecorder─►PCM opus─┐    │                │              │
  └─────────┬──┘             │   │                └──▲───────────┘
            │ WebSocket       │   │                   │ Feishu API
            │ /call?t=JWT     ▼   ▼                   │
  ┌─────────┴──────────────────────────┐     ┌───────┴─────────┐
  │  voice_bridge (新进程)              │     │ feishu_bridge    │
  │  ┌──────────────────────────────┐  │     │ (已有)            │
  │  │ WS server (客户连进)          │  │     │                  │
  │  │ ASR streaming (whisper/vol..) │  │     │                  │
  │  │ TTS streaming (piper/edge..)  │  │     │                  │
  │  │ session → channel 映射 (RAM)  │  │     │                  │
  │  │ WS client (连 CS)             │  │     │                  │
  │  └──────────────────────────────┘  │     │                  │
  └────────────┬───────────────────────┘     └──────▲───────────┘
               │ WS                                  │ WS
               ▼                                      │
      ┌────────────────────────────────────────────┐
      │            channel_server                   │
      │  router + ws.broadcast(msg) to all bridges  │
      └────────────────────┬───────────────────────┘
                           │ IRC PRIVMSG
                           ▼
                      #conv-001
                           │
                  ┌────────┴──────────┐
                  │                   │
           linyilun-fast-001   linyilun-deep-001
```

### 2.1 对 zchat 其他模块的改动

| 模块 | 改动 |
|------|------|
| `channel_server` | **零改动** — `ws.broadcast` 已经广播给所有 bridge |
| `routing.toml` schema | **零改动** — voice 不进 schema |
| `feishu_bridge` | **零改动** — 它收到 IRC 消息时不需要知道消息来自哪种模态 |
| `zchat/cli` | 加 `zchat voice` 子命令组（start / test / status） |
| `channel_server/tools/` | 新加 MCP tool `voice.issue_link` |
| agent soul/skills | fast-agent 加一条 "客户要电话" skill（~20 行 md） |

## 3. voice_bridge 进程结构

```
zchat-channel-server/src/voice_bridge/
├── __init__.py
├── __main__.py              # python -m voice_bridge --channel ... --port 8080
├── config.py                # ASR/TTS engine 选型 + 端口 + JWT secret
├── bridge.py                # 主类：CS WS client + 客户 WS server 双向 loop
├── ws_server.py             # 接客户浏览器连接，JWT 验签
├── session.py               # VoiceSession：一个客户连接 = 一个 session，N:1 挂 IRC channel
├── asr/
│   ├── base.py              # ASREngine 抽象：stream(audio_chunk) → partial/final text
│   ├── whisper_cpp.py       # local whisper.cpp 实现（CPU/GPU）
│   └── volcengine.py        # 字节跳动 streaming STT
├── tts/
│   ├── base.py              # TTSEngine 抽象：synthesize(text) → async iterator of audio chunks
│   ├── piper.py             # local piper TTS（快，中文质量一般）
│   └── edge_tts.py          # 微软 edge-tts（云，免费，中文好）
├── vad/
│   └── webrtc_vad.py        # 语音活动检测：检测客户说完
└── static/                  # web 前端
    ├── index.html           # /call 页面
    ├── call.js              # MediaRecorder + WebSocket + audio 播放
    └── call.css
```

### 3.1 一个 voice session 的生命周期

```
1. 浏览器加载 /call?t=<JWT>
2. call.js 发 WS connect → voice_bridge ws_server
3. voice_bridge 验签 JWT → 解 channel=#conv-001, customer_id=zhangsan
4. 创建 VoiceSession(id=uuid4(), channel="#conv-001", customer="zhangsan")
5. 如果这是该 channel 的第一个 voice session，voice_bridge 不做额外注册
   （CS 看 voice_bridge 作为单一 WS client，不按 session 颗粒度追踪）
6. browser getUserMedia → PCM 16kHz mono → opus encode → WS send 帧
7. voice_bridge ASR stream 输入 → 得到 partial text (每 200ms) + final text (停顿检测到)
8. final text → ws_messages.build_message(channel="#conv-001",
                                            source=f"voice-{customer_id}",
                                            content=final_text)
   → 发 CS → 广播回 IRC → agent 处理
9. agent 回复 __msg:<id>:...（IRC PRIVMSG）
   → CS 广播 → voice_bridge 收到 (channel 匹配)
   → TTS stream → WS audio 帧发回所有该 channel 上的活跃 session
10. 客户关 tab → WS 断 → session 清理
```

### 3.2 N:1 session → channel

- 同一个 channel 可以同时有多个 voice session（比如飞书群里 2 个客户同时点链接）
- voice_bridge 内存里：`{channel_id: [session1, session2, ...]}`
- 每个 session 独立 ASR pipeline（说话不串）
- CS 回复广播到该 channel 时，voice_bridge 给**所有**该 channel 的 session 做 TTS + 推音频
- TTS 流可以**复用**（同一文本，同一声音 → 合成一次，多路推送），省算力

## 4. 延迟预算

目标：客户说完一句 → 听到 agent 回复第一声 ≤ 800ms

| 阶段 | 目标 | 方案 |
|------|------|------|
| browser mic → voice_bridge | < 100ms | WebSocket opus 帧，局域网/公网均可 |
| VAD 检测停顿 | < 200ms | webrtcvad / silero-vad，200ms 静音触发 |
| ASR final decode | < 200ms | whisper.cpp small int8 / volcengine streaming |
| IRC round-trip (ws → irc → agent → irc → ws) | < 150ms | 本地进程，不是瓶颈 |
| agent 推理（fast-agent 用 Sonnet） | ??? | **瓶颈**：首 token 200-800ms，agent 完整回复可能 2-5s |
| TTS 首 chunk 生成 | < 150ms | piper / edge-tts streaming，首音频帧 100ms 内出 |
| voice_bridge → browser → 扬声器 | < 100ms | opus 解码 + Web Audio |

**关键优化**：agent 不等完整回复，**按 token 流 emit 到 IRC**，voice_bridge 按 token 增量 TTS。这需要：
- agent soul 改："对 voice channel，按句号/逗号 emit 中间 PRIVMSG（而不是憋完一整条消息）"
- MCP tool `reply_streaming(chunks)` 支持连续发多条 PRIVMSG 代表同一回复
- voice_bridge 对同一条 reply 的多个 chunk 累积 TTS，播完一段接下一段

**降级方案**：不开 streaming reply，完整消息到了再 TTS。端到端延迟变成 3-5s。仍比按住说话的异步语音好。

## 5. Standalone 独立测试（没飞书也能跑）

### 5.1 三级测试

| 级别 | 命令 | 需要的东西 | 作用 |
|------|------|-----------|------|
| **L0 ASR/TTS 自环** | `zchat voice test --loopback` | 只需 voice_bridge | 客户说啥 voice_bridge 就念啥，验证 ASR→TTS 链路 |
| **L1 agent 对话** | `zchat voice test --channel '#test-voice' --agent fast-agent` | voice_bridge + CS + 一个 agent | 完整对话，不挂飞书 |
| **L2 + 飞书 transcript** | 常规 `zchat up` + `zchat voice start` | 全家桶 | 生产形态 |

### 5.2 L1 命令行为

```bash
# 起 L1：
zchat voice test --channel '#test-voice' --agent fast-agent

# zchat 内部：
# 1. 确保 #test-voice 已经在 routing.toml（没有就临时 add_channel）
# 2. 起 fast-agent 加入 #test-voice（如果还没）
# 3. 起 voice_bridge（--dev-mode --channel '#test-voice'）
# 4. 给 dev-mode token 签一个（无 feishu 群链接步骤）
# 5. 打开浏览器到 http://localhost:8080/call?t=<devtoken>
#    用户直接说话，agent 回复 TTS

# 结束：
# Ctrl-C 杀 voice_bridge + 清 fast-agent（如果是 CLI 临时起的）
```

`--dev-mode` 下 voice_bridge 跳过 JWT 校验，接受 URL 里直接传 `?channel=` 参数。生产环境必须走 JWT。

### 5.3 独立测试的重要性

- 调 ASR/TTS 引擎选型时不用启飞书机器人
- CI 可以跑 L0 自环测试（录好的 audio 文件 → ASR → TTS → 比对输出音频）
- 客户端（浏览器 JS）单独迭代时不用后端依赖
- agent 开发可以在 L1 直接测语音交互，不干扰飞书生产环境

## 6. JWT Token 方案

### 6.1 签发方：MCP tool `voice.issue_link`

```python
# zchat-channel-server/src/channel_server/tools/voice.py
@tool
async def voice_issue_link(
    ctx: Context,
    customer_id: str = "",
    ttl_seconds: int = 180,
) -> dict:
    """Agent 触发：生成一个语音通话链接。

    Args:
      customer_id: 客户标识（飞书 open_id / 业务系统 uid）；为空则 'anon-<8hex>'
      ttl_seconds: 链接有效期，默认 3 分钟

    Returns:
      {"url": "...", "expires_at": <unix>}
    """
    channel = ctx.channel
    customer = customer_id or f"anon-{uuid4().hex[:8]}"
    exp = int(time.time()) + ttl_seconds
    token = jwt.encode({
        "channel": channel,
        "customer": customer,
        "exp": exp,
        "iat": int(time.time()),
        "nonce": secrets.token_urlsafe(8),
    }, settings.VOICE_JWT_SECRET, algorithm="HS256")
    return {
        "url": f"{settings.VOICE_PORTAL_URL}/call?t={token}",
        "expires_at": exp,
    }
```

### 6.2 校验方：voice_bridge WS server

```python
async def _handle_ws(self, ws, path):
    token = parse_query(path).get("t")
    if not token:
        if self.dev_mode:
            channel = parse_query(path).get("channel")
            customer = parse_query(path).get("customer", "dev-user")
            if not channel:
                return await ws.close(1008, "missing channel (dev mode)")
        else:
            return await ws.close(1008, "missing token")
    else:
        try:
            claims = jwt.decode(token, settings.VOICE_JWT_SECRET,
                                algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return await ws.close(1008, "token expired")
        except jwt.InvalidTokenError:
            return await ws.close(1008, "invalid token")
        channel = claims["channel"]
        customer = claims["customer"]
    session = VoiceSession(id=uuid4().hex, channel=channel, customer=customer)
    ...
```

### 6.3 安全

- JWT secret 放 `~/.zchat/voice-jwt.secret`（一次性 generated，写 config）
- MCP tool 校验 `ctx.channel` 来自 agent 自己的 channel（agent 不能给别的 channel 签 token）
- 链接 3 分钟有效 + nonce 防重放（voice_bridge 进程内记住最近 1h 的 nonce）
- 生产 TLS 必需（wss:// + https://）—— caddy 签 cert 挂前
- Rate limit：同一 IP 每分钟 ≤ 5 次连接尝试

## 7. ASR / TTS 选型（MVP 两档）

### 7.1 本地免费档（dev / 低成本生产）

```
ASR: whisper.cpp (ggml-small-q5_1.bin 中文)
     - 本地 CPU，M1 mac ~200ms/段
     - streaming 需 whisper-streaming wrapper
TTS: piper (中文 zh_CN-huayan-medium.onnx)
     - 本地 CPU，~50ms/帧
     - 质量一般但可接受
```

优点：零云成本，零外网依赖
缺点：中文口音强时识别率下降，TTS 自然度一般

### 7.2 云端高质量档（生产）

```
ASR: Volcengine 流式 ASR (火山引擎，字节)
     - 中文实时识别，支持标点
     - 延迟 ~100ms
     - 0.002元/秒
TTS: Volcengine 流式 TTS
     - 支持多发音人 + 情感调节
     - 延迟 ~80ms 首字节
     - 0.003元/秒
```

优点：中文体验好，低延迟
缺点：国内云依赖，成本 ~0.3元/分钟

### 7.3 极限档（未来）

```
OpenAI Realtime API (GPT-4o)
- LLM + ASR + TTS 一站式，<300ms 端到端
- 但替换掉了 zchat 的 agent 层，失去 IRC 总线 + 飞书双写
- 只适合纯 voice 场景，不适合 zchat 的 channel-centric 模型
```

不推荐，架构不符。

### 7.4 MVP 默认

**本地档（7.1）**，接口预留插件化（`asr_engine = "whisper_cpp"` / `"volcengine"`）。

## 8. MVP 切片

### Phase 1：L0 独立测试（1-2 天）

产出：
- voice_bridge 进程（`__main__.py`，能起 WS server 接客户）
- 最小 asr/tts 接口（whisper.cpp + piper）
- 静态网页 `/call`（MediaRecorder + WS + audio 播放）
- `zchat voice test --loopback` 命令

验收：`说什么听什么` 工作，延迟 < 1.5s

### Phase 2：L1 agent 对话（2-3 天）

产出：
- voice_bridge 连 CS (ws_messages.build_register, build_message)
- session → channel 映射
- 收 IRC 广播 → TTS → 推客户
- `zchat voice test --channel '#test' --agent fast-agent` 命令
- dev-mode token 绕过

验收：客户语音和 fast-agent 完整来回对话，延迟 < 3s（不含 agent 推理）

### Phase 3：JWT + MCP tool（1 天）

产出：
- MCP tool `voice.issue_link`
- JWT 验签生产模式
- fast-agent skill：`handle-voice-request`
- `zchat voice start` 生产启动命令

验收：飞书群测试 — agent 发链接，客户点开对话，飞书群看 transcript

### Phase 4：streaming reply 延迟优化（选做，2-3 天）

产出：
- agent soul 支持 token-level emit（voice channel 自动开启）
- voice_bridge 增量 TTS（收到第一句就开念）
- MCP tool `reply_streaming` 或扩展现有 `reply` 支持 `final=false` chunk

验收：端到端延迟 < 1s 到第一声

### Phase 5：barge-in（选做，2 天）

产出：
- VAD 检测客户开口 → 前端 cancel TTS 播放 → 发 `speech_start` 事件
- voice_bridge 收 speech_start 时给 CS 发 `__zchat_sys:user_barge_in` 事件
- agent 收到 barge_in → 停止当前 reply chunk emit

验收：agent 正在念，客户开口，agent 立刻停

## 9. 用户需决定

1. **Phase 1 是否先只做 L0（不连 CS 不起 agent）**，还是直接冲 Phase 2？
   - 我倾向先 L0，ASR/TTS 链路先跑通，避免 debug 链路交叉
2. **ASR/TTS 默认选本地还是云？** 本地免费但可能不够好；云好但要密钥+钱
   - 我倾向本地（7.1），不依赖外部服务
3. **Phase 4 和 5 是 MVP 的一部分还是 v2 再做？**
   - Phase 4 streaming 显著提升体验，值得做
   - Phase 5 barge-in 是 "phone call feel" 的关键，但实现代价高，v2 再做也可
4. **web 前端域**：用 `cs.inside.h2os.cloud` 子域还是公网域？
   - 我倾向：dev 用 localhost，生产用内网 + caddy，真客户场景才上公网

## 10. 与 cc-openclaw 的 trade-off 对照

| 维度 | cc-openclaw | zchat voice-bridge |
|------|-------------|-------------------|
| voice gateway 归属 | 独立外部进程，只定义 WS 协议 | voice_bridge 作为 zchat 内置 bridge |
| 路由模型 | actor (voice_session ↔ cc_session) | IRC channel + ws.broadcast |
| 多模态同步 | 需要显式 wire actor | 自动（同一 IRC channel 多个 bridge） |
| ASR/TTS 实现 | 完全由外部 gateway 决定 | zchat 自己提供 pluggable engine |
| 独立测试 | 要起 openclaw 全家桶 | L0/L1/L2 三级独立 |
| 飞书双写 | 通过 feishu_adapter wire actor | 免费（IRC 总线天然） |

**zchat 的优势**：IRC 总线让 voice / feishu / WeeChat 这些模态"自动对齐"，不需要 actor wiring；劣势：agent 必须在 IRC channel 里（符合现有设计）。

---

**下一步**：用户拍板 §9 的 4 个决定点，然后进 Phase 1 实现。
