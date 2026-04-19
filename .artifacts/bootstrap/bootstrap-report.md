# Bootstrap Report: zchat CLI

Generated: 2026-04-17 | Version: 0.3.1.dev27

## Project Overview

- **zchat CLI**: 多 agent 协作管理工具，通过 IRC 协议连接 Claude Code agents
- **源码**: 21 个模块文件, 4120 行
- **测试**: 28 个 unit test 文件, 307 个测试用例
- **模板**: 7 个 agent 模板 (claude, fast-agent, deep-agent, admin-agent, squad-agent, deep-thinking, fast-response)
- **CLI 框架**: Typer (Click-based)

## Test Baseline

| 指标 | 值 |
|------|-----|
| Unit tests | 307/307 passed (0 failed, 0 skipped) |
| Duration | 14.62s |
| Test files | 28 |
| Coverage | 所有 CLI 模块都有对应测试文件 |

## Module Summary

| 模块 | 路径 | 行数 | 测试数 | 描述 |
|------|------|------|--------|------|
| app | zchat/cli/app.py | 1503 | 63 | 主 CLI：Typer 命令树，40+ 子命令 |
| agent_manager | zchat/cli/agent_manager.py | 404 | 19 | Agent 生命周期：创建/停止/重启/发送 |
| irc_manager | zchat/cli/irc_manager.py | 358 | 19 | IRC daemon (ergo) + WeeChat 管理 |
| auth | zchat/cli/auth.py | 272 | 15 | OIDC 认证：device code flow + token 管理 |
| runner | zchat/cli/runner.py | 233 | 18 | Runner 解析：全局配置 + 模板目录合并 |
| doctor | zchat/cli/doctor.py | 228 | 10 | 环境诊断 + 组件安装 |
| project | zchat/cli/project.py | 206 | 20 | 项目管理：创建/列表/使用/删除 |
| zellij | zchat/cli/zellij.py | 186 | 16 | Zellij CLI 封装（tab/pane/session 操作） |
| update | zchat/cli/update.py | 176 | 20 | 自动更新检查 + 升级逻辑 |
| paths | zchat/cli/paths.py | 159 | 17 | 集中路径解析（env > config > defaults） |
| **routing** | zchat/cli/routing.py | 125 | 18 | **V4 新增** routing.toml 读写 API |
| migrate | zchat/cli/migrate.py | 114 | 4 | tmux → Zellij 配置迁移 |
| template_loader | zchat/cli/template_loader.py | 111 | 7 | 模板加载/渲染/列表 |
| ergo_auth_script | zchat/cli/ergo_auth_script.py | 108 | 4 | ergo SASL auth-script（OIDC 验证） |
| config_cmd | zchat/cli/config_cmd.py | 107 | 10 | 全局配置管理（~/.zchat/config.toml） |
| layout | zchat/cli/layout.py | 100 | 9 | Zellij KDL layout 生成 |
| defaults | zchat/cli/defaults.py | 34 | 6 | 内置默认配置加载 |

## V4 Changes (vs previous bootstrap)

### 新增模块
- **routing.py** (125 行): config.toml/routing.toml 分离，动态频道-agent 映射
  - `add_channel`, `list_channels`, `channel_exists`, `join_agent`, `remove_channel`
  - 18 个测试覆盖 (`test_routing_cli.py`)

### 新增 CLI 命令
- `zchat channel create` — 注册 channel 到 routing.toml
- `zchat channel list` — 列出已注册 channel
- `zchat agent join` — 将 agent 添加到 channel（更新 state + routing）
- `zchat agent create --channel` — 创建 agent 时自动注册到 routing.toml

### 新增模板
- fast-agent, deep-agent, admin-agent, squad-agent (V4 新增)
- 原有: claude, deep-thinking, fast-response

### 测试改进
- 测试总数: 236 → 307 (+71 tests, +30%)
- 之前失败的 `test_unreachable_server_raises` 已修复 (0 failures)
- 新增测试文件: `test_routing_cli.py` (18 tests), `test_channel_cmd.py` (21 tests)

### 配置格式变更
- 项目配置拒绝旧格式（`[irc]`/`[tmux]` 段），要求重建
- `default_type` → `default_runner` 重命名
- `[channel_server]` 段新增 bridge_port, plugins_dir, timers, participants

## Environment

| 组件 | 版本 |
|------|------|
| Python | 3.13.5 |
| uv | 0.7.15 |
| CLI framework | Typer |
| Platform | Linux 6.6.87.2-microsoft-standard-WSL2 |

### 外部依赖
- **必需**: uv, python3, zellij, claude, zchat-channel-server
- **可选**: ergo (本地 IRC server, E2E only), weechat (IRC client)

### 子模块
- `zchat-protocol/` — 协议规范 (git submodule)
- `zchat-channel-server/` — MCP server (git submodule)

## Artifact Registry

| 文件 | 说明 |
|------|------|
| `.artifacts/bootstrap/manifest.json` | 文件清单 + 统计 |
| `.artifacts/bootstrap/env-report.json` | 环境 + 依赖 |
| `.artifacts/bootstrap/test-baseline.json` | 测试基线 (307 passed) |
| `.artifacts/bootstrap/module-reports/*.json` | 17 个模块报告 + tests.json |
| `.artifacts/bootstrap/bootstrap-report.md` | 本报告 |
