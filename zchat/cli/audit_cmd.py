"""audit CLI — 读 audit plugin 的 state.json 输出状态和报告。

管理型 agent 通过 run_zchat_cli(["audit", "status"]) 或 ["audit", "report"] 取数。

V7 (2026-04-22) 起：audit plugin state 路径改为
    <project_dir>/plugins/audit/state.json
(V6 的 <project_dir>/audit.json 已废弃。如果 plugins.toml 显式 override 了
audit.data_dir，本 CLI 仍读默认路径——生产环境 operator 不应手动 override。)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import typer


audit_app = typer.Typer(name="audit", help="Read audit plugin state for channel statistics.")


def _resolve_audit_path(ctx: typer.Context) -> Path:
    """定位 audit plugin state.json。

    V7 路径：<project_dir>/plugins/audit/state.json
    """
    project_name = ctx.obj.get("project") if ctx.obj else None
    if project_name:
        from zchat.cli.paths import project_dir
        return Path(project_dir(project_name)) / "plugins" / "audit" / "state.json"

    return Path("plugins/audit/state.json")


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"channels": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"channels": {}}


def _compute_aggregates(state: dict[str, Any]) -> dict[str, Any]:
    channels = (state.get("channels") or {}).values()
    total_takeovers = 0
    total_resolved = 0
    takeover_then_resolve = 0
    csat_scores: list[int] = []
    for ch in channels:
        takeovers = ch.get("takeovers") or []
        total_takeovers += len(takeovers)
        if ch.get("state") == "resolved":
            total_resolved += 1
            if takeovers:
                takeover_then_resolve += 1
        if ch.get("csat_score") is not None:
            csat_scores.append(ch["csat_score"])
    esc_rate = (
        takeover_then_resolve / total_takeovers if total_takeovers else 0.0
    )
    csat_mean = sum(csat_scores) / len(csat_scores) if csat_scores else None
    return {
        "total_channels": len((state.get("channels") or {})),
        "total_takeovers": total_takeovers,
        "total_resolved": total_resolved,
        "escalation_resolve_rate": round(esc_rate, 3),
        "csat_mean": round(csat_mean, 2) if csat_mean is not None else None,
    }


@audit_app.command("status")
def cmd_audit_status(
    ctx: typer.Context,
    channel: Optional[str] = typer.Option(None, "--channel", "-c",
                                          help="Only show status for this channel"),
    json_out: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show active channels and their state. Reads audit.json.

    Without --channel: list all channels + aggregates.
    With --channel X: show detailed status for channel X.
    """
    path = _resolve_audit_path(ctx)
    state = _load_state(path)

    if channel:
        ch = state.get("channels", {}).get(channel)
        if ch is None:
            typer.echo(f"Channel '{channel}' not found in {path}", err=True)
            raise typer.Exit(1)
        if json_out:
            typer.echo(json.dumps(ch, ensure_ascii=False, indent=2))
        else:
            typer.echo(f"Channel: {channel}")
            typer.echo(f"  state: {ch.get('state')}")
            typer.echo(f"  created_at: {ch.get('created_at')}")
            typer.echo(f"  first_reply_at: {ch.get('first_reply_at')}")
            typer.echo(f"  resolved_at: {ch.get('resolved_at')}")
            typer.echo(f"  message_count: {ch.get('message_count', 0)}")
            typer.echo(f"  takeovers: {len(ch.get('takeovers') or [])}")
            typer.echo(f"  csat_score: {ch.get('csat_score')}")
        return

    agg = _compute_aggregates(state)
    if json_out:
        typer.echo(json.dumps({
            "channels": state.get("channels", {}),
            "aggregates": agg,
        }, ensure_ascii=False, indent=2))
        return

    typer.echo(f"Audit status (from {path})")
    typer.echo(f"  total channels: {agg['total_channels']}")
    typer.echo(f"  total takeovers: {agg['total_takeovers']}")
    typer.echo(f"  total resolved: {agg['total_resolved']}")
    typer.echo(f"  escalation→resolve rate: {agg['escalation_resolve_rate']:.1%}")
    if agg["csat_mean"] is not None:
        typer.echo(f"  CSAT mean: {agg['csat_mean']:.2f}")

    # 活跃 channel 列表
    active = [
        (ch_id, ch) for ch_id, ch in (state.get("channels") or {}).items()
        if ch.get("state") != "resolved"
    ]
    if active:
        typer.echo("\nActive channels:")
        for ch_id, ch in active:
            tkv = len(ch.get("takeovers") or [])
            typer.echo(f"  {ch_id}\tstate={ch.get('state')}\tmessages={ch.get('message_count', 0)}\ttakeovers={tkv}")


@audit_app.command("report")
def cmd_audit_report(
    ctx: typer.Context,
    json_out: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Aggregate report: 接管次数 / CSAT / 升级转结案率 / 总 channel 数。"""
    path = _resolve_audit_path(ctx)
    state = _load_state(path)
    agg = _compute_aggregates(state)

    if json_out:
        typer.echo(json.dumps(agg, ensure_ascii=False, indent=2))
        return

    typer.echo("Audit report")
    typer.echo(f"  total channels: {agg['total_channels']}")
    typer.echo(f"  total takeovers: {agg['total_takeovers']}")
    typer.echo(f"  total resolved: {agg['total_resolved']}")
    typer.echo(f"  escalation→resolve rate: {agg['escalation_resolve_rate']:.1%}")
    if agg["csat_mean"] is not None:
        typer.echo(f"  CSAT mean: {agg['csat_mean']:.2f}")
    else:
        typer.echo("  CSAT: no scores yet")


@audit_app.command("export")
def cmd_audit_export(
    ctx: typer.Context,
    output: Optional[Path] = typer.Option(None, "--output", "-o",
                                           help="Output file path (default stdout)"),
):
    """Export raw audit.json."""
    path = _resolve_audit_path(ctx)
    state = _load_state(path)
    data = json.dumps(state, ensure_ascii=False, indent=2)
    if output:
        output.write_text(data, encoding="utf-8")
        typer.echo(f"Exported to {output}")
    else:
        typer.echo(data)
