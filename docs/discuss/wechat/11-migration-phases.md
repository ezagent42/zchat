# 11 · 实施 Phase + 风险 + Rollback

## 1. Phase 切片（建议串行，每片可独立 PR + 回退）

### Phase 0 · 共享层抽取（1 天）

把 `feishu_bridge` 中跟 IM 平台无关的部分挪到 `src/_im_bridge_shared/`：
- `bridge_api_client.py`（CS WS 通信）
- `routing_reader.py`

feishu_bridge 改 import 路径，`tests/` 跟着改。

**验收**：`uv run pytest tests/unit/test_feishu_*` 全过。
**回退**：单 git revert。

### Phase 1 · wecom_bridge skeleton（2 天）

新建 `src/wecom_bridge/` 目录树（参见 01 §3）。空实现 + entry point + routing 解析：
- `__main__.py` 能 `python -m wecom_bridge --bot <name>` 启动
- `config.py` build_config_from_routing 验证
- `routing_reader.py` 复用共享层
- `pyproject.toml` 加 entry_points: `zchat-wecom-bridge = "wecom_bridge.__main__:main"`
- `pyproject.toml` 加依赖：`wechatpy[cryptography]>=1.8` 或 `httpx + cryptography`（看 03 决策）

**验收**：起进程不崩，log "wecom_bridge ready (no driver yet)"。
**回退**：删整个 `src/wecom_bridge/`。

### Phase 2 · Kefu driver MVP（5 天）

最复杂，分子 phase：

**2a. callback HTTPS server**（1 天）
- `drivers/kefu/callback.py` aiohttp server
- 实现 GET 验签 + POST 解密
- 单元测试 mock crypto

**2b. sync_msg pull**（1 天）
- `drivers/kefu/sync_msg.py` 用 cursor + has_more 循环
- token 持久化到 `~/.zchat/projects/<proj>/.wecom-bridge-<bot>/cursor.json`

**2c. send_msg**（1 天）
- `drivers/kefu/send_msg.py` text/image/menu/link
- retry + token refresh

**2d. message_parsers + outbound 路由**（1 天）
- 接 callback → sync_msg → parse → ws_messages.build_message → CS WS

**2e. lazy_create + enter_session**（1 天）
- 收 enter_session event → _lazy_create_channel_and_agent

**验收**：真 WeCom 客服收消息，IRC 看到 PRIVMSG，agent 回复，客户在微信收到。
**回退**：禁用 routing.toml `[bots.*-wecom]` 段 → 老飞书继续用。

### Phase 3 · Botlink driver（3 天）

**3a. WSS client**（2 天）
- `drivers/botlink/ws_client.py` 连 wss://openws.work.weixin.qq.com
- 心跳 + 断线重连
- 加密 / 鉴权（如果有；查 path/101463）

**3b. send + parser**（1 天）
- text/markdown/template_card 发送
- 接收 WSS frame → ws_messages

**验收**：admin / squad 内部群 @ bot 能收到，回复进 IRC #admin。
**回退**：删 `drivers/botlink/`，admin/squad 暂时仍用 feishu。

### Phase 4 · supervise + CSAT 集成（2 天）

- supervise: squad bridge 接 customer 的 ws_messages → 发 markdown 到 squad 内部群（含 `[conv-X]` 前缀）
- operator 在 squad 群打 `[conv-X] xxx` → 翻译成 IRC __side
- CSAT msgmenu 实现 + click event 解析 → audit plugin

**验收**：完整 supervise + CSAT 流程跑通（10 §5.3 §5.4）。
**回退**：禁用 squad-wecom，仍用 squad-feishu。

### Phase 5 · cli 集成 + 文档（1 天）

- `zchat bot add --type wecom --platform-role kefu/botlink/webhook`
- `zchat doctor` 加 wecom 检查（cred 文件 / callback URL 可达 / token 有效）
- `docs/guide/008-wecom-setup.md` 用户接入指南
- `zchat up --only bridges` 同时起 feishu + wecom

**验收**：管理员从零按 008 指南 90min 内 onboard 完成。
**回退**：cli 改动是 typer option 加法，向后兼容。

### Phase 6 · 上线试点（1 周）

- 选 1 个真实商户做 alpha：迁 1 个客户对话 channel 到 WeCom
- 监控指标：消息延迟 / 失败率 / CSAT
- 收集 operator 反馈

**验收**：1 周稳定运行，CSAT ≥ 4.0（飞书是 4.5+，WeCom 因平台限制略降可接受）。
**回退**：对应 channel routing.toml 改回 feishu bot。

---

## 2. 时间总估

| Phase | 工作日 |
|---|---|
| 0 共享层 | 1 |
| 1 skeleton | 2 |
| 2 Kefu | 5 |
| 3 Botlink | 3 |
| 4 supervise + CSAT | 2 |
| 5 cli 集成 + docs | 1 |
| **代码完工** | **14 工作日 (~3 周)** |
| 6 试点 | 5 工作日（calendar）|
| **完整上线** | **~4 周** |

## 3. 风险清单 + 缓解

| # | 风险 | 影响 | 概率 | 缓解 |
|---|---|---|---|---|
| 1 | WeCom 后台审批慢（自建应用 / 客服账号申请）| 阻塞 Phase 2 | 中 | 提前一周申请；代理用商户的账号 |
| 2 | callback URL 公网可达不稳（DNS / TLS / 防火墙）| Kefu 收不到消息 | 中 | Phase 2a 第一天验通；caddy 实测 |
| 3 | Kefu sync_msg 频率受限超额 | 高峰期消息延迟 | 中 | 实现 token-based 限频解放 + 队列化 |
| 4 | smart bot WSS SDK Python 版本不稳 | Botlink 不可用 | 中 | 用底层 WSS 客户端自实现（备选）|
| 5 | template_card 不能 update 的 UX 退化 operator 不接受 | 商户拒绝 | 高 | 提前 trade-off review；用 markdown 卡 + debounce 折中 |
| 6 | corp_secret 频繁过期 / 被泄露 | 服务中断 | 低 | rotate 流程文档化 + alert |
| 7 | 客户在 Kefu 发 WeCom 不支持的类型（投票 / 红包） | bot 装聋作哑 | 中 | 1 min 没收到响应 → bot 主动 nudge "目前仅支持文本 / 图片..." |
| 8 | 飞书与 WeCom 路径行为不一致 → agent 困惑 | 回复质量降 | 低 | agent 不知 IM 平台，所有差异在 bridge 层吞掉 |
| 9 | 共享 IRC bot nick 跟 WeCom 客户冲突 | 命名碰撞 | 极低 | scoped_name 已防（{username}-{short}）|
| 10 | 飞书 + WeCom 同时跑两份 audit 同 conv | 数据重复 | 低 | conv channel name 不同（feishu-conv-001 vs wecom-conv-001）|

## 4. 不可逆操作

- **WeCom 后台 EncodingAESKey 改了** → 所有 bridge 重启 + credentials/*.json 改 + caddy 不变
- **corp_secret rotate** → 需所有用此 corp_id 的 bridge 一起重启
- **客服账号删除** → 此 open_kfid 历史会话丢，重建新 open_kfid 后客户重新接入

## 5. Rollback 策略

| 何时 rollback | 怎么做 |
|---|---|
| Phase 0/1 skeleton 没工作 | 直接 git revert PR |
| Phase 2 Kefu 不稳 | routing.toml 删 `[bots.*-wecom-kefu]`，飞书继续 |
| Phase 3 Botlink WSS 频繁断 | admin/squad 临时回退到飞书 |
| Phase 4 supervise UX 不行 | 客户对话仍走 WeCom，supervise 临时回飞书（双客服并存）|
| Phase 6 alpha 商户拒绝 | 商户重回飞书 + 总结复盘 → 决定要不要 v2 |

## 6. 决策清单（开工前用户拍板）

1. ☐ 商户能接受"客户对话从群改 1-1 客服"形态吗？
2. ☐ 商户能接受"卡片不能 update，看到两条消息"的 UX？
3. ☐ operator 能学会"squad 群 [conv-X] 前缀指令"约定？
4. ☐ 选 wechatpy SDK 还是自建 httpx + cryptography？（推荐 wechatpy MVP，自建为后续优化）
5. ☐ 一个企业部署一个 corp_id（一套 token）还是多个？（推荐一个，多个 bot 共享 corp）
6. ☐ 是否同时维护飞书 + WeCom（双平台）还是切换？（推荐共存 6 月再决定弃哪个）

## 7. 验收 / 关闭标准

完整迁移项目"完成"判定：

- [x] 所有 unit test 通过 (250+ 测试)
- [x] 真机 WeCom 客户对话 + supervise + CSAT 三套链路稳定运行 1 周
- [x] 文档 docs/guide/008-wecom-setup.md 让管理员能独立 onboard
- [x] 至少 1 个真实商户在生产环境用 WeCom bridge ≥ 30 天，CSAT ≥ 4.0，无平台级故障
- [x] feishu_bridge 仍可用且无回归
- [x] CI green（feishu + wecom 测试全过）
