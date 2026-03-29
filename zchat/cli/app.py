#!/usr/bin/env python3
"""zchat: Claude Code agent lifecycle management CLI."""
from __future__ import annotations

import os
import time
from typing import Optional

import typer


from zchat.cli.project import (
    ZCHAT_DIR, create_project_config, list_projects,
    get_default_project, set_default_project, resolve_project,
    load_project_config, remove_project, project_dir, state_file_path,
)
from zchat.cli.agent_manager import AgentManager
from zchat.cli.irc_manager import IrcManager

app = typer.Typer(name="zchat", help="Claude Code agent lifecycle management")
project_app = typer.Typer(help="Project configuration management")
irc_app = typer.Typer(help="IRC server and client management")
irc_daemon_app = typer.Typer(help="Local ergo IRC server")
agent_app = typer.Typer(help="Claude Code agent lifecycle")
setup_app = typer.Typer(help="Install and configure components")

app.add_typer(project_app, name="project")
app.add_typer(irc_app, name="irc")
irc_app.add_typer(irc_daemon_app, name="daemon")
app.add_typer(agent_app, name="agent")
app.add_typer(setup_app, name="setup")


def _get_config(ctx: typer.Context) -> dict:
    cfg = ctx.obj.get("config") if ctx.obj else None
    if not cfg:
        typer.echo("Error: No project selected. Run 'zchat project create <name>' or use '--project <name>'.")
        raise typer.Exit(1)
    return cfg


def _get_tmux_session(ctx: typer.Context) -> str:
    """Get tmux session name from project config."""
    cfg = _get_config(ctx)
    session = cfg.get("tmux", {}).get("session")
    if not session:
        # Fallback for projects created before tmux session tracking
        project_name = ctx.obj["project"]
        session = f"zchat-{project_name}"
    return session


def _get_irc_manager(ctx: typer.Context) -> IrcManager:
    cfg = _get_config(ctx)
    project_name = ctx.obj["project"]
    return IrcManager(
        config=cfg,
        state_file=state_file_path(project_name),
        tmux_session=_get_tmux_session(ctx),
    )


def _get_agent_manager(ctx: typer.Context) -> AgentManager:
    cfg = _get_config(ctx)
    project_name = ctx.obj["project"]
    return AgentManager(
        irc_server=cfg["irc"]["server"],
        irc_port=cfg["irc"]["port"],
        irc_tls=cfg["irc"].get("tls", False),
        username=cfg["agents"]["username"],
        default_channels=cfg["agents"]["default_channels"],
        env_file=cfg["agents"].get("env_file", ""),
        claude_args=cfg["agents"].get("claude_args"),
        mcp_server_cmd=cfg["agents"].get("mcp_server_cmd"),
        tmux_session=_get_tmux_session(ctx),
        state_file=state_file_path(project_name),
    )


@app.callback()
def main(
    ctx: typer.Context,
    project: Optional[str] = typer.Option(None, help="Project name (overrides auto-detection)"),
):
    """Claude Code agent lifecycle management."""
    ctx.ensure_object(dict)

    resolved = resolve_project(explicit=project)
    if resolved:
        try:
            ctx.obj["project"] = resolved
            ctx.obj["config"] = load_project_config(resolved)
        except FileNotFoundError:
            if ctx.invoked_subcommand not in ("project", "doctor", "setup"):
                typer.echo(f"Error: Project '{resolved}' not found. Run 'zchat project create {resolved}'.")
                raise typer.Exit(1)


# ============================================================
# project commands
# ============================================================

@project_app.command("create")
def cmd_project_create(name: str):
    """Create a new project with interactive config setup."""
    pdir = project_dir(name)
    if os.path.exists(pdir):
        typer.echo(f"Project '{name}' already exists.")
        raise typer.Exit(1)
    server = typer.prompt("IRC server", default="127.0.0.1")
    port = typer.prompt("IRC port", default=6667, type=int)
    tls = typer.confirm("TLS", default=False)
    password = typer.prompt("Password", default="", show_default=False)
    nick = typer.prompt("Nickname", default=os.environ.get("USER", "user"))
    channels = typer.prompt("Default channels", default="#general")
    proxy = typer.prompt("HTTP proxy (ip:port, leave empty for direct connection)",
                         default="", show_default=False)

    # Generate env file if proxy is set
    env_file = ""
    if proxy:
        proxy_url = proxy if proxy.startswith("http") else f"http://{proxy}"
        env_path = os.path.join(pdir, "claude.local.env")
        os.makedirs(pdir, exist_ok=True)
        with open(env_path, "w") as f:
            f.write(f"HTTP_PROXY={proxy_url}\n")
            f.write(f"HTTPS_PROXY={proxy_url}\n")
        env_file = env_path

    create_project_config(name, server=server, port=port, tls=tls,
                          password=password, nick=nick, channels=channels,
                          env_file=env_file)
    typer.echo(f"\nProject '{name}' created at {pdir}/")
    typer.echo(f"Config saved to {pdir}/config.toml")
    if proxy:
        typer.echo(f"Proxy config saved to {pdir}/claude.local.env")

@project_app.command("list")
def cmd_project_list():
    """List all projects."""
    projects = list_projects()
    default = get_default_project()
    if not projects:
        typer.echo("No projects. Run 'zchat project create <name>'.")
        return
    for p in projects:
        marker = " (default)" if p == default else ""
        typer.echo(f"  {p}{marker}")

@project_app.command("use")
def cmd_project_use(name: str):
    """Set default project and attach to its tmux session."""
    if not os.path.isdir(project_dir(name)):
        typer.echo(f"Project '{name}' does not exist.")
        raise typer.Exit(1)
    set_default_project(name)
    cfg = load_project_config(name)
    session_name = cfg.get("tmux", {}).get("session", f"zchat-{name}")
    typer.echo(f"Default project set to '{name}'.")
    # Attach to the project's tmux session
    import subprocess
    if os.environ.get("TMUX"):
        # Already inside tmux — switch client
        subprocess.run(["tmux", "switch-client", "-t", session_name])
    else:
        # Outside tmux — attach
        subprocess.run(["tmux", "attach", "-t", session_name])

@project_app.command("remove")
def cmd_project_remove(name: str):
    """Remove a project and its state."""
    pdir = project_dir(name)
    if not os.path.isdir(pdir):
        typer.echo(f"Project '{name}' does not exist.")
        raise typer.Exit(1)
    # Safety: check for running agents
    try:
        cfg = load_project_config(name)
        mgr = AgentManager(
            irc_server=cfg["irc"]["server"], irc_port=cfg["irc"]["port"],
            irc_tls=cfg["irc"].get("tls", False),
            username=cfg["agents"]["username"],
            default_channels=cfg["agents"]["default_channels"],
            state_file=state_file_path(name),
        )
        running = [n for n, i in mgr.list_agents().items() if i["status"] == "running"]
        if running:
            typer.echo(f"Error: Running agents: {', '.join(running)}. Stop them first.")
            raise typer.Exit(1)
    except FileNotFoundError:
        pass
    remove_project(name)
    typer.echo(f"Project '{name}' removed.")

@project_app.command("show")
def cmd_project_show(name: Optional[str] = typer.Argument(None)):
    """Show project config."""
    if not name:
        name = resolve_project()
    if not name:
        typer.echo("No project selected.")
        raise typer.Exit(1)
    try:
        cfg = load_project_config(name)
    except FileNotFoundError:
        typer.echo(f"Project '{name}' does not exist.")
        raise typer.Exit(1)
    typer.echo(f"Project: {name}")
    typer.echo(f"  IRC server: {cfg['irc']['server']}:{cfg['irc']['port']}")
    typer.echo(f"  TLS: {cfg['irc']['tls']}")
    typer.echo(f"  Nickname: {cfg['agents']['username']}")
    typer.echo(f"  Channels: {', '.join(cfg['agents']['default_channels'])}")


# ============================================================
# irc daemon commands
# ============================================================

@irc_daemon_app.command("start")
def cmd_irc_daemon_start(
    ctx: typer.Context,
    port: Optional[int] = typer.Option(None, help="Override IRC port from config"),
):
    """Start local ergo IRC server."""
    mgr = _get_irc_manager(ctx)
    mgr.daemon_start(port_override=port)

@irc_daemon_app.command("stop")
def cmd_irc_daemon_stop(ctx: typer.Context):
    """Stop local ergo IRC server."""
    mgr = _get_irc_manager(ctx)
    mgr.daemon_stop()


# ============================================================
# irc client commands
# ============================================================

@irc_app.command("start")
def cmd_irc_start(
    ctx: typer.Context,
    nick: Optional[str] = typer.Option(None, help="Override nickname from config"),
):
    """Start WeeChat in tmux, auto-connect to IRC."""

    mgr = _get_irc_manager(ctx)
    mgr.start_weechat(nick_override=nick)

@irc_app.command("stop")
def cmd_irc_stop(ctx: typer.Context):
    """Stop WeeChat."""
    mgr = _get_irc_manager(ctx)
    mgr.stop_weechat()

@irc_app.command("status")
def cmd_irc_status(ctx: typer.Context):
    """Show IRC server and client status."""
    mgr = _get_irc_manager(ctx)
    s = mgr.status()
    typer.echo("IRC Server:")
    if s["daemon"]["running"]:
        typer.echo(f"  status: running (pid {s['daemon']['pid'] or 'unknown'})")
    else:
        typer.echo("  status: stopped")
    typer.echo(f"  server: {s['daemon']['server']}:{s['daemon']['port']}")
    typer.echo("")
    typer.echo("IRC Client (WeeChat):")
    if s["weechat"]["running"]:
        typer.echo(f"  status: running (pane {s['weechat']['pane_id']})")
    else:
        typer.echo("  status: stopped")
    typer.echo(f"  nick: {s['weechat']['nick']}")


# ============================================================
# agent commands
# ============================================================

@agent_app.command("create")
def cmd_agent_create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    workspace: Optional[str] = typer.Option(None, help="Custom workspace path"),
    channels: Optional[str] = typer.Option(None, help="Comma-separated channels to join"),
):
    """Create and launch a new agent."""

    mgr = _get_agent_manager(ctx)
    ch = [c.strip() for c in channels.split(",")] if channels else None
    info = mgr.create(name, workspace=workspace, channels=ch)
    scoped = mgr.scoped(name)
    typer.echo(f"Created {scoped}")
    typer.echo(f"  pane: {info['pane_id']}")
    typer.echo(f"  workspace: {info['workspace']}")

@agent_app.command("stop")
def cmd_agent_stop(ctx: typer.Context, name: str = typer.Argument(...)):
    """Stop a running agent."""
    mgr = _get_agent_manager(ctx)
    scoped = mgr.scoped(name)
    mgr.stop(name, force=True)
    typer.echo(f"Stopped {scoped}")

@agent_app.command("list")
def cmd_agent_list(ctx: typer.Context):
    """List all agents with status."""
    mgr = _get_agent_manager(ctx)
    agents = mgr.list_agents()
    if not agents:
        typer.echo("No agents")
        return
    for name, info in agents.items():
        status = info["status"]
        pane = info.get("pane_id", "—")
        ws = info.get("workspace", "—")
        elapsed = time.time() - info.get("created_at", time.time())
        if status != "offline" and elapsed > 0:
            if elapsed >= 3600:
                uptime = f"{elapsed / 3600:.0f}h"
            elif elapsed >= 60:
                uptime = f"{elapsed / 60:.0f}m"
            else:
                uptime = f"{elapsed:.0f}s"
        else:
            uptime = "—"
        ch = ", ".join(info.get("channels", []))
        typer.echo(f"  {name}\t{status}\t{uptime}\t{pane}\t{ch}\t{ws}")

@agent_app.command("status")
def cmd_agent_status(ctx: typer.Context, name: str = typer.Argument(...)):
    """Show detailed info for a single agent."""
    mgr = _get_agent_manager(ctx)
    info = mgr.get_status(name)
    scoped = mgr.scoped(name)
    elapsed = time.time() - info.get("created_at", time.time())
    mins, secs = divmod(int(elapsed), 60)
    typer.echo(f"{scoped}")
    typer.echo(f"  status:    {info['status']}")
    typer.echo(f"  uptime:    {mins}m {secs}s")
    typer.echo(f"  pane:      {info.get('pane_id', '—')}")
    typer.echo(f"  workspace: {info.get('workspace', '—')}")
    typer.echo(f"  channels:  {', '.join(info.get('channels', []))}")

@agent_app.command("send")
def cmd_agent_send(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    text: str = typer.Argument(..., help="Text to send to agent's tmux pane"),
):
    """Send text to agent's tmux pane (tmux send-keys)."""

    mgr = _get_agent_manager(ctx)
    scoped = mgr.scoped(name)
    mgr.send(name, text)
    typer.echo(f"Sent to {scoped} (pane {mgr._agents[scoped]['pane_id']})")

@agent_app.command("restart")
def cmd_agent_restart(ctx: typer.Context, name: str = typer.Argument(...)):
    """Restart an agent (stop + create with same config)."""

    mgr = _get_agent_manager(ctx)
    scoped = mgr.scoped(name)
    mgr.restart(name)
    typer.echo(f"Restarted {scoped}")


# ============================================================
# shutdown
# ============================================================

@app.command("shutdown")
def cmd_shutdown(ctx: typer.Context):
    """Stop all agents + WeeChat + ergo."""
    try:
        mgr = _get_agent_manager(ctx)
        agents = mgr.list_agents()
        for name in list(agents.keys()):
            if agents[name]["status"] != "offline":
                mgr.stop(name, force=True)
                typer.echo(f"Stopped {name}")
    except (SystemExit, Exception):
        pass
    try:
        irc = _get_irc_manager(ctx)
        irc.stop_weechat()
        irc.daemon_stop()
    except (SystemExit, Exception):
        pass
    typer.echo("Shutdown complete.")


# ============================================================
# doctor
# ============================================================

@app.command("doctor")
def cmd_doctor():
    """Check environment dependencies and project status."""
    from zchat.cli.doctor import run_doctor
    run_doctor()


# ============================================================
# setup commands
# ============================================================

@setup_app.command("weechat")
def cmd_setup_weechat(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing plugin"),
):
    """Download and install the WeeChat zchat plugin."""
    from zchat.cli.doctor import setup_weechat
    setup_weechat(force=force)


# ============================================================
# self-update
# ============================================================

_GIT_REPOS = [
    "zchat-protocol @ git+https://github.com/ezagent42/zchat-protocol.git@main",
    "zchat-channel-server @ git+https://github.com/ezagent42/claude-zchat-channel.git@main",
    "zchat @ git+https://github.com/ezagent42/zchat.git@main",
]


@app.command("self-update")
def cmd_self_update():
    """Update zchat to the latest version from GitHub."""
    import subprocess
    import sys

    python = sys.executable
    typer.echo("Updating zchat from GitHub (main)...")
    result = subprocess.run(
        [python, "-m", "pip", "install", "--force-reinstall", "--no-deps"] + _GIT_REPOS,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        typer.echo(f"Error:\n{result.stderr}")
        raise typer.Exit(1)

    # Show installed commit
    result2 = subprocess.run(
        [python, "-m", "pip", "show", "zchat"],
        capture_output=True, text=True,
    )
    for line in result2.stdout.splitlines():
        if line.startswith("Version:"):
            typer.echo(f"Updated to {line}")
            break
    typer.echo("Done. Restart any running zchat commands to use the new version.")


if __name__ == "__main__":
    app()
