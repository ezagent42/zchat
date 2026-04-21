# 已知限制与路线图

## 平台支持

| 平台 | 状态 | 说明 |
|------|------|------|
| macOS (Apple Silicon) | ✅ 已验证 | 主要开发和测试平台 |
| macOS (Intel) | ✅ 应支持 | Homebrew formula 包含 x86_64 二进制 |
| Linux (x86_64) / WSL2 | ⚠️ 未验证 | Homebrew (Linuxbrew) formula 已包含 Linux 支持，但未经测试 |
| Windows (原生) | ❌ 不支持 | tmux 无原生 Windows 支持，需通过 WSL2 使用 |

### Linux / WSL2 用户须知

zchat 的所有依赖（tmux、WeeChat、ergo、Claude Code、Python）均有 Linux 版本，理论上可通过 Linuxbrew 安装：

```bash
# WSL2 中安装 Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装 zchat（未验证）
brew tap ezagent42/zchat
brew install zchat
brew install ezagent42/zchat/ergo
```

如果你在 Linux/WSL2 上测试成功或遇到问题，请反馈到 [GitHub Issues](https://github.com/ezagent42/zchat/issues)。

## 已知限制

| 限制 | 影响 | 应对方案 |
|------|------|----------|
| Channel MCP 是 research preview | 必须使用 `--dangerously-load-development-channels` flag | 等待正式发布 |
| Claude Code 需要登录 | 不支持 API key 认证 | 使用 claude.ai 账号 |
| `--dangerously-skip-permissions` | Claude 无需确认即可执行文件操作 | 仅在信任环境使用 |
| IRC server 必须运行 | 所有通信经由本地 IRC server | `zchat irc daemon start` 自动启动 |
| 无跨 session 历史 | 重启后消息丢失 | WeeChat logger 自动保存本地 |

## 路线图

- **Agent 间通信** — Agent 通过 IRC private message 直接协作
- **飞书桥接** — 飞书作为 IRC 桥接节点
- **Ed25519 签名** — 消息签名验证，防止冒充
- **Web UI** — 通过 WeeChat relay API 暴露 Web 前端
- **Linux 验证** — 完成 Linux/WSL2 平台测试
