# 09 · 部署 — Caddy 反代 + 公网 callback + WSS 出站

## 1. 网络拓扑

```
                   Internet
                       │
           ┌───────────┼───────────┐
           ▼           ▼           ▼
      WeCom 客户   WeCom 长连接  WeCom 客服
     (浏览器/手机)  服务器       回调
           │           │           │
           ▼           │           │
    voice_bridge   wecom_bridge   wecom_bridge
    /ws (WSS)      botlink (WSS)  kefu (HTTPS)
           │       OUTBOUND       │
     caddy:443                    caddy:443
     反代到 :8787                  反代到 :8788
                                  /wecom/<bot>/callback
```

- **入站需要公网 HTTPS**：Kefu callback (POST /wecom/.../callback)
- **出站直连 WeCom**：botlink WSS / Kefu sync_msg / send_msg / webhook（不需要公网入站）
- **voice_bridge 已部署**：WSS /ws 复用同一个 caddy

## 2. Caddyfile 完整片段

加到 `~/.config/caddy/Caddyfile`：

```caddyfile
# WeCom Kefu callback — 公网入站
wecom-customer.inside.h2os.cloud {
    tls {
        dns alidns {
            access_key_id {env.ALICLOUD_ACCESS_KEY_ID}
            access_key_secret {env.ALICLOUD_ACCESS_KEY_SECRET}
        }
        resolvers 223.5.5.5 8.8.8.8
    }
    # 仅暴露 callback path，其他 404
    @callback path /wecom/callback /wecom/callback/*
    handle @callback {
        reverse_proxy 127.0.0.1:8788 {
            header_up Host {host}
            header_up X-Real-IP {remote}
        }
    }
    @health path /health
    handle @health {
        reverse_proxy 127.0.0.1:8788
    }
    handle {
        respond "Not Found" 404
    }
}

# admin / squad 也可以加（如果要公开 web 端口；通常 botlink WSS 出站不需要）
# 略
```

## 3. WeCom 后台配置（Kefu）

### 3.1 创建客服账号

1. 登录 [WeCom 管理后台](https://work.weixin.qq.com/wework_admin/)
2. **客户联系 → 微信客服 → 客服账号管理 → 添加**
3. 命名：例 "AI 客服-001"
4. 复制 `open_kfid`（形如 `wkXXXXXXXX`）→ 记到 credentials/customer-wecom.json

### 3.2 配置消息回调

1. **客户联系 → 微信客服 → 开发配置**
2. 接收消息 URL：`https://wecom-customer.inside.h2os.cloud/wecom/callback`
3. Token：`openssl rand -hex 16` 生成 → 填入 → 也写到 credentials
4. EncodingAESKey：点"随机生成" → 复制 → 写到 credentials
5. 保存：WeCom 立即 GET 验证 → wecom_bridge 必须已起好

### 3.3 自建应用（拿 corp_secret）

1. **应用管理 → 自建应用 → 创建应用**（如果尚未有）
2. 复制：corp_id（在"我的企业"页）+ AgentID + Secret
3. 应用权限：**管理客户联系** ✓（必须勾，Kefu API 才能用）

### 3.4 智能机器人（admin/squad 用）

1. **应用管理 → 智能机器人 → 创建机器人**
2. 复制 BotID + Secret
3. 在 WeCom 的内部 admin 群 / squad 群里 @ 此机器人 → 群成员邀请加入

## 4. 凭证文件示例

`~/.zchat/projects/prod/credentials/customer-wecom.json`:
```json
{
  "type": "wecom",
  "platform_role": "kefu",
  "corp_id": "ww123abcdef0123",
  "corp_secret": "xxxxxx",
  "agent_id": 1000002,
  "open_kfid": "wkXXXXXXXX",
  "callback_token": "RandomString32B",
  "encoding_aes_key": "43-char-base64"
}
```

`~/.zchat/projects/prod/credentials/admin-wecom.json`:
```json
{
  "type": "wecom",
  "platform_role": "botlink",
  "bot_id": "B0000001",
  "bot_secret": "yyyyyy"
}
```

文件权限 `chmod 600`。

## 5. 启动顺序

```bash
# 1. 同 dev: 起 cs / ergo / feishu_bridges (如有)
zchat up

# 2. wecom_bridge 已被 zchat up 自动起（routing.toml [bots.*-wecom] 探测）

# 3. caddy reload
caddy reload --config ~/.config/caddy/Caddyfile

# 4. WeCom 后台配置 callback URL → 触发 GET 验证
# log 看：[wecom-bridge.callback] URL verified ok

# 5. 在 WeCom 客户端找到客服 → 发"hi"
# log 看：[wecom-bridge.kefu] sync_msg pulled 1 message: text "hi"
```

## 6. 健康监控

每个 wecom_bridge 进程暴露 `/health`：

```bash
curl https://wecom-customer.inside.h2os.cloud/health
# → ok
```

Botlink driver 没有 HTTP 端口，但有 WSS 心跳 — 用 zellij tab log 看 `[botlink] heartbeat ok`。

加到 zchat doctor：
```bash
zchat doctor
# 检查输出：
#   wecom-customer (kefu): /health 200, callback URL reachable
#   wecom-admin (botlink): WSS connected, last heartbeat 5s ago
```

## 7. 端口规划（含 voice + 多 bot）

| 端口 | 服务 |
|---|---|
| 6667 | ergo IRC (内网)|
| 9999 | channel_server WS |
| 8787 | voice_bridge (caddy 反代)|
| 8788 | wecom_bridge customer-wecom (Kefu callback) |
| 8789 | wecom_bridge customer-wecom-2 (如有第二个 Kefu) |
| (内网无端口) | wecom_bridge admin-wecom (botlink WSS 出站) |
| (内网无端口) | wecom_bridge squad-wecom (botlink WSS 出站) |

## 8. 防火墙 / DNS

- 出站：必须能访问 `qyapi.weixin.qq.com` (api) 和 `openws.work.weixin.qq.com` (botlink WSS)
- 入站：caddy 已绑 80/443，inside.h2os.cloud DNS 加：
  - `A wecom-customer 100.64.0.27`
  - `A wecom-admin 100.64.0.27` (如需公开)
  - `A voice 100.64.0.27`

注：实际公网 IP 不一定是 100.64.x.x（那是 Tailscale / inside 域）— 视部署改

## 9. Rolling restart

WeCom Kefu 的 cursor 由 wecom_bridge 持久化（详见 02 §sync_msg），重启后从上次 cursor 继续 → 无消息丢失。

```bash
# 单独重启某个 wecom_bridge tab
zchat agent restart customer-wecom   # 不对，这是 agent 的命令
# 应该用：
pkill -f "wecom_bridge.*--bot customer-wecom"
# 等 zellij tab 自重启 (start.sh 退出后 zellij 不会自动重起 — 需要 zchat up --only bridges)
```

或者更简单：`zchat shutdown && zchat up`。

## 10. 灾难恢复

| 故障 | 影响 | 自动恢复 | 手动操作 |
|---|---|---|---|
| Caddy 挂 | Kefu callback 收不到 → WeCom 重试 3 次后丢消息 | systemd 重启 | 检查 caddy log |
| wecom_bridge customer 挂 | callback 收到 200 但无消息处理 | systemd 重启 | 看 cursor 是否恢复 |
| WeCom API 5xx | 暂时发不出 | retry with backoff (sender 内置) | 看 errcode log |
| corp_secret 泄露 | 别人能假冒应用 | — | WeCom 后台 rotate secret，所有 wecom_bridge 重启 |
| EncodingAESKey 泄露 | 别人能解密 callback | — | 同上 + 改 callback Token |

## 11. 跟现有 ergo + caddy + voice 共存检查

- ✅ ergo 不动（IRC 6667 不冲突）
- ✅ caddy 加 site，老 site 不影响
- ✅ voice_bridge 端口（8787）跟 wecom (8788+) 不冲突
- ✅ feishu_bridge 跟 wecom_bridge 共存（routing.toml 多 bot）
