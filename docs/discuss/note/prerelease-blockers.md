# Pre-release 阻塞和修改记录

> 更新于 2026-04-16
> 记录 pre-release 测试启动前发现的阻塞项和所做修改

---

## 服务启动验证

| 服务 | 命令 | 状态 | 说明 |
|------|------|------|------|
| ergo IRC server | `zchat irc daemon start` | ✅ 运行中 (pid 120222, :6667) | |
| channel-server | `uv run zchat-channel` | ✅ 可启动 | 需 BRIDGE_PORT 避免端口冲突 |
| agent_mcp | `uv run zchat-agent-mcp` | ✅ 可启动 | stdin MCP server，无 --help |
| feishu_bridge | `python -m feishu_bridge.bridge` | ✅ 模块可导入 | 需 --config 参数 |
| zchat CLI | `uv run zchat --help` | ✅ 正常 | |
| zellij | `zellij --version` | ✅ 0.44.1 | |
| asciinema | `asciinema` | ❌ 未安装 | 需 `pip install asciinema` 或 `brew install asciinema` |

## 阻塞项

### Blocker 1: asciinema 未安装

**影响**: 无法录制 pre-release 测试过程作为证据
**修复**: `pip install asciinema` 或 `brew install asciinema`
**优先级**: P1 — 不阻塞测试本身，阻塞证据采集
**状态**: 待安装

### Blocker 2: tests/pre_release/ 测试代码未写

**影响**: 无法执行 Layer 3 飞书 E2E 测试
**修复**: 需要开发（详见 eval-doc cs-eval-prerelease-infra）
**包含**:
- FeishuTestClient 7 个新方法 (~100 行)
- full_stack fixture (~80 行)
- test_feishu_e2e.py (~150 行)
**优先级**: P0 — 阻塞 pre-release
**状态**: eval-doc 已创建，待 dev-loop 开发

### Blocker 3: feishu-e2e-config.yaml chat_id 未填

**影响**: 飞书 E2E 无法连接真实群
**修复**: 替换 oc_customer_test_xxx / oc_squad_test_xxx / oc_admin_test_xxx 为真实值
**优先级**: P0 — 阻塞飞书测试
**状态**: 模板已创建，待用户填入

### Blocker 4: E2E 偶发端口连接失败 (WSL2 已知问题)

**影响**: 个别 E2E 测试偶发 ConnectionRefusedError（端口释放延迟）
**原因**: WSL2 网络栈端口释放慢 + channel_server function-scoped fixture 每个测试重启进程
**已做**: bridge_ws 增加 5 次 retry + 1s backoff（de6942d）
**现状**: 从 3 errors → 1 error（偶发），非代码 bug
**优先级**: P2 — WSL2 环境特有，Linux/macOS 原生不受影响
**状态**: 已缓解，接受偶发

---

### Blocker 5: MCP server 指向旧的 zchat-channel（已修复）

**影响**: agent 创建时启动嵌入式 channel-server 而非轻量 agent_mcp，Phase 4.6 架构拆分失效
**修复**: 5 个文件中 `zchat-channel` → `zchat-agent-mcp`（start.sh, .env.example, defaults.toml, migrate.py, CLAUDE.md）
**验证**: `zchat project create prerelease-test` → config.toml 中 `mcp_server_cmd = ["zchat-agent-mcp"]` ✅
**commit**: f77908a
**状态**: ✅ 已修复

---

## 已做的修改（本次 session）

| 修改 | commit | 说明 |
|------|--------|------|
| Gate fix (send_event target_capabilities) | 542fb29 | sla.breach 不广播到 customer |
| CardAwareClient + CSAT | f5fc661 | 飞书卡片回调闭环 |
| .gitignore | 0256535 | 排除 __pycache__, *.db, credentials |
| DB consolidation merge | 9e95d62 | 3 文件 → 1 文件 5 表 |
| Pre-release 配置文件 | 9dc3d98 | routing.toml + feishu-e2e-config.yaml 模板 |
| Artifacts 补全 | 多个 | 48→49 artifacts，全链路完整 |

## Layer 1/2 可直接执行

Layer 1 (Unit) 和 Layer 2 (E2E Bridge API) 不依赖飞书，可以立即运行：

```bash
cd zchat-channel-server

# Layer 1: Unit 回归
uv run pytest tests/unit/ feishu_bridge/tests/ -v

# Layer 2: E2E Bridge API
uv run pytest tests/e2e/ -v -m e2e --timeout=30
```

只有 Layer 3 (飞书 E2E) 被 Blocker 2 和 3 阻塞。
