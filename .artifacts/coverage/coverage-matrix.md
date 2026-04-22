---
type: coverage-matrix
producer: skill-0-project-builder
project: zchat
generated_at: "2026-04-21"
status: current
---

# Coverage Matrix · zchat (main repo)

> Bootstrap 于 2026-04-21，基于 Skill 0 (project-builder) 产出。

## 1. 代码测试覆盖

| Module | Source | Tests | 覆盖状态 |
|---|---|---|---|
| app | `zchat/cli/app.py` (~1800 行) | `tests/unit/test_channel_cmd.py`, `test_agent_commands.py` 等 | ✅ 主命令路径 |
| agent_manager | `zchat/cli/agent_manager.py` | `tests/unit/test_agent_manager*.py` | ✅ lifecycle + auto-confirm |
| irc_manager | `zchat/cli/irc_manager.py` | `tests/unit/test_irc_*.py` | ✅ ergo/WeeChat 启停 |
| project | `zchat/cli/project.py` 等 | `tests/unit/test_project*.py` | ✅ CRUD + migrate |
| routing | `zchat/cli/routing.py` | `tests/unit/test_routing_cli.py` | ✅ V6 schema (bot/channel) |
| zellij | `zchat/cli/zellij.py` + `layout.py` | `tests/unit/test_zellij*.py` | ✅ session/tab |
| auth | `zchat/cli/auth.py` + `ergo_auth_script.py` | `tests/unit/test_auth*.py` | ✅ OIDC + SASL |
| runner | `zchat/cli/runner.py` + `template_loader.py` | `tests/unit/test_runner*.py` | ✅ 环境渲染 |
| doctor_update | `zchat/cli/doctor.py` + `update.py` + `audit.py` | `tests/unit/test_doctor*.py` | ✅ 诊断 + 自更新 |
| templates | `zchat/cli/templates/` (4 PRD agent + claude) | 跨 template integration tests | ⚠️ 主要靠 agent 运行时验证，无直接 unit |
| tests | 自指 | — | — |

**单元测试基线**: 325 passed / 0 failed。

## 2. 操作 E2E 覆盖

E2E 测试 (tests/e2e/) 由 `pytest -m e2e` 触发：
- 依赖 ergo IRC server + uv (hard deps, 已 ready)
- 依赖 zellij (hard dep, 已 ready)

**本次运行**: 超时被中断（collect 或 prewarm 阶段环境 spin-up 时间 > 5m 默认 timeout）。
建议 CI：`pytest tests/e2e -m e2e --timeout 600`。

## 3. Pre-release 覆盖

`tests/pre_release/walkthrough.sh` asciinema 录制（manual）。
最新真机跑为 V6 finalize: 见 `.artifacts/e2e-reports/report-v6-finalize-001.md`，PRD TC-PR-2.1 至 TC-PR-CSAT/RoutingDynamic/LazyCreate A-D 全过。

## 4. 架构红线

- core (`channel_server/` + `zchat-protocol/`) 0 业务名命中
- `feishu_bridge/` + `templates/` 允许业务语义（业务/用户面层）
- 见 `.artifacts/code-diffs/code-diff-v6-finalize-phase4.md` §业务术语红线

## 5. 已知缺口

- E2E timeout 需要 CI 提高 timeout（非代码问题）
- templates 目录没有直接 unit test（agent 行为靠 PRD 真机验证）
- `zchat/cli/data/plugins/.gitkeep` 占位文件，不影响

## 历史

- Bootstrap 2026-04-17 (V4 时期) → 已清理
- Bootstrap 2026-04-21 (V6 finalize 后) → 本报告
