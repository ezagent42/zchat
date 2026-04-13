# 测试文件分布

> 分析日期：2026-04-09

## 目录结构

```
tests/
├── unit/                          # 单元测试（18 文件，100+ cases）
│   ├── test_agent_focus_hide.py
│   ├── test_agent_manager.py
│   ├── test_auth.py
│   ├── test_config_cmd.py
│   ├── test_defaults.py
│   ├── test_ergo_auth_script.py
│   ├── test_irc_check.py
│   ├── test_layout.py
│   ├── test_list_commands.py
│   ├── test_migrate.py
│   ├── test_paths.py
│   ├── test_plugin_integration.py
│   ├── test_project.py
│   ├── test_project_create_params.py
│   ├── test_runner.py
│   ├── test_template_loader.py
│   ├── test_update.py
│   └── test_zellij_helpers.py
│
├── integration/                   # 集成测试（仅 placeholder）
│   └── conftest.py
│
├── e2e/                           # E2E 测试（2 文件，13 test functions）
│   ├── conftest.py                # 核心 fixtures
│   ├── e2e-setup.sh               # 手动 E2E 环境脚本
│   ├── test_e2e.py                # 9 阶段端到端测试
│   └── test_zellij_lifecycle.py   # Zellij tab 生命周期
│
├── pre_release/                   # 预发布验收（8 模块，50+ cases）
│   ├── conftest.py                # 预发布 fixtures
│   ├── run.sh                     # 执行脚本
│   ├── walkthrough.sh             # asciinema 录制主脚本
│   ├── walkthrough-steps.sh       # 录制中执行的步骤
│   ├── test_00_doctor.py
│   ├── test_01_project.py
│   ├── test_02_template.py
│   ├── test_03_irc.py
│   ├── test_04_agent.py
│   ├── test_04a_irc_chat.py
│   ├── test_04b_remote_irc.py
│   ├── test_05_setup.py
│   ├── test_06_auth.py            # manual 标记
│   ├── test_07_self_update.py     # manual 标记
│   └── test_08_shutdown.py
│
└── shared/                        # 共享测试工具
    ├── cli_runner.py              # CLI 执行封装
    ├── irc_probe.py               # IRC 探针客户端
    ├── tmux_helpers.py            # tmux 操作辅助（旧版）
    └── zellij_helpers.py          # Zellij 操作辅助（新版）
```

## 子模块测试

```
zchat-channel-server/tests/
└── test_channel_server.py         # mention 检测、消息分片、系统消息、指令加载

zchat-protocol/tests/
├── test_sys_messages.py           # 系统消息编解码
└── test_naming.py                 # scoped_name 命名规则
```

## 测试相关文档

```
docs/
├── dev/testing.md                 # 测试架构概述
├── e2e-manual-test.md             # 手动 E2E 指南
└── discuss/
    ├── e2e-log/                   # E2E 测试执行记录
    │   └── 2026-04-08-quickstart-test.md
    └── test-status/               # 本分析报告
```

## 配置文件

| 文件 | 内容 |
|------|------|
| `pytest.ini` | testpaths、markers（integration/e2e/prerelease/manual/order）、asyncio_mode=auto |
| `pyproject.toml [dependency-groups.dev]` | pytest, pytest-asyncio, pytest-order, pytest-timeout |
| `Makefile` | `test`（unit）、`test-e2e`（e2e）快捷命令 |
| `.github/workflows/test.yml` | CI 只跑 unit tests（macOS） |

## 统计

| 分类 | 文件数 | 测试用例数 | 外部依赖 |
|------|--------|-----------|----------|
| 单元测试 | 18 | 100+ | 无 |
| 集成测试 | 1 (placeholder) | 0 | ergo |
| E2E 测试 | 2 | 13 | ergo + Zellij |
| 预发布测试 | 8 模块 | 50+ | ergo + Zellij + WeeChat + Claude |
| Channel-server | 1 | 10 | 无 |
| Protocol | 2 | 10 | 无 |
| **合计** | **32** | **170+** | — |
