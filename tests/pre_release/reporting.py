"""Pre-release pytest reporting helpers.

Generates machine-readable JSON and human-readable Markdown reports after a
pre-release test run.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import traceback
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CHECKLIST_ITEMS = [
    {
        "id": "doctor",
        "label": "doctor 环境检查",
        "module": "tests/pre_release/test_00_doctor.py",
        "type": "automated",
    },
    {
        "id": "project",
        "label": "project 生命周期",
        "module": "tests/pre_release/test_01_project.py",
        "type": "automated",
    },
    {
        "id": "template",
        "label": "template 管理",
        "module": "tests/pre_release/test_02_template.py",
        "type": "automated",
    },
    {
        "id": "irc",
        "label": "irc daemon/client",
        "module": "tests/pre_release/test_03_irc.py",
        "type": "automated",
    },
    {
        "id": "agent",
        "label": "agent 生命周期与消息",
        "module": "tests/pre_release/test_04_agent.py",
        "type": "automated",
    },
    {
        "id": "setup",
        "label": "setup weechat",
        "module": "tests/pre_release/test_05_setup.py",
        "type": "automated",
    },
    {
        "id": "auth",
        "label": "auth 命令",
        "module": "tests/pre_release/test_06_auth.py",
        "type": "manual",
    },
    {
        "id": "self_update",
        "label": "update/upgrade",
        "module": "tests/pre_release/test_07_self_update.py",
        "type": "manual",
    },
    {
        "id": "shutdown",
        "label": "shutdown 收尾",
        "module": "tests/pre_release/test_08_shutdown.py",
        "type": "automated",
    },
    {
        "id": "remote_irc",
        "label": "remote IRC TLS+SASL",
        "module": "tests/pre_release/test_04b_remote_irc.py",
        "type": "remote",
    },
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def _shorten(text: str, limit: int = 1200) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... [truncated]"


def _safe_get_longrepr(report: Any) -> str:
    longreprtext = getattr(report, "longreprtext", "") or ""
    if longreprtext:
        return _shorten(longreprtext)
    longrepr = getattr(report, "longrepr", None)
    if isinstance(longrepr, tuple):
        return _shorten(" | ".join(str(part) for part in longrepr))
    if longrepr is not None:
        return _shorten(str(longrepr))
    return ""


def _status_label(status: str) -> str:
    labels = {
        "verified": "已验证",
        "failed": "失败",
        "manual_required": "手工验证",
        "conditional_not_run": "条件未满足",
        "not_verified": "未验证",
    }
    return labels.get(status, status)


def _extract_failure_highlights(failure: str) -> dict[str, str]:
    """Extract compact, high-signal lines from pytest longrepr text."""
    lines = [line.strip() for line in failure.splitlines() if line.strip()]
    if not lines:
        return {
            "headline": "",
            "assertion_line": "",
            "error_line": "",
            "hint": "",
        }

    assertion_line = next(
        (line for line in lines if line.startswith(">") and "assert " in line),
        "",
    )
    if not assertion_line:
        assertion_line = next((line for line in lines if "assert " in line), "")

    error_line = next((line for line in lines if line.startswith("E ")), "")
    if not error_line:
        error_line = next(
            (
                line
                for line in lines
                if "Error:" in line
                or "Exception:" in line
                or line.startswith("AssertionError")
            ),
            "",
        )

    headline = error_line or assertion_line or lines[-1]
    hint = ""
    if "wait_for_message(" in failure and "assert msg is not None" in failure:
        hint = "消息在超时窗口内未到达；建议优先检查频道加入状态、昵称一致性和发送路径。"

    return {
        "headline": _shorten(headline, limit=200),
        "assertion_line": _shorten(assertion_line, limit=200),
        "error_line": _shorten(error_line, limit=200),
        "hint": hint,
    }


@dataclass
class _CaseSeed:
    nodeid: str
    module: str
    name: str
    markers: list[str]


class PreReleaseReportCollector:
    """Collects pytest run events and writes reports at session finish."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.started_at = _utc_now_iso()
        self.started_wall = datetime.now(timezone.utc)
        self.case_seeds: dict[str, _CaseSeed] = {}
        self.case_results: dict[str, dict[str, Any]] = {}
        self.generated_paths: list[str] = []
        self.report_error: str | None = None
        self.enabled = not bool(config.getoption("no_pre_release_report"))

    def register_item(self, item: Any) -> None:
        nodeid = item.nodeid
        module = _normalize_path(nodeid.split("::", 1)[0])
        markers = sorted({marker.name for marker in item.iter_markers()})
        self.case_seeds[nodeid] = _CaseSeed(
            nodeid=nodeid,
            module=module,
            name=item.name,
            markers=markers,
        )
        self.case_results.setdefault(nodeid, self._new_case_result(nodeid))

    def _new_case_result(self, nodeid: str) -> dict[str, Any]:
        seed = self.case_seeds.get(nodeid)
        module = _normalize_path(nodeid.split("::", 1)[0])
        markers = seed.markers if seed else []
        is_manual = "manual" in markers
        is_remote = "remote" in module.lower() or "remote" in nodeid.lower()
        return {
            "nodeid": nodeid,
            "module": seed.module if seed else module,
            "name": seed.name if seed else nodeid.split("::")[-1],
            "markers": markers,
            "status": "unknown",
            "duration_s": 0.0,
            "retry_count": 0,
            "is_manual": is_manual,
            "is_remote": is_remote,
            "failure_at": None,
            "failure": None,
            "stdout_snippet": "",
            "stderr_snippet": "",
        }

    def on_report(self, report: Any) -> None:
        if not self.enabled or not _normalize_path(report.nodeid).startswith("tests/pre_release/"):
            return

        case = self.case_results.setdefault(report.nodeid, self._new_case_result(report.nodeid))
        case["duration_s"] += float(getattr(report, "duration", 0.0) or 0.0)

        outcome = getattr(report, "outcome", "")
        when = getattr(report, "when", "")
        if outcome == "rerun":
            case["retry_count"] += 1
            return

        # Prefer "call" phase for final status, but keep setup-skip/failure too.
        if outcome == "failed" and when in {"setup", "call", "teardown"}:
            case["status"] = "failed"
            if case["failure_at"] is None:
                case["failure_at"] = _utc_now_iso()
            case["failure"] = _safe_get_longrepr(report)
        elif outcome == "skipped" and when in {"setup", "call"} and case["status"] == "unknown":
            case["status"] = "skipped"
            skip_reason = _safe_get_longrepr(report)
            case["failure"] = skip_reason or case["failure"]
        elif outcome == "passed" and when == "call" and case["status"] == "unknown":
            case["status"] = "passed"

        out = getattr(report, "capstdout", "") or ""
        err = getattr(report, "capstderr", "") or ""
        if out and not case["stdout_snippet"]:
            case["stdout_snippet"] = _shorten(out)
        if err and not case["stderr_snippet"]:
            case["stderr_snippet"] = _shorten(err)

    def _module_summary(self) -> list[dict[str, Any]]:
        by_module: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "module": "",
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "unknown": 0,
                "duration_s": 0.0,
                "failed_cases": [],
                "manual_cases": 0,
                "remote_cases": 0,
            }
        )
        for case in self.case_results.values():
            mod = case["module"]
            bucket = by_module[mod]
            bucket["module"] = mod
            bucket["total"] += 1
            bucket["duration_s"] += case["duration_s"]
            status = case["status"]
            if status == "passed":
                bucket["passed"] += 1
            elif status == "failed":
                bucket["failed"] += 1
                bucket["failed_cases"].append(case["name"])
            elif status == "skipped":
                bucket["skipped"] += 1
            elif status == "unknown":
                bucket["unknown"] += 1
            if case["is_manual"]:
                bucket["manual_cases"] += 1
            if case["is_remote"]:
                bucket["remote_cases"] += 1

        return sorted(by_module.values(), key=lambda x: x["module"])

    def _gate_status(self, totals: dict[str, int]) -> tuple[str, list[str]]:
        risks: list[str] = []
        if totals["failed"] > 0:
            return "FAIL", risks
        if totals["skipped"] > 0:
            risky_skip_count = sum(
                1
                for case in self.case_results.values()
                if case["status"] == "skipped" and (case["is_manual"] or case["is_remote"])
            )
            if risky_skip_count > 0:
                risks.append(
                    f"{risky_skip_count} 个用例因 manual/remote 条件被跳过，建议补跑对应场景"
                )
            else:
                risks.append("存在跳过用例，建议确认是否影响发布结论")
            return "PASS_WITH_RISKS", risks
        return "PASS", risks

    def _checklist(self, module_summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
        module_index = {item["module"]: item for item in module_summary}
        checklist: list[dict[str, Any]] = []
        for item in CHECKLIST_ITEMS:
            module_data = module_index.get(item["module"])
            status = "not_verified"
            notes = ""
            if module_data is None or module_data["total"] == 0:
                status = "not_verified"
                notes = "本次未执行"
            elif module_data["failed"] > 0:
                status = "failed"
                notes = f"失败 {module_data['failed']} 个用例"
            elif module_data["passed"] > 0 and module_data["failed"] == 0 and module_data["skipped"] == 0:
                status = "verified"
                notes = "自动验证通过"
            elif module_data.get("unknown", 0) > 0 and module_data["passed"] == 0:
                status = "not_verified"
                if item["type"] == "manual":
                    notes = "本次未执行（manual marker 被过滤）"
                elif item["type"] == "remote":
                    notes = "本次未执行（remote 条件未触发）"
                else:
                    notes = "本次未执行（marker 过滤）"
            elif module_data["skipped"] > 0:
                if item["type"] == "manual":
                    status = "manual_required"
                    notes = "手工项未完整执行"
                elif item["type"] == "remote":
                    status = "conditional_not_run"
                    notes = "远程条件不满足或未配置凭据"
                else:
                    status = "not_verified"
                    notes = "存在跳过用例"
            checklist.append(
                {
                    "id": item["id"],
                    "label": item["label"],
                    "type": item["type"],
                    "module": item["module"],
                    "status": status,
                    "status_label": _status_label(status),
                    "notes": notes,
                }
            )
        return checklist

    def _environment(self) -> dict[str, Any]:
        zchat_cmd = os.environ.get("ZCHAT_CMD", "zchat")
        zchat_version = "unknown"
        try:
            res = subprocess.run(
                [zchat_cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if res.returncode == 0:
                zchat_version = (res.stdout or res.stderr).strip()
            else:
                zchat_version = f"unavailable (exit={res.returncode})"
        except Exception:
            zchat_version = "unavailable"
        return {
            "timestamp_utc": _utc_now_iso(),
            "os": platform.platform(),
            "python_version": platform.python_version(),
            "zchat_cmd": zchat_cmd,
            "zchat_version": zchat_version,
            "dependencies": {
                "zellij": bool(shutil.which("zellij")),
                "ergo": bool(shutil.which("ergo")),
                "weechat": bool(shutil.which("weechat")),
            },
            "env": {
                "ZCHAT_CMD": os.environ.get("ZCHAT_CMD", ""),
                "ZCHAT_HOME": os.environ.get("ZCHAT_HOME", ""),
            },
        }

    def _report_payload(self, session: Any, exitstatus: int) -> dict[str, Any]:
        finished_wall = datetime.now(timezone.utc)
        duration_s = (finished_wall - self.started_wall).total_seconds()
        cases = sorted(self.case_results.values(), key=lambda c: c["nodeid"])
        totals = {
            "total": len(cases),
            "passed": sum(1 for c in cases if c["status"] == "passed"),
            "failed": sum(1 for c in cases if c["status"] == "failed"),
            "skipped": sum(1 for c in cases if c["status"] == "skipped"),
            "unknown": sum(1 for c in cases if c["status"] == "unknown"),
        }
        gate_status, risks = self._gate_status(totals)
        modules = self._module_summary()
        checklist = self._checklist(modules)

        return {
            "schema_version": "1.0",
            "run": {
                "suite": "pre_release",
                "started_at_utc": self.started_at,
                "finished_at_utc": _utc_now_iso(),
                "duration_s": round(duration_s, 3),
                "exit_status": exitstatus,
                "pytest_args": list(getattr(session.config.invocation_params, "args", [])),
                "command": " ".join(sys.argv),
            },
            "summary": {
                **totals,
                "gate_status": gate_status,
                "gate_risks": risks,
            },
            "environment": self._environment(),
            "modules": modules,
            "cases": cases,
            "checklist": checklist,
            "artifacts": self.generated_paths,
        }

    def _render_markdown(self, payload: dict[str, Any]) -> str:
        summary = payload["summary"]
        run = payload["run"]
        env = payload["environment"]
        lines: list[str] = []
        lines.append("# Pre-release Test Report")
        lines.append("")
        lines.append("## 执行摘要")
        lines.append("")
        lines.append(f"- Gate: `{summary['gate_status']}`")
        lines.append(
            f"- Total: {summary['total']} / Passed: {summary['passed']} / Failed: {summary['failed']} "
            f"/ Skipped: {summary['skipped']} / Unknown: {summary['unknown']}"
        )
        lines.append(f"- Duration: {run['duration_s']}s")
        lines.append(f"- Command: `{run['command']}`")
        if summary["gate_risks"]:
            lines.append("- Risks:")
            for risk in summary["gate_risks"]:
                lines.append(f"  - {risk}")
        lines.append("")
        lines.append("## 环境快照")
        lines.append("")
        lines.append(f"- Timestamp (UTC): {env['timestamp_utc']}")
        lines.append(f"- OS: {env['os']}")
        lines.append(f"- Python: {env['python_version']}")
        lines.append(f"- zchat: {env['zchat_version']}")
        lines.append(
            "- Dependencies: "
            f"zellij={env['dependencies']['zellij']}, "
            f"ergo={env['dependencies']['ergo']}, "
            f"weechat={env['dependencies']['weechat']}"
        )
        lines.append("")
        lines.append("## 模块结果")
        lines.append("")
        lines.append("| Module | Passed | Failed | Skipped | Unknown | Duration(s) |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for module in payload["modules"]:
            lines.append(
                f"| `{module['module']}` | {module['passed']} | {module['failed']} | "
                f"{module['skipped']} | {module.get('unknown', 0)} | {module['duration_s']:.2f} |"
            )
        lines.append("")
        lines.append("## 发布检查清单")
        lines.append("")
        lines.append("| Item | Type | Status | Notes |")
        lines.append("|---|---|---|---|")
        for item in payload["checklist"]:
            lines.append(
                f"| {item['label']} | {item['type']} | {item['status_label']} | {item['notes']} |"
            )
        lines.append("")
        failed_cases = [c for c in payload["cases"] if c["status"] == "failed"]
        if failed_cases:
            lines.append("## 失败详情")
            lines.append("")
            for case in failed_cases:
                highlights = _extract_failure_highlights(case.get("failure", "") or "")
                lines.append(f"### `{case['nodeid']}`")
                lines.append("")
                lines.append("- 失败摘要")
                lines.append(
                    f"  - Headline: `{highlights['headline'] or '无可提取摘要'}`"
                )
                if highlights["error_line"]:
                    lines.append(f"  - Error: `{highlights['error_line']}`")
                if highlights["assertion_line"]:
                    lines.append(f"  - Assertion: `{highlights['assertion_line']}`")
                if highlights["hint"]:
                    lines.append(f"  - Hint: {highlights['hint']}")
                lines.append(f"- Duration: `{case['duration_s']:.2f}s`")
                lines.append(f"- Retries: `{case['retry_count']}`")
                lines.append("")
                if case["failure"]:
                    lines.append("<details>")
                    lines.append("<summary>展开原始 traceback</summary>")
                    lines.append("")
                    lines.append("```text")
                    lines.append(case["failure"])
                    lines.append("```")
                    lines.append("</details>")
                    lines.append("")
                if case["stderr_snippet"]:
                    lines.append("<details>")
                    lines.append("<summary>展开 stderr</summary>")
                    lines.append("")
                    lines.append("```text")
                    lines.append(case["stderr_snippet"])
                    lines.append("```")
                    lines.append("</details>")
                    lines.append("")
                if case["stdout_snippet"]:
                    lines.append("<details>")
                    lines.append("<summary>展开 stdout</summary>")
                    lines.append("")
                    lines.append("```text")
                    lines.append(case["stdout_snippet"])
                    lines.append("```")
                    lines.append("</details>")
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def finalize(self, session: Any, exitstatus: int) -> None:
        if not self.enabled:
            return
        if not self.case_seeds and not self.case_results:
            return
        try:
            report_dir_opt = self.config.getoption("pre_release_report_dir")
            if report_dir_opt:
                report_dir = Path(report_dir_opt)
            else:
                report_dir = Path(self.config.rootpath) / "tests" / "pre_release" / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)

            payload = self._report_payload(session, exitstatus)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            json_path = report_dir / f"pre-release-report-{stamp}.json"
            md_path = report_dir / f"pre-release-report-{stamp}.md"

            payload["artifacts"] = [
                _normalize_path(str(json_path)),
                _normalize_path(str(md_path)),
            ]
            json_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            md_path.write_text(self._render_markdown(payload), encoding="utf-8")

            self.generated_paths = payload["artifacts"]
        except Exception as exc:
            self.report_error = f"{exc}\n{traceback.format_exc()}"

