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
from zchat.cli.auth import device_code_flow, save_token, load_cached_token, refresh_token_if_needed

app = typer.Typer(name="zchat", help="Claude Code agent lifecycle management")
project_app = typer.Typer(help="Project configuration management")
irc_app = typer.Typer(help="IRC server and client management")
irc_daemon_app = typer.Typer(help="Local ergo IRC server")
agent_app = typer.Typer(help="Claude Code agent lifecycle")
setup_app = typer.Typer(help="Install and configure components")
template_app = typer.Typer(help="Agent template management")
auth_app = typer.Typer(help="Authentication management")

app.add_typer(project_app, name="project")
app.add_typer(irc_app, name="irc")
irc_app.add_typer(irc_daemon_app, name="daemon")
app.add_typer(agent_app, name="agent")
app.add_typer(setup_app, name="setup")
app.add_typer(template_app, name="template")
app.add_typer(auth_app, name="auth")


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
    from zchat.cli.auth import get_username
    cfg = _get_config(ctx)
    project_name = ctx.obj["project"]
    return AgentManager(
        irc_server=cfg["irc"]["server"],
        irc_port=cfg["irc"]["port"],
        irc_tls=cfg["irc"].get("tls", False),
        irc_password=cfg["irc"].get("password", ""),
        username=get_username(),
        default_channels=cfg["agents"]["default_channels"],
        env_file=cfg["agents"].get("env_file", ""),
        default_type=cfg["agents"].get("default_type", "claude"),
        tmux_session=_get_tmux_session(ctx),
        state_file=state_file_path(project_name),
        project_dir=project_dir(project_name),
    )


def _version_callback(value: bool):
    if value:
        from zchat._version import __version__
        typer.echo(f"zchat {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    project: Optional[str] = typer.Option(None, help="Project name (overrides auto-detection)"),
    version: bool = typer.Option(False, "--version", "-V", callback=_version_callback,
                                 is_eager=True, help="Show version and exit"),
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
def cmd_project_create(
    name: str,
    server: Optional[str] = typer.Option(None, help="IRC server address"),
    port: Optional[int] = typer.Option(None, help="IRC port"),
    tls: Optional[bool] = typer.Option(None, help="Enable TLS"),
    password: Optional[str] = typer.Option(None, help="IRC password"),
    channels: Optional[str] = typer.Option(None, help="Default channels (comma-separated)"),
    agent_type: Optional[str] = typer.Option(None, "--agent-type", help="Agent template name (e.g. 'claude')"),
    proxy: Optional[str] = typer.Option(None, help="HTTP proxy (ip:port, empty string for none)"),
):
    """Create a new project with config setup.

    When all required options are provided, runs non-interactively.
    Otherwise, prompts for missing values.
    """
    pdir = project_dir(name)
    if os.path.exists(pdir):
        typer.echo(f"Project '{name}' already exists.")
        raise typer.Exit(1)

    # --- IRC server ---
    _server: str
    _port: int
    _tls: bool
    _password: str
    if server is not None:
        _server = server
        if server == "zchat.inside.h2os.cloud":
            _port = port if port is not None else 6697
            _tls = tls if tls is not None else True
        else:
            _port = port if port is not None else 6667
            _tls = tls if tls is not None else False
        _password = password if password is not None else ""
    else:
        typer.echo("IRC Server:")
        typer.echo("  1) zchat.inside.h2os.cloud (recommended)")
        typer.echo("  2) Custom server")
        server_choice = typer.prompt("Choose", default="1")
        if server_choice == "1":
            _server = "zchat.inside.h2os.cloud"
            _port = 6697
            _tls = True
            _password = ""
        else:
            _server = typer.prompt("IRC server", default="127.0.0.1")
            _port = typer.prompt("IRC port", default=6667, type=int)
            _tls = typer.confirm("TLS", default=False)
            _password = typer.prompt("Password", default="", show_default=False)

    # --- Channels ---
    _channels: str = channels if channels is not None else typer.prompt("Default channels", default="#general")

    # --- Agent type ---
    from zchat.cli.template_loader import list_templates
    templates = list_templates()
    if not templates:
        typer.echo("Error: No agent templates found.")
        raise typer.Exit(1)

    if agent_type is not None:
        matched = [t for t in templates if t["template"]["name"] == agent_type]
        if not matched:
            typer.echo(f"Error: Agent type '{agent_type}' not found. Available: "
                       + ", ".join(t["template"]["name"] for t in templates))
            raise typer.Exit(1)
        default_type = agent_type
        selected_types = [agent_type]
    else:
        typer.echo("Agent types:")
        for i, tpl in enumerate(templates, 1):
            tname = tpl["template"]["name"]
            tdesc = tpl["template"].get("description", "")
            typer.echo(f"  {i}) {tname} - {tdesc}")
        selection = typer.prompt("Select types (comma-separated)", default="1")
        selected_indices = [int(s.strip()) - 1 for s in selection.split(",") if s.strip().isdigit()]
        selected_types = []
        for idx in selected_indices:
            if 0 <= idx < len(templates):
                selected_types.append(templates[idx]["template"]["name"])
        if not selected_types:
            selected_types = [templates[0]["template"]["name"]]
        default_type = selected_types[0]

    # --- Type-specific config: Claude ---
    env_file = ""
    if "claude" in selected_types:
        if proxy is not None:
            if proxy:
                proxy_url = proxy if proxy.startswith("http") else f"http://{proxy}"
                env_path = os.path.join(pdir, "claude.local.env")
                os.makedirs(pdir, exist_ok=True)
                with open(env_path, "w") as f:
                    f.write(f"HTTP_PROXY={proxy_url}\n")
                    f.write(f"HTTPS_PROXY={proxy_url}\n")
                env_file = env_path
        else:
            typer.echo("Claude configuration:")
            proxy_input = typer.prompt("  HTTP proxy (ip:port, leave empty for direct connection)",
                                       default="", show_default=False)
            if proxy_input:
                proxy_url = proxy_input if proxy_input.startswith("http") else f"http://{proxy_input}"
                env_path = os.path.join(pdir, "claude.local.env")
                os.makedirs(pdir, exist_ok=True)
                with open(env_path, "w") as f:
                    f.write(f"HTTP_PROXY={proxy_url}\n")
                    f.write(f"HTTPS_PROXY={proxy_url}\n")
                env_file = env_path

    create_project_config(name, server=_server, port=_port, tls=_tls,
                          password=_password, nick="", channels=_channels,
                          env_file=env_file, default_type=default_type)
    typer.echo(f"\nProject '{name}' created at {pdir}/")
    typer.echo(f"Config saved to {pdir}/config.toml")
    if env_file:
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
    # Attach to the project's tmux session if it exists
    import subprocess
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True,
    )
    if result.returncode != 0:
        typer.echo(
            f"Session not running. Use 'zchat irc start' to start it."
        )
        return
    if os.environ.get("TMUX"):
        subprocess.run(["tmux", "switch-client", "-t", session_name])
    else:
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
        from zchat.cli.auth import get_username
        cfg = load_project_config(name)
        mgr = AgentManager(
            irc_server=cfg["irc"]["server"], irc_port=cfg["irc"]["port"],
            irc_tls=cfg["irc"].get("tls", False),
            irc_password=cfg["irc"].get("password", ""),
            username=get_username(),
            default_channels=cfg["agents"]["default_channels"],
            state_file=state_file_path(name),
        )
        running = [n for n, i in mgr.list_agents().items() if i["status"] == "running"]
        if running:
            typer.echo(f"Error: Running agents: {', '.join(running)}. Stop them first.")
            raise typer.Exit(1)
    except (FileNotFoundError, RuntimeError):
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


@app.command("set")
def cmd_set(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Config key (dotted, e.g. agents.default_type)"),
    value: str = typer.Argument(..., help="Value to set"),
):
    """Set a project config value."""
    from zchat.cli.project import set_config_value
    project_name = ctx.obj.get("project")
    if not project_name:
        typer.echo("Error: No project selected.")
        raise typer.Exit(1)
    set_config_value(project_name, key, value)
    typer.echo(f"Set {key} = {value}")


# ============================================================
# auth commands
# ============================================================

@auth_app.command("login")
def cmd_auth_login(
    issuer: str = typer.Option("https://6fzzkh.logto.app/", help="OIDC issuer URL"),
    client_id: str = typer.Option("t7ddhdfqrfgwpmounxdsx", help="OIDC client ID"),
    method: str = typer.Option("oidc", help="Auth method: oidc or local"),
    username: str = typer.Option("", help="Username for local method"),
):
    """Authenticate via OIDC device code flow or set local username."""
    from zchat.cli.auth import _global_auth_dir, _sanitize_irc_nick
    auth_dir = _global_auth_dir()
    existing = load_cached_token(auth_dir)
    if existing:
        typer.echo(f"Already logged in as: {existing.get('username', '?')} ({existing.get('email', '')})")
        typer.echo("Run 'zchat auth logout' first to re-login.")
        raise typer.Exit(0)

    if method == "local":
        if not username:
            typer.echo("Error: --username is required for --method local")
            raise typer.Exit(1)
        nick = _sanitize_irc_nick(username)
        if not nick:
            typer.echo(f"Error: '{username}' is not a valid IRC nick")
            raise typer.Exit(1)
        save_token(auth_dir, {"username": nick})
        typer.echo(f"Username set: {nick}")
        return

    # OIDC device code flow (default)
    try:
        result = device_code_flow(issuer=issuer, client_id=client_id)
    except Exception as e:
        typer.echo(f"Login failed: {e}")
        raise typer.Exit(1)
    email = result.get("email", result["username"])
    nick = _sanitize_irc_nick(email.split("@")[0] if "@" in email else email)
    result["username"] = nick
    save_token(auth_dir, result)
    typer.echo(f"\nLogged in as: {nick} ({email})")


@auth_app.command("status")
def cmd_auth_status():
    """Show current authentication status."""
    from zchat.cli.auth import _global_auth_dir
    data = load_cached_token(_global_auth_dir())
    if data:
        import datetime
        exp = datetime.datetime.fromtimestamp(data["expires_at"])
        typer.echo(f"Username: {data['username']}")
        typer.echo(f"Token expires: {exp.isoformat()}")
    else:
        typer.echo("Not logged in. Run 'zchat auth login'.")


@auth_app.command("refresh")
def cmd_auth_refresh():
    """Manually refresh access token."""
    import json
    from zchat.cli.auth import _global_auth_dir
    auth_path = os.path.join(_global_auth_dir(), "auth.json")
    if not os.path.isfile(auth_path):
        typer.echo("Not logged in. Run 'zchat auth login'.")
        raise typer.Exit(1)
    with open(auth_path) as f:
        data = json.load(f)
    token_endpoint = data.get("token_endpoint", "")
    client_id = data.get("client_id", "")
    if not token_endpoint or not client_id:
        typer.echo("Token data incomplete. Run 'zchat auth login' again.")
        raise typer.Exit(1)
    result = refresh_token_if_needed(
        _global_auth_dir(),
        token_endpoint=token_endpoint,
        client_id=client_id,
    )
    if result:
        typer.echo(f"Token refreshed for {result['username']}")
    else:
        typer.echo("Refresh failed. Run 'zchat auth login'.")
        raise typer.Exit(1)


@auth_app.command("logout")
def cmd_auth_logout():
    """Clear cached authentication tokens."""
    from zchat.cli.auth import _global_auth_dir
    auth_path = os.path.join(_global_auth_dir(), "auth.json")
    if os.path.isfile(auth_path):
        os.remove(auth_path)
        typer.echo("Logged out.")
    else:
        typer.echo("Not logged in.")


# ============================================================
# template commands
# ============================================================

@template_app.command("list")
def cmd_template_list():
    """List available agent templates."""
    from zchat.cli.template_loader import list_templates
    templates = list_templates()
    if not templates:
        typer.echo("No templates found.")
        return
    for tpl in templates:
        name = tpl["template"]["name"]
        desc = tpl["template"].get("description", "")
        source = tpl.get("source", "")
        typer.echo(f"  {name}\t{desc}\t({source})")


@template_app.command("show")
def cmd_template_show(name: str = typer.Argument(..., help="Template name")):
    """Show template details."""
    from zchat.cli.template_loader import load_template, resolve_template_dir
    try:
        tpl = load_template(name)
        tpl_dir = resolve_template_dir(name)
    except Exception as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(1)
    typer.echo(f"Template: {tpl['template']['name']}")
    typer.echo(f"  Description: {tpl['template'].get('description', '')}")
    typer.echo(f"  Location: {tpl_dir}")
    typer.echo(f"  pre_stop: {tpl['hooks'].get('pre_stop', '')!r}")


@template_app.command("set")
def cmd_template_set(
    name: str = typer.Argument(..., help="Template name"),
    key: str = typer.Argument(..., help="Environment variable name"),
    value: str = typer.Argument(..., help="Value"),
):
    """Set a template .env variable."""
    from zchat.cli.template_loader import resolve_template_dir, _parse_env_file
    from zchat.cli.project import ZCHAT_DIR
    try:
        tpl_dir = resolve_template_dir(name)
    except Exception as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(1)
    # If template is built-in (inside package), .env goes to user dir
    user_tpl_dir = os.path.join(ZCHAT_DIR, "templates", name)
    if not tpl_dir.startswith(ZCHAT_DIR):
        os.makedirs(user_tpl_dir, exist_ok=True)
        env_path = os.path.join(user_tpl_dir, ".env")
    else:
        env_path = os.path.join(tpl_dir, ".env")
    env = _parse_env_file(env_path)
    env[key] = value
    with open(env_path, "w") as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")
    typer.echo(f"Set {key} in {name} template .env")


@template_app.command("create")
def cmd_template_create(name: str = typer.Argument(..., help="Template name")):
    """Create an empty template scaffold."""
    from zchat.cli.project import ZCHAT_DIR
    tpl_dir = os.path.join(ZCHAT_DIR, "templates", name)
    if os.path.exists(tpl_dir):
        typer.echo(f"Template '{name}' already exists at {tpl_dir}")
        raise typer.Exit(1)
    os.makedirs(tpl_dir)
    with open(os.path.join(tpl_dir, "template.toml"), "w") as f:
        f.write(f'[template]\nname = "{name}"\ndescription = ""\n\n[hooks]\npre_stop = ""\n')
    with open(os.path.join(tpl_dir, "start.sh"), "w") as f:
        f.write("#!/bin/bash\nset -euo pipefail\nexec echo \"TODO: implement start script\"\n")
    os.chmod(os.path.join(tpl_dir, "start.sh"), 0o755)
    with open(os.path.join(tpl_dir, ".env.example"), "w") as f:
        f.write("# Auto-injected by zchat\nAGENT_NAME={{agent_name}}\nIRC_SERVER={{irc_server}}\n"
                "IRC_PORT={{irc_port}}\nIRC_CHANNELS={{irc_channels}}\nIRC_TLS={{irc_tls}}\n"
                "IRC_PASSWORD={{irc_password}}\nWORKSPACE={{workspace}}\n")
    typer.echo(f"Created template scaffold at {tpl_dir}/")


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
        typer.echo(f"  status: running (window {s['weechat'].get('window', 'unknown')})")
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
    agent_type: Optional[str] = typer.Option(None, "--type", "-t", help="Template type (default: from config)"),
):
    """Create and launch a new agent."""
    mgr = _get_agent_manager(ctx)
    ch = [c.strip() for c in channels.split(",")] if channels else None
    info = mgr.create(name, workspace=workspace, channels=ch, agent_type=agent_type)
    scoped = mgr.scoped(name)
    typer.echo(f"Created {scoped} (type: {info['type']})")
    typer.echo(f"  window: {info['window_name']}")
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
        window = info.get("window_name", info.get("pane_id", "—"))
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
        agent_type = info.get("type", "unknown")
        ch = ", ".join(info.get("channels", []))
        typer.echo(f"  {name}\t{agent_type}\t{status}\t{uptime}\t{window}\t{ch}\t{ws}")

@agent_app.command("status")
def cmd_agent_status(ctx: typer.Context, name: str = typer.Argument(...)):
    """Show detailed info for a single agent."""
    mgr = _get_agent_manager(ctx)
    info = mgr.get_status(name)
    scoped = mgr.scoped(name)
    elapsed = time.time() - info.get("created_at", time.time())
    mins, secs = divmod(int(elapsed), 60)
    typer.echo(f"{scoped}")
    typer.echo(f"  type:      {info.get('type', 'unknown')}")
    typer.echo(f"  status:    {info['status']}")
    typer.echo(f"  uptime:    {mins}m {secs}s")
    typer.echo(f"  window:    {info.get('window_name', info.get('pane_id', '—'))}")
    typer.echo(f"  workspace: {info.get('workspace', '—')}")
    typer.echo(f"  channels:  {', '.join(info.get('channels', []))}")

@agent_app.command("send")
def cmd_agent_send(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    text: str = typer.Argument(..., help="Text to send to agent's tmux window"),
):
    """Send text to agent's tmux window (tmux send-keys)."""

    mgr = _get_agent_manager(ctx)
    scoped = mgr.scoped(name)
    mgr.send(name, text)
    typer.echo(f"Sent to {scoped}")

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
    """Stop all agents + WeeChat + ergo + tmux session."""
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
    # Kill tmux session
    try:
        session_name = _get_tmux_session(ctx)
        from zchat.cli.tmux import get_session
        session = get_session(session_name)
        session.kill()
    except (KeyError, SystemExit, Exception):
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
        [python, "-m", "pip", "install", "--force-reinstall", "--no-deps",
         "--ignore-installed"] + _GIT_REPOS,
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
