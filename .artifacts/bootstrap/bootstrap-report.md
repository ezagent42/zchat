# Bootstrap Report · zchat (main)

> Skill 0 · project-builder · 2026-04-21 V6 finalize 后重跑

## 环境

- Python 3.13.5, uv 已 ready
- ergo, zellij, jq 三件套已 ready
- 测试基线: 325 unit passed / 0 failed

## 项目

- 源文件 389 个，Python 118 个覆盖 117（99.2%）
- 仅 `.gitkeep` 占位文件未分析

## 11 模块

1. **app** — Typer CLI 根 + 所有子命令
2. **agent_manager** — Agent lifecycle（create/stop/restart/send）+ ready marker + auto-confirm watcher（phase 7 加新 Claude Code prompt 模式）
3. **irc_manager** — ergo daemon + WeeChat zellij tab + SASL auth injection
4. **project** — project CRUD + paths + defaults + global config
5. **routing** — routing.toml V6 schema read/write（bot + channel + entry_agent；agents 字段已删）
6. **zellij** — zellij subprocess 封装 + KDL layout
7. **auth** — OIDC device-code + ergo_auth_script
8. **runner** — template resolution + env 渲染
9. **doctor_update** — 诊断 + 自更新 + audit.json 读取
10. **templates** — 5 个 agent template（claude/fast/deep/admin/squad），fast/deep/admin/squad 各带 CLAUDE.md + skills/
11. **tests** — 3 层测试（unit/e2e/pre_release）

## 决策 & 跳过

- E2E `tests/e2e -m e2e` 在 collect 阶段因 env spin-up 慢被 5 分钟 timeout 中断。建议 CI `--timeout 600`。
- Pre-release walkthrough 非自动化，用户真机验收已过（见 `e2e-reports/report-v6-finalize-001.md`）。

## 历史 artifacts 清理

- V3/V4/V5 eval-docs / test-plans / code-diffs / test-diffs → 已删
- 保留 V6 finalize evidence: eval-doc-012 + code-diff-v6-finalize-phase{1-7} + e2e-report-v6-finalize-001
- registry.json 重建 version=2

## 下一步

- Stage 4: 修 CS 4 个 E2E（CSAT + help_request lifecycle V6 refactor 后未同步）
- Stage 5: 3 遍 ralph-loop 稳定态

---

## 2026-04-22 补录：Skill 1 regeneration (Step 7+8)

**触发**：发现 `ff0c8d7` 只执行了 Step 1-6（.artifacts/ 重生），**未执行 Step 7**（SKILL.md 未刷新，仍为 2026-04-10 pre-V6 版本，列 15 modules + V5 模块名 paths/runner/template_loader/migrate/update）。

**本次补录**执行 Step 7+8：

- `.claude/skills/project-discussion-zchat/SKILL.md` → 基于 `.artifacts/bootstrap/module-reports/` 11 个 V6 模块重写
- `.claude/skills/project-discussion-zchat/references/module-details.md` → 从 module-reports 聚合生成
- `.claude/skills/project-discussion-zchat/scripts/` 整理：
  - 删除 10 个 V5 残余 (test-agent/config/defaults/ergo-auth/irc/layout/migrate/paths/template/update)
  - 新增 6 个 V6 per-module (test-agent_manager/doctor_update/irc_manager/routing/templates/pre-release)
  - 修正 4 个 (test-app/runner/project/zellij 扩展至完整 V6 文件集，test-auth 补 test_ergo_auth_script.py)
  - 保留 5 个 aggregate (test-e2e/channel-server/protocol/unit-all + self-test/refresh-index/close-issue)

**Step 8 自验证基线比对**（11/11 ✅）：

| test-runner | 基线 | 验证 | 匹配 |
|---|---|---|---|
| test-agent_manager.sh | 25 | 25 passed | ✅ |
| test-app.sh | 52 | 52 passed | ✅ |
| test-auth.sh | 19 | 19 passed | ✅ |
| test-doctor_update.sh | 43 | 43 passed | ✅ |
| test-irc_manager.sh | 32 | 32 passed | ✅ |
| test-project.sh | 65 | 65 passed | ✅ |
| test-routing.sh | 67 | 67 passed | ✅ |
| test-runner.sh | 11 | 11 passed | ✅ |
| test-templates.sh | 11 | 11 passed | ✅ |
| test-zellij.sh | 31 | 31 passed | ✅ |
| test-unit-all.sh | 304 | 304 passed | ✅ |

**覆盖矩阵**：`.artifacts/coverage/coverage-matrix.md` 加 YAML frontmatter 以通过 verify-bootstrap.sh。
