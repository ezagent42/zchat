#!/usr/bin/env python3
"""Dev-Loop Skills E2E 自动化测试脚本。

通过 claude -p (pipe mode) 无头运行每个 skill，然后用 verify-skill-output.sh
验证磁盘产出。基于 skill-creator 的 eval 模式。

用法:
    uv run python3 docs/discuss/skill-dev/run-skill-e2e.py [--skill N] [--timeout 300] [--dry-run]
    uv run python3 docs/discuss/skill-dev/run-skill-e2e.py --skill 6  # 只测 Skill 6
    uv run python3 docs/discuss/skill-dev/run-skill-e2e.py --all      # 按顺序跑全部
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path("/home/yaosh/projects/zchat")
ARTIFACTS_DIR = PROJECT_ROOT / ".artifacts"
VERIFY_SCRIPT = PROJECT_ROOT / "docs/discuss/skill-dev/verify-skill-output.sh"
REPORT_DIR = PROJECT_ROOT / "docs/discuss/skill-dev/e2e-report"

# --- 数据结构 ---


@dataclass
class Assertion:
    """单个断言。"""

    description: str
    check: str  # "contains", "regex", "file_exists", "verify_script", "command"
    value: str
    passed: bool | None = None
    evidence: str = ""


@dataclass
class TestCase:
    """单个测试用例。"""

    skill: int
    function: int
    name: str
    prompt: str
    assertions: list[Assertion] = field(default_factory=list)
    setup_commands: list[str] = field(default_factory=list)
    cleanup_commands: list[str] = field(default_factory=list)
    timeout: int = 300
    # 结果
    status: str = "pending"  # pending, running, passed, failed, error, skipped
    output: str = ""
    duration: float = 0.0
    error_msg: str = ""


# --- 测试用例定义 ---


def _reg(script_dir: str = "/home/yaosh/.claude/skills/artifact-registry/scripts") -> str:
    """返回 registry 脚本的基础路径。"""
    return script_dir


REG = _reg()


def build_test_cases() -> list[TestCase]:
    """构建所有 skill 的全部功能测试用例 (33 个)。"""
    cases = []

    # ================================================================
    # Skill 6: artifact-registry (5 功能)
    # ================================================================

    cases.append(TestCase(
        skill=6, function=1, name="init-artifact-space",
        prompt=(
            '使用 artifact-registry skill，在 /tmp/test-e2e-init 初始化 artifact space。'
            '先运行 mkdir -p /tmp/test-e2e-init && cd /tmp/test-e2e-init && git init，'
            '然后运行 init-artifact-space.sh --project-root /tmp/test-e2e-init。'
            '最后展示创建的目录结构和 registry.json 内容。'
        ),
        assertions=[
            Assertion("提到 registry.json", "contains", "registry.json"),
            Assertion("提到 artifacts 目录", "regex", r"(eval-docs|test-plans|e2e-reports)"),
        ],
        cleanup_commands=["rm -rf /tmp/test-e2e-init"],
        timeout=120,
    ))

    cases.append(TestCase(
        skill=6, function=2, name="register",
        prompt=(
            '使用 artifact-registry skill，运行 query.sh --project-root /home/yaosh/projects/zchat --summary '
            '展示当前已注册的 artifact 列表，然后说明 register.sh 的参数格式。'
        ),
        assertions=[
            Assertion("展示了 registry 内容", "regex", r"(coverage-matrix|eval-doc|artifact)"),
            Assertion("提到 register 参数", "regex", r"(--type|--name|--producer|--path|--status)"),
        ],
        timeout=120,
    ))

    cases.append(TestCase(
        skill=6, function=3, name="query",
        prompt=(
            '使用 artifact-registry skill，执行以下查询并展示结果：\n'
            '1. query.sh --project-root /home/yaosh/projects/zchat --type coverage-matrix\n'
            '2. query.sh --project-root /home/yaosh/projects/zchat --summary\n'
            '展示两个命令的完整输出。'
        ),
        assertions=[
            Assertion("按 type 查询返回结果", "contains", "coverage-matrix"),
            Assertion("summary 包含统计", "regex", r"(Total|总计).*\d+"),
        ],
        timeout=120,
    ))

    cases.append(TestCase(
        skill=6, function=4, name="update-status",
        prompt=(
            '使用 artifact-registry skill，说明 update-status.sh 支持的状态流转规则。'
            '具体说明哪些流转是合法的（draft→confirmed→executed→archived），'
            '哪些是非法的（如 executed→draft），以及非法流转时脚本的行为。'
        ),
        assertions=[
            Assertion("提到状态流转", "regex", r"(draft.*confirmed|confirmed.*executed|forward)"),
            Assertion("提到非法流转", "regex", r"(非法|拒绝|error|reject|cannot|不允许)"),
        ],
        timeout=120,
    ))

    cases.append(TestCase(
        skill=6, function=5, name="link",
        prompt=(
            '使用 artifact-registry skill，说明 link.sh 的功能和使用方式。'
            '它如何建立双向关联？查询当前 registry 中是否有已建立的 related_ids 关联。'
            '运行 query.sh --project-root /home/yaosh/projects/zchat --summary 展示结果。'
        ),
        assertions=[
            Assertion("提到双向关联", "regex", r"(双向|bidirectional|related_ids|关联)"),
            Assertion("展示了查询结果", "regex", r"(Total|artifacts?)"),
        ],
        timeout=120,
    ))

    # ================================================================
    # Skill 1: project-discussion-zchat (6 功能)
    # ================================================================

    cases.append(TestCase(
        skill=1, function=1, name="项目知识问答",
        prompt=(
            '使用 project-discussion-zchat skill 回答：'
            'zchat 的 agent_manager 模块是如何管理 agent 生命周期的？'
            'create/stop/restart 的核心逻辑在哪里？'
            '请引用具体的 file:line，并运行相关单元测试验证。'
        ),
        assertions=[
            Assertion("包含 file:line 引用", "regex", r"agent_manager\.py:\d+"),
            Assertion("包含函数名引用", "regex",
                      r"(create_agent|stop_agent|restart_agent|\.create|\.stop|\.restart|create\(|stop\(|restart\()"),
            Assertion("包含测试执行证据", "regex", r"(passed|failed|PASSED|FAILED|test session)"),
        ],
        timeout=300,
    ))

    cases.append(TestCase(
        skill=1, function=2, name="自动刷新检测",
        setup_commands=[
            # 创建 code-diff 触发刷新
            f"cat > {ARTIFACTS_DIR}/code-diffs/test-refresh-diff.md << 'EEOF'\n"
            "---\ntype: code-diff\nid: code-diff-refresh-001\nstatus: draft\n"
            "producer: manual-test\ncreated_at: \"2026-04-10\"\n---\n"
            "# Test Refresh Diff\n## Changes\n- Modified: zchat/cli/agent_manager.py (test)\nEEOF",
            f"bash {REG}/register.sh --project-root {PROJECT_ROOT} --type code-diff "
            f"--name 'refresh test diff' --producer manual-test "
            f"--path .artifacts/code-diffs/test-refresh-diff.md --status draft",
        ],
        prompt=(
            '使用 project-discussion-zchat skill。'
            '检查 .artifacts/ 中是否有新的 code-diff 或 e2e-report artifact，'
            '然后回答：agent_manager 模块最近有什么变动？'
        ),
        assertions=[
            Assertion("检测到新 artifact", "regex", r"(code-diff|新的|检测到|发现|refresh|变动|diff)"),
            Assertion("包含 agent_manager 分析", "regex", r"(agent_manager|agent.manager)"),
        ],
        cleanup_commands=[
            f"rm -f {ARTIFACTS_DIR}/code-diffs/test-refresh-diff.md",
        ],
        timeout=300,
    ))

    cases.append(TestCase(
        skill=1, function=3, name="分流判断",
        setup_commands=[
            # 创建 eval-doc 用于分流
            f"cat > {ARTIFACTS_DIR}/eval-docs/eval-triage-test.md << 'EEOF'\n"
            "---\ntype: eval-doc\nid: eval-doc-triage-test\nstatus: draft\n"
            "mode: verify\nfeature: \"scoped_name 双前缀\"\n"
            "producer: skill-5\ncreated_at: \"2026-04-10\"\n---\n"
            "# Eval: scoped_name 双前缀\n## Testcase\n"
            "| # | 场景 | 预期效果 | 实际效果 | 差异 | 优先级 |\n"
            "|---|------|---------|---------|------|--------|\n"
            "| 1 | scoped_name(\"alice-helper\", \"alice\") | alice-helper | alice-alice-helper | 双前缀 | P0 |\nEEOF",
        ],
        prompt=(
            '使用 project-discussion-zchat skill。'
            '我们来讨论 .artifacts/eval-docs/eval-triage-test.md 中的 eval-doc，'
            'scoped_name 的双前缀问题是不是 bug？'
            '请读取 zchat-protocol 中的 naming 模块代码，运行 protocol 测试，给出分流判断。'
        ),
        assertions=[
            Assertion("读取了代码", "regex", r"(naming|scoped_name|protocol|zchat.protocol)"),
            Assertion("给出判断结论", "regex", r"(bug|问题|是|不是|结论|判断|确认)"),
        ],
        cleanup_commands=[
            f"rm -f {ARTIFACTS_DIR}/eval-docs/eval-triage-test.md",
        ],
        timeout=300,
    ))

    cases.append(TestCase(
        skill=1, function=4, name="Artifact 交互",
        prompt=(
            '使用 project-discussion-zchat skill，'
            '查一下当前 .artifacts/ 中有哪些 artifact，各自什么状态？'
            '使用 artifact-registry 的 query.sh --summary 获取数据。'
        ),
        assertions=[
            Assertion("包含 coverage-matrix 信息", "contains", "coverage-matrix"),
            Assertion("包含状态信息", "regex", r"(draft|confirmed|executed|archived)"),
        ],
        timeout=180,
    ))

    cases.append(TestCase(
        skill=1, function=5, name="自我演进（驳回归档）",
        setup_commands=[
            # 创建非 bug eval-doc
            f"cat > {ARTIFACTS_DIR}/eval-docs/eval-not-bug-test.md << 'EEOF'\n"
            "---\ntype: eval-doc\nid: eval-doc-not-bug-test\nstatus: draft\n"
            "mode: verify\nfeature: \"zchat doctor 检查 Docker\"\n"
            "producer: skill-5\ncreated_at: \"2026-04-10\"\n---\n"
            "# Eval: doctor 检查 Docker\n## Testcase\n"
            "| # | 场景 | 预期效果 | 实际效果 | 差异 | 优先级 |\n"
            "|---|------|---------|---------|------|--------|\n"
            "| 1 | zchat doctor | 检查 Docker | 不检查 Docker | 缺少 Docker 检查 | P2 |\nEEOF",
            f"bash {REG}/register.sh --project-root {PROJECT_ROOT} --type eval-doc "
            f"--name 'doctor Docker check' --producer skill-5 "
            f"--path .artifacts/eval-docs/eval-not-bug-test.md --status draft",
        ],
        prompt=(
            '使用 project-discussion-zchat skill。'
            '.artifacts/eval-docs/eval-not-bug-test.md 描述了 "zchat doctor 不检查 Docker"。'
            '结论：这不是 bug，是 feature request。'
            '请将这个 eval-doc 归档（archived），在文件中追加 rejection_reason 字段说明原因。'
            '使用 update-status.sh 更新状态。'
        ),
        assertions=[
            Assertion("提到归档或 archived", "regex", r"(archived|归档|reject|驳回)"),
            Assertion("提到 feature request", "regex", r"(feature.request|功能请求|不是.bug|not.a.bug)"),
        ],
        cleanup_commands=[
            f"rm -f {ARTIFACTS_DIR}/eval-docs/eval-not-bug-test.md",
        ],
        timeout=300,
    ))

    cases.append(TestCase(
        skill=1, function=6, name="测试 Pipeline 信息查询",
        prompt=(
            '使用 project-discussion-zchat skill，'
            '这个项目的 E2E 测试 pipeline 是什么样的？用什么框架？'
            'fixture 有哪些？怎么采集证据？测试命名规范是什么？marker 有哪些？'
        ),
        assertions=[
            Assertion("包含 pytest 框架", "contains", "pytest"),
            Assertion("包含 E2E 目录", "contains", "tests/e2e"),
            Assertion("包含 fixture 信息", "regex",
                      r"(e2e_context|ergo_server|zchat_cli|irc_probe|fixture)"),
            Assertion("包含 marker 信息", "regex",
                      r"(pytest\.mark\.e2e|mark\.e2e|@.*e2e|e2e.*mark)"),
        ],
        timeout=300,
    ))

    # ================================================================
    # Skill 5: feature-eval (6 功能)
    # ================================================================

    cases.append(TestCase(
        skill=5, function=1, name="模拟模式 (simulate)",
        prompt=(
            '使用 feature-eval skill 的模拟模式（simulate）。'
            '模拟：如果 zchat 支持 agent 间通过 IRC DM 直接私聊（不经过频道），'
            '预期各场景的效果如何？'
            '生成 eval-doc，保存到 .artifacts/eval-docs/，注册到 registry。'
            '直接以 draft 状态保存，不需要确认。'
        ),
        assertions=[
            Assertion("包含 testcase", "regex", r"(testcase|测试用例|场景|test.?case)"),
            Assertion("包含正常路径", "regex", r"(DM|私聊|PRIVMSG|直接.?消息)"),
            Assertion("包含边界情况", "regex", r"(离线|不存在|错误|边界|offline)"),
            Assertion("eval-docs 有文件", "command",
                      f"test $(find {ARTIFACTS_DIR}/eval-docs -name 'eval-agent-dm*' -type f | wc -l) -gt 0"),
        ],
        timeout=600,
    ))

    cases.append(TestCase(
        skill=5, function=2, name="用户确认后注册 (draft→confirmed)",
        prompt=(
            '使用 feature-eval skill。'
            f'读取 .artifacts/eval-docs/ 中最新的 eval-doc（关于 agent DM 的），'
            '我已审查完毕，确认这个 eval-doc 内容正确。'
            '请将它的状态从 draft 更新为 confirmed。'
            '使用 artifact-registry 的 update-status.sh 执行状态变更。'
        ),
        assertions=[
            Assertion("提到状态变更", "regex", r"(confirmed|状态.*更新|update.*status|draft.*confirmed)"),
            Assertion("registry 有 confirmed eval-doc", "command",
                      f"bash {REG}/query.sh --project-root {PROJECT_ROOT} --type eval-doc --status confirmed "
                      f"2>/dev/null | grep -c confirmed || true"),
        ],
        timeout=300,
    ))

    cases.append(TestCase(
        skill=5, function=3, name="验证模式 (verify)",
        prompt=(
            '使用 feature-eval skill 的验证模式（verify）。'
            "发现 bug：scoped_name('alice-helper', 'alice') 返回 'alice-alice-helper'。"
            '收集信息生成 eval-doc，保存到 .artifacts/eval-docs/，注册到 registry。'
            '直接以 draft 状态保存，不创建 GitHub issue。'
        ),
        assertions=[
            Assertion("包含 bug 分析", "regex", r"(bug|双前缀|prefix|scoped_name)"),
            Assertion("包含 eval-doc", "regex", r"(eval-doc|verify|验证)"),
        ],
        timeout=300,
    ))

    cases.append(TestCase(
        skill=5, function=4, name="create-issue.sh --dry-run",
        prompt=(
            '使用 feature-eval skill。'
            '找到 .artifacts/eval-docs/ 中关于 scoped_name 的 eval-doc，'
            '使用 create-issue.sh --dry-run 模式测试 issue 创建。'
            '运行命令并展示 dry-run 输出。不要实际创建 issue。'
        ),
        assertions=[
            Assertion("dry-run 模式", "regex", r"(dry.run|Would create|不实际创建)"),
            Assertion("包含 title", "regex", r"(Title|title|标题|scoped_name)"),
        ],
        timeout=180,
    ))

    cases.append(TestCase(
        skill=5, function=5, name="add-watcher.sh --dry-run",
        prompt=(
            '使用 feature-eval skill。'
            '运行 add-watcher.sh --dry-run 测试添加 watcher 功能：'
            'bash /home/yaosh/.claude/skills/feature-eval/scripts/add-watcher.sh '
            '--issue-url https://github.com/ezagent42/zchat/issues/1 '
            '--watcher testuser --dry-run'
        ),
        assertions=[
            Assertion("dry-run 输出", "regex", r"(dry.run|Would add|watcher)"),
            Assertion("包含 issue URL", "contains", "ezagent42/zchat"),
        ],
        timeout=120,
    ))

    cases.append(TestCase(
        skill=5, function=6, name="Artifact 注册（验证模式完整流程）",
        prompt=(
            '使用 artifact-registry skill，查询 registry 中 type 为 eval-doc 的所有条目。'
            '运行 query.sh --project-root /home/yaosh/projects/zchat --type eval-doc。'
            '验证是否有 simulate 和 verify 两种 mode 的 eval-doc 都已注册。'
        ),
        assertions=[
            Assertion("查到 eval-doc 条目", "regex", r"eval-doc"),
            Assertion("有多个 eval-doc", "regex", r"(eval-doc-00[12]|\"id\".*eval)"),
        ],
        timeout=120,
    ))

    # ================================================================
    # Skill 2: test-plan-generator (5 功能)
    # ================================================================

    cases.append(TestCase(
        skill=2, function=1, name="从 code-diff 生成 test-plan",
        setup_commands=[
            # 创建 code-diff
            f"cat > {ARTIFACTS_DIR}/code-diffs/diff-restart-refactor.md << 'EEOF'\n"
            "---\ntype: code-diff\nid: code-diff-restart-001\nstatus: draft\n"
            "producer: phase-2\ncreated_at: \"2026-04-10\"\n---\n"
            "# Code Diff: Agent restart 重构\n## 变更文件\n"
            "- M zchat/cli/agent_manager.py (restart 函数重构)\n"
            "## 影响模块\n- agent_manager\n## 改动类型\n"
            "- 修改：restart 现在先 graceful stop 再 create\nEEOF",
            f"bash {REG}/register.sh --project-root {PROJECT_ROOT} --type code-diff "
            f"--name 'restart refactor diff' --producer phase-2 "
            f"--path .artifacts/code-diffs/diff-restart-refactor.md --status draft",
        ],
        prompt=(
            '使用 test-plan-generator skill。'
            '根据 .artifacts/code-diffs/diff-restart-refactor.md (code-diff-restart-001) 生成测试计划。'
            '读取 code-diff 和 coverage-matrix，输出测试计划。'
            '保存到 .artifacts/test-plans/，注册到 registry。直接以 draft 状态保存。'
        ),
        assertions=[
            Assertion("包含 TC-ID", "regex", r"TC-\d+"),
            Assertion("来源包含 code-diff", "regex", r"(code-diff|code.diff|源.*diff)"),
            Assertion("包含 restart 相关用例", "regex", r"(restart|重启)"),
        ],
        cleanup_commands=[
            f"rm -f {ARTIFACTS_DIR}/code-diffs/diff-restart-refactor.md",
        ],
        timeout=300,
    ))

    cases.append(TestCase(
        skill=2, function=2, name="从 coverage-gap 生成 test-plan",
        prompt=(
            '使用 test-plan-generator skill。'
            '分析 coverage-matrix 中未覆盖的用户流程，'
            '为 "创建项目" 流程生成测试计划。'
            '保存到 .artifacts/test-plans/，注册到 registry。直接以 draft 状态保存。'
        ),
        assertions=[
            Assertion("包含测试用例", "regex", r"(TC-\d+|测试用例)"),
            Assertion("来源为 coverage-gap", "regex", r"(coverage.gap|未覆盖|覆盖.*gap)"),
            Assertion("包含项目创建", "regex", r"(创建项目|project.create|zchat project)"),
        ],
        timeout=300,
    ))

    cases.append(TestCase(
        skill=2, function=3, name="从 eval-doc 生成 test-plan",
        prompt=(
            '使用 test-plan-generator skill。'
            '从 .artifacts/eval-docs/ 中状态为 confirmed 的 eval-doc 生成测试计划。'
            '如果没有 confirmed 的 eval-doc，就用 eval-doc-001（agent DM 模拟）作为输入。'
            '将 eval-doc 中的 testcase 转换为测试计划中的用例。'
            '保存到 .artifacts/test-plans/，注册到 registry。直接以 draft 状态保存。'
        ),
        assertions=[
            Assertion("包含 TC-ID", "regex", r"TC-\d+"),
            Assertion("来源为 eval-doc", "regex", r"(eval-doc|eval.doc)"),
            Assertion("test-plans 目录有新文件", "command",
                      f"test $(find {ARTIFACTS_DIR}/test-plans -name '*.md' -type f | wc -l) -gt 0"),
        ],
        timeout=300,
    ))

    cases.append(TestCase(
        skill=2, function=4, name="人 review + confirm 流程",
        prompt=(
            '使用 test-plan-generator skill。'
            '找到 .artifacts/test-plans/ 中最新的 draft 状态 test-plan，'
            '我已审查完毕，确认内容正确。请将它的状态更新为 confirmed。'
            '使用 artifact-registry 的 update-status.sh 执行变更。'
        ),
        assertions=[
            Assertion("状态变更", "regex", r"(confirmed|状态.*更新|update.*status)"),
            Assertion("有 confirmed test-plan", "command",
                      f"bash {REG}/query.sh --project-root {PROJECT_ROOT} --type test-plan --status confirmed "
                      f"2>/dev/null | grep -c confirmed || echo 0"),
        ],
        timeout=300,
    ))

    cases.append(TestCase(
        skill=2, function=5, name="注册到 .artifacts/",
        prompt=(
            '使用 artifact-registry skill，查询所有 test-plan 类型的 artifact：'
            'bash /home/yaosh/.claude/skills/artifact-registry/scripts/query.sh '
            '--project-root /home/yaosh/projects/zchat --type test-plan'
        ),
        assertions=[
            Assertion("有 test-plan 条目", "regex", r"test-plan"),
            Assertion("有 producer skill-2", "regex", r"(skill-2|producer)"),
        ],
        timeout=120,
    ))

    # ================================================================
    # Skill 3: test-code-writer (5 功能)
    # ================================================================

    cases.append(TestCase(
        skill=3, function=1, name="读取 confirmed test-plan",
        prompt=(
            '使用 test-code-writer skill。'
            '通过 artifact-registry 查询 .artifacts/test-plans/ 中 confirmed 状态的 test-plan，'
            '读取其内容，列出将要实现的 TC-ID 列表。'
        ),
        assertions=[
            Assertion("列出了 TC-ID", "regex", r"TC-\d+"),
            Assertion("读取了 plan 内容", "regex", r"(test-plan|测试计划|plan)"),
        ],
        timeout=300,
    ))

    cases.append(TestCase(
        skill=3, function=2, name="查询 pipeline 信息",
        prompt=(
            '使用 test-code-writer skill。'
            '读取项目的测试 pipeline 信息：框架、E2E 目录、fixture 列表、命名规范。'
            '实际读取 tests/e2e/conftest.py 了解 fixture 实现。'
        ),
        assertions=[
            Assertion("包含 pytest", "contains", "pytest"),
            Assertion("包含 conftest", "regex", r"(conftest|fixture)"),
            Assertion("包含 E2E 目录", "contains", "tests/e2e"),
        ],
        timeout=300,
    ))

    cases.append(TestCase(
        skill=3, function=3, name="生成 E2E 测试代码",
        prompt=(
            '使用 test-code-writer skill。'
            '根据 .artifacts/test-plans/ 中最新的 confirmed test-plan 编写 E2E 测试代码。'
            '生成的测试应放在 tests/e2e/ 目录下，使用 @pytest.mark.e2e，'
            '复用已有 fixture（e2e_context, ergo_server, zchat_cli 等），'
            '函数命名遵循 test_{action}_{target} 规范。'
        ),
        assertions=[
            Assertion("生成了测试代码", "regex", r"(def test_|@pytest\.mark|test_.*\.py)"),
            Assertion("使用了 fixture", "regex", r"(e2e_context|ergo_server|zchat_cli|fixture)"),
            Assertion("包含 pytest.mark.e2e", "regex", r"(pytest\.mark\.e2e|mark\.e2e)"),
        ],
        timeout=600,
    ))

    cases.append(TestCase(
        skill=3, function=4, name="追加 vs 新建文件判断",
        prompt=(
            '使用 test-code-writer skill。'
            '在编写 E2E 测试代码时，说明你的文件决策：'
            '是追加到已有 test 文件还是新建文件？'
            '列出 tests/e2e/ 下已有文件及其行数，说明决策理由。'
        ),
        assertions=[
            Assertion("提到文件决策", "regex", r"(追加|新建|append|new file|已有文件)"),
            Assertion("列出了已有文件", "regex", r"(test_.*\.py|tests/e2e/)"),
        ],
        timeout=300,
    ))

    cases.append(TestCase(
        skill=3, function=5, name="生成 test-diff artifact",
        prompt=(
            '使用 test-code-writer skill。'
            '检查 tests/e2e/ 中最近修改的测试文件，生成 test-diff artifact：'
            '记录新增的测试函数、使用的 fixture、文件路径。'
            '保存到 .artifacts/test-diffs/，注册到 registry。'
            '然后将关联的 test-plan 状态更新为 executed。'
        ),
        assertions=[
            Assertion("提到 test-diff", "regex", r"(test-diff|test.diff)"),
            Assertion("提到新增函数", "regex", r"(def test_|新增|函数|function)"),
        ],
        timeout=300,
    ))

    # ================================================================
    # Skill 4: test-runner (6 功能)
    # ================================================================

    cases.append(TestCase(
        skill=4, function=1, name="env-check 预检",
        prompt=(
            '使用 test-runner skill。'
            '运行 env-check.sh --project-root /home/yaosh/projects/zchat 检查 E2E 环境。'
            '展示完整的检查结果，说明哪些是 hard dependency，哪些是 soft。'
        ),
        assertions=[
            Assertion("运行了 env-check", "regex", r"(PASS|pass|ready|Environment Check)"),
            Assertion("区分 hard/soft", "regex", r"(hard|soft|warning|WARN)"),
        ],
        timeout=180,
    ))

    cases.append(TestCase(
        skill=4, function=2, name="执行完整 E2E 套件",
        prompt=(
            '使用 test-runner skill。'
            '执行完整的 E2E 测试套件。先运行 env-check 确认环境就绪，'
            '然后运行 uv run pytest tests/e2e/ -v --tb=long -q。'
            '展示完整的 pytest 输出。'
        ),
        assertions=[
            Assertion("pytest 实际执行", "regex", r"(passed|failed|error|PASSED|FAILED|test session)"),
            Assertion("包含测试结果", "regex", r"(\d+ passed|\d+ failed|\d+ error)"),
        ],
        timeout=600,
    ))

    cases.append(TestCase(
        skill=4, function=3, name="新增 vs 回归分类",
        prompt=(
            '使用 test-runner skill。'
            '检查 .artifacts/test-diffs/ 中是否有 test-diff artifact。'
            '如果有，将 test-diff 中列出的函数标记为 new case，其余为 regression case。'
            '如果没有 test-diff，所有测试都标记为 regression。'
            '展示分类结果。'
        ),
        assertions=[
            Assertion("有分类结果", "regex", r"(new.case|regression|新增|回归)"),
            Assertion("提到 test-diff", "regex", r"(test-diff|test.diff|没有.*diff)"),
        ],
        timeout=300,
    ))

    cases.append(TestCase(
        skill=4, function=4, name="证据采集",
        prompt=(
            '使用 test-runner skill。'
            '说明 E2E 测试的证据采集机制：每个测试如何采集证据？'
            '失败测试如何收集上下文（traceback、日志、进程状态）？'
            '读取 tests/e2e/ 的代码说明证据采集点。'
        ),
        assertions=[
            Assertion("提到证据", "regex", r"(证据|evidence|capture|采集|traceback)"),
            Assertion("提到失败处理", "regex", r"(失败|failure|error|traceback|日志|log)"),
        ],
        timeout=300,
    ))

    cases.append(TestCase(
        skill=4, function=5, name="生成 e2e-report",
        prompt=(
            '使用 test-runner skill。'
            '基于最近一次 E2E 测试执行结果，生成结构化 e2e-report。'
            '包含 YAML frontmatter（type: e2e-report），结果汇总表，'
            '每个测试的详细结果。保存到 .artifacts/e2e-reports/，注册到 registry。'
        ),
        assertions=[
            Assertion("提到 e2e-report", "regex", r"(e2e-report|e2e.report|测试报告)"),
            Assertion("包含结果汇总", "regex", r"(passed|failed|汇总|summary|通过|失败)"),
        ],
        timeout=600,
    ))

    cases.append(TestCase(
        skill=4, function=6, name="更新 coverage-matrix",
        prompt=(
            '使用 test-runner skill。'
            '基于 E2E 测试结果，检查哪些用户流程的测试通过了。'
            '读取 .artifacts/coverage/coverage-matrix.md，'
            '说明哪些流程现在有 E2E 覆盖，哪些还没有。'
            '如果有新通过的测试，更新 coverage-matrix 中对应的标记。'
        ),
        assertions=[
            Assertion("读取了 coverage-matrix", "regex", r"(coverage.matrix|覆盖矩阵)"),
            Assertion("列出了覆盖状态", "regex", r"(覆盖|covered|未覆盖|not covered|✅|❌)"),
        ],
        timeout=300,
    ))

    return cases


# --- 执行引擎 ---


def snapshot_registry() -> Path:
    """保存 registry.json 快照。"""
    snapshot = Path(f"/tmp/registry-before-{int(time.time())}.json")
    src = ARTIFACTS_DIR / "registry.json"
    if src.exists():
        shutil.copy2(src, snapshot)
    return snapshot


def run_claude_p(prompt: str, timeout: int = 300) -> tuple[str, float, int]:
    """通过 claude -p 无头运行 prompt，返回 (output, duration, exit_code)。"""
    cmd = [
        "claude",
        "-p", prompt,
        "--output-format", "text",
        "--max-turns", "30",
        "--add-dir", str(Path.home() / ".claude/skills"),
        "--permission-mode", "bypassPermissions",
    ]

    # 移除 CLAUDECODE 环境变量以允许嵌套
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
            env=env,
        )
        duration = time.time() - start
        output = result.stdout + ("\n[STDERR]\n" + result.stderr if result.stderr else "")
        return output, duration, result.returncode
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        return f"[TIMEOUT after {timeout}s]", duration, -1


def check_assertion(assertion: Assertion, output: str) -> None:
    """检查单个断言。"""
    if assertion.check == "contains":
        assertion.passed = assertion.value.lower() in output.lower()
        if assertion.passed:
            # 提取匹配上下文
            idx = output.lower().find(assertion.value.lower())
            start = max(0, idx - 30)
            end = min(len(output), idx + len(assertion.value) + 30)
            assertion.evidence = f"...{output[start:end]}..."
        else:
            assertion.evidence = "未在输出中找到"

    elif assertion.check == "regex":
        match = re.search(assertion.value, output, re.IGNORECASE)
        assertion.passed = match is not None
        if match:
            assertion.evidence = f"匹配: '{match.group()}'"
        else:
            assertion.evidence = f"regex '{assertion.value}' 未匹配"

    elif assertion.check == "file_exists":
        path = Path(assertion.value)
        assertion.passed = path.exists()
        assertion.evidence = f"{'存在' if assertion.passed else '不存在'}: {path}"

    elif assertion.check == "command":
        try:
            r = subprocess.run(
                assertion.value, shell=True, capture_output=True, text=True, timeout=30
            )
            assertion.passed = r.returncode == 0
            assertion.evidence = r.stdout.strip()[:200] if r.stdout else f"exit={r.returncode}"
            if r.returncode != 0 and r.stderr:
                assertion.evidence += f" stderr: {r.stderr.strip()[:100]}"
        except subprocess.TimeoutExpired:
            assertion.passed = False
            assertion.evidence = "命令超时"

    elif assertion.check == "verify_script":
        try:
            r = subprocess.run(
                ["bash", str(VERIFY_SCRIPT)] + assertion.value.split(),
                capture_output=True, text=True, timeout=30,
                cwd=str(PROJECT_ROOT),
            )
            assertion.passed = r.returncode == 0
            assertion.evidence = r.stdout.strip()[-300:]
        except subprocess.TimeoutExpired:
            assertion.passed = False
            assertion.evidence = "verify 脚本超时"


def run_test_case(tc: TestCase, dry_run: bool = False) -> None:
    """执行单个测试用例。"""
    print(f"\n{'='*60}")
    print(f"[Skill {tc.skill} 功能 {tc.function}] {tc.name}")
    print(f"{'='*60}")

    if dry_run:
        tc.status = "skipped"
        print(f"  [dry-run] 提示词: {tc.prompt[:80]}...")
        print(f"  [dry-run] 断言数: {len(tc.assertions)}")
        print(f"  [dry-run] 超时: {tc.timeout}s")
        return

    # Setup
    for cmd in tc.setup_commands:
        print(f"  [setup] {cmd}")
        subprocess.run(cmd, shell=True, capture_output=True, cwd=str(PROJECT_ROOT))

    # 快照 registry
    snapshot = snapshot_registry()

    # 执行
    tc.status = "running"
    print(f"  运行 claude -p (timeout={tc.timeout}s)...")
    print(f"  提示词: {tc.prompt[:100]}...")

    output, duration, exit_code = run_claude_p(tc.prompt, tc.timeout)
    tc.output = output
    tc.duration = duration

    print(f"  完成: {duration:.1f}s, exit={exit_code}, output={len(output)} chars")

    if exit_code == -1:
        tc.status = "error"
        tc.error_msg = f"超时 ({tc.timeout}s)"
        print(f"  ❌ 超时")
        return

    # 检查断言
    all_passed = True
    for a in tc.assertions:
        check_assertion(a, output)
        status = "✅" if a.passed else "❌"
        print(f"  {status} {a.description}: {a.evidence[:80]}")
        if not a.passed:
            all_passed = False

    tc.status = "passed" if all_passed else "failed"

    # Cleanup
    for cmd in tc.cleanup_commands:
        print(f"  [cleanup] {cmd}")
        subprocess.run(cmd, shell=True, capture_output=True, cwd=str(PROJECT_ROOT))

    # 清理快照
    if snapshot.exists():
        snapshot.unlink()


# --- 报告生成 ---


def generate_report(cases: list[TestCase]) -> str:
    """生成 markdown 格式报告。"""
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d %H:%M UTC")

    total = len(cases)
    passed = sum(1 for c in cases if c.status == "passed")
    failed = sum(1 for c in cases if c.status == "failed")
    errors = sum(1 for c in cases if c.status == "error")
    skipped = sum(1 for c in cases if c.status == "skipped")

    lines = [
        "# Dev-Loop Skills 交互式 E2E 测试报告",
        "",
        f"**日期**: {timestamp}",
        f"**方法**: `claude -p` (pipe mode) 无头自动化执行",
        f"**总用例**: {total} | **通过**: {passed} | **失败**: {failed} | **错误**: {errors} | **跳过**: {skipped}",
        "",
        "---",
        "",
        "## 结果汇总",
        "",
        "| Skill | 功能 | 名称 | 状态 | 耗时 | 断言 |",
        "|-------|------|------|------|------|------|",
    ]

    for tc in cases:
        status_icon = {
            "passed": "PASS", "failed": "FAIL",
            "error": "ERROR", "skipped": "SKIP", "pending": "—"
        }.get(tc.status, "?")
        assertion_summary = ""
        if tc.assertions:
            a_pass = sum(1 for a in tc.assertions if a.passed)
            a_total = len(tc.assertions)
            assertion_summary = f"{a_pass}/{a_total}"
        duration_str = f"{tc.duration:.1f}s" if tc.duration > 0 else "—"
        lines.append(
            f"| {tc.skill} | {tc.function} | {tc.name} | {status_icon} | {duration_str} | {assertion_summary} |"
        )

    lines.extend(["", "---", "", "## 详细结果", ""])

    for tc in cases:
        lines.append(f"### Skill {tc.skill} 功能 {tc.function}: {tc.name}")
        lines.append("")
        lines.append(f"**状态**: {tc.status} | **耗时**: {tc.duration:.1f}s")
        lines.append("")
        lines.append(f"**提示词**: `{tc.prompt[:120]}{'...' if len(tc.prompt) > 120 else ''}`")
        lines.append("")

        if tc.error_msg:
            lines.append(f"**错误**: {tc.error_msg}")
            lines.append("")

        if tc.assertions:
            lines.append("**断言**:")
            lines.append("")
            lines.append("| # | 描述 | 结果 | 证据 |")
            lines.append("|---|------|------|------|")
            for i, a in enumerate(tc.assertions, 1):
                result = "PASS" if a.passed else ("FAIL" if a.passed is not None else "—")
                evidence = a.evidence.replace("|", "\\|").replace("\n", " ")[:100]
                lines.append(f"| {i} | {a.description} | {result} | {evidence} |")
            lines.append("")

        # 输出摘要（截取关键部分）
        if tc.output and tc.status != "skipped":
            # 截取前 500 字符和后 500 字符
            output_preview = tc.output[:500]
            if len(tc.output) > 1000:
                output_preview += f"\n\n... (共 {len(tc.output)} 字符，已截断) ...\n\n"
                output_preview += tc.output[-500:]
            elif len(tc.output) > 500:
                output_preview = tc.output

            lines.append("<details>")
            lines.append(f"<summary>输出摘要 ({len(tc.output)} chars)</summary>")
            lines.append("")
            lines.append("```")
            lines.append(output_preview)
            lines.append("```")
            lines.append("")
            lines.append("</details>")
            lines.append("")

        # 失败分析
        if tc.status == "failed":
            failed_assertions = [a for a in tc.assertions if a.passed is False]
            lines.append("**失败原因分析**:")
            lines.append("")
            for a in failed_assertions:
                lines.append(f"- **{a.description}**: {a.evidence}")
            lines.append("")

            # 修复建议
            lines.append("**修复建议**:")
            lines.append("")
            for a in failed_assertions:
                if "未在输出中找到" in a.evidence or "未匹配" in a.evidence:
                    lines.append(
                        f"- 检查 Skill {tc.skill} SKILL.md 中是否有明确指令要求输出 `{a.description}` 相关内容"
                    )
                elif "不存在" in a.evidence:
                    lines.append(
                        f"- Skill {tc.skill} 未在磁盘上创建预期文件。检查 SKILL.md 步骤中文件写入逻辑"
                    )
                elif "exit=" in a.evidence:
                    lines.append(
                        f"- 命令执行失败: {a.evidence}"
                    )
            lines.append("")

        lines.append("---")
        lines.append("")

    # 总结
    lines.extend([
        "## 修复建议汇总",
        "",
    ])

    failed_cases = [tc for tc in cases if tc.status in ("failed", "error")]
    if failed_cases:
        for tc in failed_cases:
            lines.append(f"### Skill {tc.skill} 功能 {tc.function}: {tc.name}")
            if tc.status == "error":
                lines.append(f"- **问题**: {tc.error_msg}")
                lines.append(f"- **建议**: 增加超时时间或检查 skill 执行逻辑")
            else:
                for a in tc.assertions:
                    if a.passed is False:
                        lines.append(f"- **{a.description}**: {a.evidence}")
            lines.append("")
    else:
        lines.append("无失败用例。")
        lines.append("")

    return "\n".join(lines)


# --- 主入口 ---


def main():
    parser = argparse.ArgumentParser(description="Dev-Loop Skills E2E 自动化测试")
    parser.add_argument("--skill", type=int, help="只测试指定 skill (1-6)")
    parser.add_argument("--all", action="store_true", help="按顺序测试全部 skill")
    parser.add_argument("--timeout", type=int, default=300, help="默认超时秒数")
    parser.add_argument("--dry-run", action="store_true", help="只显示会执行什么")
    parser.add_argument("--model", type=str, default=None, help="覆盖模型 (如 sonnet)")
    args = parser.parse_args()

    cases = build_test_cases()

    # 按测试计划推荐顺序排序: 6 → 1 → 5 → 2 → 3 → 4
    skill_order = [6, 1, 5, 2, 3, 4]

    if args.skill:
        cases = [c for c in cases if c.skill == args.skill]
    else:
        # 按推荐顺序排
        def sort_key(tc):
            try:
                return (skill_order.index(tc.skill), tc.function)
            except ValueError:
                return (99, tc.function)
        cases.sort(key=sort_key)

    if not cases:
        print("没有匹配的测试用例。")
        sys.exit(1)

    if args.timeout:
        for c in cases:
            if c.timeout == 300:  # 只覆盖默认值
                c.timeout = args.timeout

    print(f"{'='*60}")
    print(f"Dev-Loop Skills E2E 自动化测试")
    print(f"用例数: {len(cases)}")
    print(f"模式: {'dry-run' if args.dry_run else 'live'}")
    print(f"{'='*60}")

    for tc in cases:
        run_test_case(tc, dry_run=args.dry_run)

    # 生成报告
    report = generate_report(cases)
    now = datetime.now()
    report_name = f"report-interactive-{now.strftime('%Y%m%d-%H%M')}.md"
    report_path = REPORT_DIR / report_name
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)

    # 打印总结
    passed = sum(1 for c in cases if c.status == "passed")
    failed = sum(1 for c in cases if c.status == "failed")
    errors = sum(1 for c in cases if c.status == "error")
    total = len(cases)

    print(f"\n{'='*60}")
    print(f"总结: {passed}/{total} 通过, {failed} 失败, {errors} 错误")
    print(f"报告: {report_path}")
    print(f"{'='*60}")

    sys.exit(1 if (failed + errors) > 0 else 0)


if __name__ == "__main__":
    main()
