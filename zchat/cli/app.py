#!/usr/bin/env python3
"""zchat: Claude Code agent lifecycle management CLI."""
from __future__ import annotations

import os
import subprocess
import time
from typing import Optional

import typer


from zchat.cli import paths
from zchat.cli.project import (
    create_project_config, list_projects,
    get_default_project, set_default_project, resolve_project,
    load_project_config, remove_project, project_dir, state_file_path,
    normalize_channel_name,
)
from zchat.cli.agent_manager import AgentManager
from zchat.cli.irc_manager import IrcManager
from zchat.cli.auth import device_code_flow, save_token, load_cached_token, refresh_token_if_needed
from zchat.cli.update import (
    load_update_state, save_update_state, should_check_today,
    check_for_updates, run_upgrade, UPDATE_STATE_FILE,
)
from zchat.cli.config_cmd import (
    load_global_config, save_global_config,
    get_config_value, set_config_value,
    resolve_server, ensure_server_in_global,
)
from zchat.cli.audit_cmd import audit_app

app = typer.Typer(name="zchat", help="Claude Code agent lifecycle management")
project_app = typer.Typer(help="Project configuration management")
irc_app = typer.Typer(help="IRC server and client management")
irc_daemon_app = typer.Typer(help="Local ergo IRC server")
agent_app = typer.Typer(help="Claude Code agent lifecycle")
setup_app = typer.Typer(help="Install and configure components")
template_app = typer.Typer(help="Agent template management")
auth_app = typer.Typer(help="Authentication management")
config_app = typer.Typer(help="Global configuration management")
channel_app = typer.Typer(help="Channel registration and management")
bot_app = typer.Typer(help="External bot registration and management")
voice_app = typer.Typer(help="Voice overlay — 临时语音通话 bridge")

app.add_typer(project_app, name="project")
app.add_typer(irc_app, name="irc")
irc_app.add_typer(irc_daemon_app, name="daemon")
app.add_typer(agent_app, name="agent")
app.add_typer(setup_app, name="setup")
app.add_typer(template_app, name="template")
app.add_typer(auth_app, name="auth")
app.add_typer(config_app, name="config")
app.add_typer(channel_app, name="channel")
app.add_typer(bot_app, name="bot")
app.add_typer(audit_app, name="audit")
app.add_typer(voice_app, name="voice")


def _get_config(ctx: typer.Context) -> dict:
    cfg = ctx.obj.get("config") if ctx.obj else None
    if not cfg:
        typer.echo("Error: No project selected. Run 'zchat project create <name>' or use '--project <name>'.")
        raise typer.Exit(1)
    return cfg


def _prompt_new_server(global_cfg: dict) -> str:
    """Interactive prompt to add a new IRC server to global config."""
    from zchat.cli.defaults import server_presets
    presets = server_presets()
    preset_names = list(presets.keys())

    typer.echo("Add new IRC server:")
    for i, name in enumerate(preset_names, 1):
        typer.echo(f"  {i}) {presets[name].get('label', name)}")
    typer.echo(f"  {len(preset_names) + 1}) Custom")
    choice = typer.prompt("Choose", default="1")

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(preset_names):
            name = preset_names[idx]
            p = presets[name]
            ensure_server_in_global(name, p["host"], p["port"], p.get("tls", False), "", global_cfg)
            return name
    except (ValueError, IndexError):
        pass

    # Custom
    host = typer.prompt("Hostname", default="127.0.0.1")
    port = typer.prompt("Port", default=6667, type=int)
    use_tls = typer.confirm("TLS", default=False)
    pw = typer.prompt("Password", default="", show_default=False)
    server_name = host.replace(".", "-").split(":")[0]
    if server_name in ("127-0-0-1", "localhost"):
        server_name = "local"
    ensure_server_in_global(server_name, host, port, use_tls, pw, global_cfg)
    return server_name


def _get_irc_config(cfg: dict) -> dict:
    """Resolve IRC connection details from project config + global config.

    Idempotent: if cfg already has an injected irc dict (with host/port),
    returns it. Only treats cfg as "old format" if [irc] section lacks
    new-format fields (host/port = injected keys).
    """
    existing = cfg.get("irc")
    if isinstance(existing, dict):
        if "host" in existing or "port" in existing:
            # Already injected by an earlier call in this ctx; return as-is
            return existing
        # Legacy [irc] section (no host/port) — reject
        raise SystemExit(
            f"Error: Project uses old config format ([irc] section).\n"
            f"Please delete the project and recreate it:\n"
            f"  zchat project remove <name> && zchat project create <name>"
        )
    # New format — resolve server reference
    server_ref = cfg.get("server", "local")
    return resolve_server(server_ref)


def _get_zellij_session(ctx: typer.Context) -> str:
    """Get Zellij session name from project config."""
    cfg = _get_config(ctx)
    session = cfg.get("zellij", {}).get("session")
    if session:
        return session
    project_name = ctx.obj["project"]
    return f"zchat-{project_name}"


def _zellij_switch(session_name: str, tab_name: str):
    """Switch to a Zellij tab. Uses go-to-tab-name inside Zellij, or prints hint outside."""
    from zchat.cli import zellij
    if os.environ.get("ZELLIJ"):
        zellij.go_to_tab(session_name, tab_name)
    else:
        typer.echo(f"Not inside Zellij. Run: zellij attach {session_name}")
        raise typer.Exit(1)


def _get_irc_manager(ctx: typer.Context) -> IrcManager:
    cfg = _get_config(ctx)
    project_name = ctx.obj["project"]
    # Inject resolved IRC config so IrcManager sees it at cfg["irc"]
    if "irc" not in cfg:
        cfg["irc"] = _get_irc_config(cfg)
        # Map host→server for IrcManager's irc_config property
        cfg["irc"].setdefault("server", cfg["irc"].get("host", "127.0.0.1"))
    return IrcManager(
        config=cfg,
        state_file=state_file_path(project_name),
        zellij_session=_get_zellij_session(ctx),
    )


def _get_agent_manager(ctx: typer.Context) -> AgentManager:
    from zchat.cli.auth import get_username
    cfg = _get_config(ctx)
    project_name = ctx.obj["project"]
    irc = _get_irc_config(cfg)
    mcp_cmd = cfg.get("mcp_server_cmd")
    if isinstance(mcp_cmd, str):
        mcp_cmd = [mcp_cmd]
    return AgentManager(
        irc_server=irc["host"],
        irc_port=irc["port"],
        irc_tls=irc.get("tls", False),
        irc_password=irc.get("password", ""),
        username=get_username(),
        default_channels=cfg.get("default_channels", []),
        env_file=cfg.get("env_file", ""),
        default_type=cfg.get("default_runner", ""),
        zellij_session=_get_zellij_session(ctx),
        state_file=state_file_path(project_name),
        project_dir=project_dir(project_name),
        mcp_server_cmd=mcp_cmd,
    )


def _version_callback(value: bool):
    if value:
        from zchat._version import __version__
        typer.echo(f"zchat {__version__}")
        raise typer.Exit()


def _spawn_update_check(state: dict, auto_upgrade: bool = True) -> None:
    """Spawn a detached background process to check for updates."""
    import sys
    cmd = [sys.executable, "-m", "zchat.cli.update", "--background-check"]
    if auto_upgrade:
        cmd.append("--auto-upgrade")
    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    project: Optional[str] = typer.Option(None, help="Project name (overrides auto-detection)"),
    version: bool = typer.Option(False, "--version", "-V", callback=_version_callback,
                                 is_eager=True, help="Show version and exit"),
):
    """Claude Code agent lifecycle management.

    Run without subcommand to start/attach the Zellij session.
    """
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

    # Background update check (once per day)
    try:
        global_cfg = load_global_config()
        state = load_update_state()
        if should_check_today(state):
            auto_upgrade = global_cfg["update"]["auto_upgrade"]
            _spawn_update_check(state, auto_upgrade=auto_upgrade)
        elif state.get("update_available") and not global_cfg["update"]["auto_upgrade"]:
            typer.echo("💡 New version available. Run `zchat upgrade` to update.", err=True)
    except Exception:
        pass  # Never block CLI startup

    # No subcommand → enter zchat main session
    if ctx.invoked_subcommand is None:
        _enter_main_session()


def _ensure_plugins():
    """Copy bundled .wasm plugins to ~/.zchat/plugins/ if missing or outdated."""
    plugins_dir = str(paths.plugins_dir())
    os.makedirs(plugins_dir, exist_ok=True)
    bundled_dir = os.path.join(os.path.dirname(__file__), "data", "plugins")
    if not os.path.isdir(bundled_dir):
        return
    for wasm in os.listdir(bundled_dir):
        if wasm.endswith(".wasm"):
            src = os.path.join(bundled_dir, wasm)
            dest = os.path.join(plugins_dir, wasm)
            src_mtime = os.path.getmtime(src)
            if not os.path.isfile(dest) or os.path.getmtime(dest) < src_mtime:
                import shutil
                shutil.copy2(src, dest)


def _zchat_bin() -> str:
    """Return the path to invoke zchat in a subprocess.

    Prefers the system-installed 'zchat' binary. Falls back to
    sys.executable -m zchat.cli for dev environments.
    """
    import sys
    import shutil
    # 1. If sys.argv[0] resolves to an executable, use it
    argv0 = sys.argv[0]
    if os.path.isabs(argv0) and os.path.isfile(argv0):
        return argv0
    resolved = shutil.which(argv0)
    if resolved:
        return resolved
    # 2. Check if 'zchat' is on PATH (e.g. Homebrew install)
    zchat_path = shutil.which("zchat")
    if zchat_path:
        return zchat_path
    # 3. Fallback: use sys.executable -m zchat.cli
    return f"{sys.executable} -m zchat.cli"


def _resolve_static_choices(source_name: str) -> list[dict] | None:
    """Resolve static choices for a source name.

    Returns list of {"value": ..., "label": ...} dicts.
    Merges built-in presets (from defaults.toml) with user config.
    """
    if source_name == "servers":
        from zchat.cli.defaults import server_presets
        seen = set()
        choices = []
        # Built-in presets first
        for name, preset in server_presets().items():
            choices.append({"value": name, "label": preset.get("label", name)})
            seen.add(name)
        # User-configured servers
        try:
            global_cfg = load_global_config()
            for name, srv in global_cfg.get("servers", {}).items():
                if name not in seen:
                    host = srv.get("host", "?")
                    port = srv.get("port", "?")
                    choices.append({"value": name, "label": f"{name} ({host}:{port})"})
        except Exception:
            pass
        return choices if choices else None
    if source_name == "projects":
        try:
            projects = list_projects()
            if projects:
                return [{"value": p, "label": p} for p in sorted(projects)]
        except Exception:
            pass
        return None
    return None


def _get_commands_json() -> str:
    """Return list-commands output as a JSON string.

    For args with a ``source``, includes pre-resolved ``choices`` when
    the source is static (e.g. servers from global config).  Runtime
    sources (running_agents, projects) are resolved by the plugin from
    Zellij events.
    """
    import json as _json
    import click

    click_group = typer.main.get_group(app)
    commands = []

    def walk(group, prefix=""):
        for name in sorted(group.list_commands(None) or []):
            cmd = group.get_command(None, name)
            if cmd is None:
                continue
            full = f"{prefix} {name}".strip()
            if isinstance(cmd, click.Group):
                if not getattr(cmd, "hidden", False):
                    walk(cmd, full)
            elif getattr(cmd, "hidden", False):
                continue
            else:
                sources = _ARG_SOURCES.get(full, {})
                args = []
                for p in cmd.params:
                    if p.name in ("ctx",) or p.name.startswith("_"):
                        continue
                    arg = {"name": p.name, "required": p.required}
                    if p.name in sources:
                        source = sources[p.name]
                        arg["source"] = source
                        # Pre-resolve static choices
                        choices = _resolve_static_choices(source)
                        if choices:
                            arg["choices"] = choices
                    args.append(arg)
                commands.append({"name": full, "args": args})

    walk(click_group)
    return _json.dumps(commands)


def _write_config_kdl(project_dir_path) -> str:
    """Generate config.kdl with correct plugin path and write to project dir."""
    import json as _json
    plugins_dir = str(paths.plugins_dir())
    zchat_home = str(paths.zchat_home())
    zchat_bin = _zchat_bin()
    commands_json = _get_commands_json()
    # Escape for KDL string (backslashes and quotes)
    commands_escaped = commands_json.replace("\\", "\\\\").replace('"', '\\"')
    config_kdl = os.path.join(project_dir_path, "config.kdl")
    content = f"""\
keybinds {{
    shared_except "locked" {{
        bind "Ctrl k" {{
            LaunchOrFocusPlugin "file:{plugins_dir}/zchat-palette.wasm" {{
                floating true
                move_to_focused_tab true
                zchat_bin "{zchat_bin}"
                zchat_home "{zchat_home}"
                commands_json "{commands_escaped}"
            }}
        }}
    }}
}}
"""
    with open(config_kdl, "w") as f:
        f.write(content)
    return config_kdl


def _enter_main_session():
    """Always enter the zchat main Zellij session.

    This is the hub. From here users manage projects, create agents,
    and switch to project sessions via ``zchat project use <name>``.
    """
    from zchat.cli import zellij
    from zchat.cli.layout import generate_layout

    _ensure_plugins()

    session_name = "zchat"

    # Already inside the main session → nothing to do
    if os.environ.get("ZELLIJ_SESSION_NAME") == session_name:
        return

    # Inside a different Zellij session → switch
    if os.environ.get("ZELLIJ"):
        zellij.switch_session(session_name)
        return

    # Session exists → attach
    if zellij.session_exists(session_name):
        os.execvp("zellij", ["zellij", "attach", session_name])
        return

    # Create new main session with a ctl tab
    main_dir = str(paths.zellij_layout_dir())
    os.makedirs(main_dir, exist_ok=True)

    layout_kdl_path = os.path.join(main_dir, "layout.kdl")
    with open(layout_kdl_path, "w") as f:
        f.write("layout {\n")
        f.write("    default_tab_template {\n")
        f.write('        pane size=1 borderless=true {\n')
        f.write('            plugin location="zellij:tab-bar"\n')
        f.write("        }\n")
        f.write("        children\n")
        plugins = str(paths.plugins_dir())
        wasm_path = os.path.join(plugins, "zchat-status.wasm")
        if os.path.isfile(wasm_path):
            f.write(f'        pane size=1 borderless=true {{\n')
            f.write(f'            plugin location="file:{wasm_path}"\n')
            f.write("        }\n")
        f.write('        pane size=2 borderless=true {\n')
        f.write('            plugin location="zellij:status-bar"\n')
        f.write("        }\n")
        f.write("    }\n")
        f.write('    tab name="ctl" focus=true {\n')
        f.write("        pane\n")
        f.write("    }\n")
        f.write("}\n")

    config_kdl = _write_config_kdl(main_dir)
    os.execvp("zellij", ["zellij", "--config", str(config_kdl),
                          "--new-session-with-layout", layout_kdl_path,
                          "--session", session_name])


def _launch_project_session(name: str):
    """Ensure the project's Zellij session is running, then switch/attach to it.

    If already inside Zellij → switch_session.
    If outside → create session (if needed) and attach.
    """
    from zchat.cli import zellij
    from zchat.cli.layout import write_layout
    from zchat.cli.auth import get_username

    _ensure_plugins()

    cfg = load_project_config(name)
    session_name = cfg.get("zellij", {}).get("session") or f"zchat-{name}"
    pdir = project_dir(name)

    # Already inside Zellij → switch session (create first if needed)
    if os.environ.get("ZELLIJ"):
        if not zellij.session_exists(session_name):
            _create_project_zellij_session(name, cfg, session_name, pdir)
        zellij.switch_session(session_name)
        return

    # Outside Zellij — session exists → attach
    if zellij.session_exists(session_name):
        os.execvp("zellij", ["zellij", "attach", session_name])
        return

    # Outside Zellij — create and attach
    _create_project_zellij_session(name, cfg, session_name, pdir)
    os.execvp("zellij", ["zellij", "attach", session_name])


def _create_project_zellij_session(name: str, cfg: dict, session_name: str, pdir: str):
    """Create a new Zellij session for a project (does NOT attach)."""
    from zchat.cli.layout import write_layout

    irc = _get_irc_config(cfg)

    # Build IrcManager to get weechat cmd and optionally start ergo
    irc_cfg = dict(cfg)
    if "irc" not in irc_cfg:
        irc_cfg["irc"] = irc
        irc_cfg["irc"].setdefault("server", irc.get("host", "127.0.0.1"))
    irc_manager = IrcManager(
        config=irc_cfg,
        state_file=state_file_path(name),
        zellij_session=session_name,
    )

    # Start ergo if local
    server = irc["host"]
    if server in ("127.0.0.1", "localhost", "::1"):
        irc_manager.daemon_start()

    weechat_cmd = irc_manager.build_weechat_cmd()
    state_path = state_file_path(name)
    state = {}
    if os.path.isfile(state_path):
        import json
        with open(state_path) as f:
            try:
                state = json.load(f)
            except Exception:
                pass

    layout_path = write_layout(pdir, cfg, state,
                               weechat_cmd=weechat_cmd,
                               project_name=name)
    config_kdl = _write_config_kdl(pdir)

    # Create session in background (detached)
    from zchat.cli import zellij
    zellij.ensure_session(session_name, layout=str(layout_path),
                          config=str(config_kdl))


# ============================================================
# project commands
# ============================================================

@project_app.command("create")
def cmd_project_create(
    name: str,
    server: Optional[str] = typer.Option(None, help="Server name (from global config) or hostname"),
    port: Optional[int] = typer.Option(None, help="IRC port (only for new server)"),
    tls: Optional[bool] = typer.Option(None, help="Enable TLS (only for new server)"),
    password: Optional[str] = typer.Option(None, help="IRC password (only for new server)"),
    channels: Optional[str] = typer.Option(None, help="Default channels (comma-separated)"),
    agent_type: Optional[str] = typer.Option(None, "--agent-type", help="Agent template name (e.g. 'claude')"),
    proxy: Optional[str] = typer.Option(None, help="HTTP proxy (ip:port, empty string for none)"),
):
    """Create a new project with config setup.

    --server can be a name from global config (e.g. 'local', 'cloud') or a
    hostname. If the server doesn't exist in global config, it is created.

    When all required options are provided, runs non-interactively.
    Otherwise, prompts for missing values.
    """
    pdir = project_dir(name)
    if os.path.exists(pdir):
        typer.echo(f"Project '{name}' already exists.")
        raise typer.Exit(1)

    global_cfg = load_global_config()
    existing_servers = global_cfg.get("servers", {})

    # --- IRC server selection ---
    _server_ref: str
    if server is not None:
        _server_ref = server
    else:
        # Show existing servers + options to add new
        choices = list(existing_servers.keys())
        if choices:
            typer.echo("IRC Server:")
            for i, sname in enumerate(choices, 1):
                srv = existing_servers[sname]
                typer.echo(f"  {i}) {sname} ({srv.get('host', '?')}:{srv.get('port', '?')})")
            typer.echo(f"  {len(choices) + 1}) Add new server")
            choice = typer.prompt("Choose", default="1")
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(choices):
                    _server_ref = choices[idx]
                else:
                    raise ValueError
            except ValueError:
                _server_ref = _prompt_new_server(global_cfg)
        else:
            _server_ref = _prompt_new_server(global_cfg)

    # Ensure server exists in global config (auto-create if it's a hostname)
    if _server_ref not in global_cfg.get("servers", {}):
        from zchat.cli.defaults import server_presets
        presets = server_presets()
        # Check if it matches a preset by hostname
        preset_match = next((n for n, p in presets.items() if p["host"] == _server_ref), None)
        if preset_match:
            p = presets[preset_match]
            _port = port if port is not None else p["port"]
            _tls = tls if tls is not None else p.get("tls", False)
            ensure_server_in_global(preset_match, p["host"], _port, _tls, password or "", global_cfg)
            _server_ref = preset_match
        else:
            _port = port if port is not None else 6667
            _tls = tls if tls is not None else False
            _password = password if password is not None else ""
            server_name = _server_ref.replace(".", "-").split(":")[0]
            if server_name in ("127-0-0-1", "localhost"):
                server_name = "local"
            ensure_server_in_global(server_name, _server_ref, _port, _tls, _password, global_cfg)
            _server_ref = server_name

    # --- Channels ---
    from zchat.cli.defaults import default_channels as _default_channels
    _channels: str = channels if channels is not None else typer.prompt("Default channels", default=",".join(_default_channels()))

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

    create_project_config(name, server=_server_ref, nick="", channels=_channels,
                          env_file=env_file, default_runner=default_type)
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
        typer.echo(f"  {p}{marker}  {project_dir(p)}")

@project_app.command("use")
def cmd_project_use(
    name: str,
    attach: bool = typer.Option(
        False,
        "--attach",
        help="Also start services + attach Zellij session (legacy V5 behavior). "
             "V6 推荐: 用 'zchat up' 显式启服务。",
    ),
):
    """Set default project. By default does NOT start any services (V6 behavior).

    Use `zchat up` to start services declared in routing.toml.
    Use `--attach` to keep V5 behavior (auto-start ergo + WeeChat + default agent).
    """
    if not os.path.isdir(project_dir(name)):
        typer.echo(f"Project '{name}' does not exist.")
        raise typer.Exit(1)
    set_default_project(name)
    typer.echo(f"Default project set to '{name}'.")
    if attach:
        _launch_project_session(name)
    else:
        typer.echo("Run `zchat up` to start services.")

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
        irc = _get_irc_config(cfg)
        mgr = AgentManager(
            irc_server=irc["host"], irc_port=irc["port"],
            irc_tls=irc.get("tls", False),
            irc_password=irc.get("password", ""),
            username=get_username(),
            default_channels=cfg.get("default_channels", []),
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
    irc = _get_irc_config(cfg)
    nickname = cfg.get("username", "")
    channels = cfg.get("default_channels", [])
    if not isinstance(channels, list):
        channels = []
    typer.echo(f"Project: {name}")
    typer.echo(f"  IRC server: {irc['host']}:{irc['port']}")
    typer.echo(f"  TLS: {irc.get('tls', False)}")
    typer.echo(f"  Nickname: {nickname}")
    typer.echo(f"  Channels: {', '.join(channels)}")


@app.command("set")
def cmd_set(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Config key (dotted, e.g. 'default_runner' or 'zellij.session')"),
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
    from pathlib import Path
    from dotenv import dotenv_values
    from zchat.cli.template_loader import resolve_template_dir
    try:
        tpl_dir = resolve_template_dir(name)
    except Exception as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(1)
    # If template is built-in (inside package), .env goes to user dir
    user_tpl_dir = paths.templates_dir() / name
    zchat_home_str = str(paths.zchat_home())
    if not tpl_dir.startswith(zchat_home_str):
        user_tpl_dir.mkdir(parents=True, exist_ok=True)
        env_path = str(user_tpl_dir / ".env")
    else:
        env_path = os.path.join(tpl_dir, ".env")
    env = {k: v for k, v in dotenv_values(env_path).items() if v is not None}
    env[key] = value
    with open(env_path, "w") as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")
    typer.echo(f"Set {key} in {name} template .env")


@template_app.command("create")
def cmd_template_create(name: str = typer.Argument(..., help="Template name")):
    """Create an empty template scaffold."""
    from pathlib import Path
    tpl_dir = paths.templates_dir() / name
    if tpl_dir.exists():
        typer.echo(f"Template '{name}' already exists at {tpl_dir}")
        raise typer.Exit(1)
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "template.toml").write_text(
        f'[template]\nname = "{name}"\ndescription = ""\n\n[hooks]\npre_stop = ""\n')
    start_sh = tpl_dir / "start.sh"
    start_sh.write_text("#!/bin/bash\nset -euo pipefail\nexec echo \"TODO: implement start script\"\n")
    start_sh.chmod(0o755)
    (tpl_dir / ".env.example").write_text(
        "# Auto-injected by zchat\nAGENT_NAME={{agent_name}}\nIRC_SERVER={{irc_server}}\n"
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
    """Start WeeChat in Zellij, auto-connect to IRC."""

    mgr = _get_irc_manager(ctx)
    try:
        mgr.start_weechat(nick_override=nick)
    except ConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        typer.echo("Check that the IRC server is running.", err=True)
        raise typer.Exit(1)

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
    channel_id: Optional[str] = typer.Option(None, "--channel", "-c",
                                              help="Register agent into this channel in routing.toml"),
):
    """Create and launch a new agent.

    If --channel is given, the agent's nick is set as entry_agent for that channel
    in routing.toml when no entry_agent exists yet (first-agent-wins).
    """
    mgr = _get_agent_manager(ctx)
    ch = [c.strip() for c in channels.split(",")] if channels else None
    # 若指定 --channel 但未传 --channels，IRC_CHANNELS 应跟随 --channel
    # （否则 agent 默认 JOIN #general，与 routing 注册的 channel 不一致）
    if ch is None and channel_id:
        ch = [channel_id.lstrip("#")]
    try:
        info = mgr.create(name, workspace=workspace, channels=ch, agent_type=agent_type)
    except ConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        typer.echo("Check that the IRC server is running.", err=True)
        raise typer.Exit(1)
    scoped = mgr.scoped(name)
    typer.echo(f"Created {scoped} (type: {info['type']})")
    typer.echo(f"  tab: {info.get('tab_name', '—')}")
    typer.echo(f"  workspace: {info.get('workspace', '—')}")

    # 若指定 --channel，自动登记到 routing.toml（仅写 entry_agent，没 agents 列表）
    if channel_id:
        from zchat.cli.routing import join_agent as routing_join_agent, channel_exists as routing_channel_exists
        project_name = ctx.obj.get("project") if ctx.obj else None
        pdir = project_dir(project_name)
        channel_normalized = normalize_channel_name(channel_id)
        if not routing_channel_exists(pdir, channel_normalized):
            typer.echo(
                f"Warning: Channel '{channel_normalized}' not registered in routing.toml. "
                f"Run `zchat channel create {channel_normalized}` first.",
                err=True,
            )
        else:
            try:
                routing_join_agent(pdir, channel_normalized, scoped)
                typer.echo(f"  routing: '{scoped}' joined '{channel_normalized}'")
            except ValueError as e:
                typer.echo(f"Warning: routing registration failed: {e}", err=True)


@agent_app.command("stop")
def cmd_agent_stop(ctx: typer.Context, name: str = typer.Argument(...)):
    """Stop a running agent."""
    mgr = _get_agent_manager(ctx)
    scoped = mgr.scoped(name)
    mgr.stop(name, force=True)
    typer.echo(f"Stopped {scoped}")

@agent_app.command("list")
def cmd_agent_list(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all agents with status."""
    mgr = _get_agent_manager(ctx)
    agents = mgr.list_agents()
    if json_output:
        import json as _json
        out = [{"name": n, **info} for n, info in agents.items()]
        typer.echo(_json.dumps(out))
        return
    if not agents:
        typer.echo("No agents")
        return
    for name, info in agents.items():
        status = info["status"]
        window = info.get("tab_name", "—")
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
    typer.echo(f"  tab:       {info.get('tab_name', '—')}")
    typer.echo(f"  workspace: {info.get('workspace', '—')}")
    typer.echo(f"  channels:  {', '.join(info.get('channels', []))}")

@agent_app.command("send")
def cmd_agent_send(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    text: str = typer.Argument(..., help="Text to send to agent's Zellij tab"),
):
    """Send text to agent's pane."""

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


@agent_app.command("start")
def cmd_agent_start(ctx: typer.Context, name: str = typer.Argument(...)):
    """Bring an offline agent back online (uses config from state.json)."""

    mgr = _get_agent_manager(ctx)
    scoped = mgr.scoped(name)
    mgr.start(name)
    typer.echo(f"Started {scoped}")

@agent_app.command("focus")
def cmd_agent_focus(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
):
    """Switch to an agent's tab."""
    mgr = _get_agent_manager(ctx)
    agent = mgr.get_status(name)
    scoped = mgr.scoped(name)
    if agent["status"] == "offline":
        typer.echo(f"{scoped} is offline")
        raise typer.Exit(1)
    _zellij_switch(mgr.session_name, agent.get("tab_name"))

@agent_app.command("hide")
def cmd_agent_hide(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name or 'all'"),
):
    """Switch back to WeeChat tab."""
    mgr = _get_agent_manager(ctx)
    if name != "all":
        mgr.get_status(name)
    _zellij_switch(mgr.session_name, "weechat")


@agent_app.command("join")
def cmd_agent_join(
    ctx: typer.Context,
    agent: str = typer.Argument(..., help="Agent name (short name or scoped nick)"),
    channel: str = typer.Argument(..., help="Channel name (with or without #)"),
    as_entry: bool = typer.Option(False, "--as-entry",
                                   help="Set this agent as channel's entry_agent (overrides existing)"),
):
    """Add agent to a registered channel.

    Updates agent state (channels list). Sets entry_agent in routing.toml when
    no entry_agent yet, or when --as-entry is given. Restart agent for IRC JOIN
    to take effect.
    """
    from zchat.cli.routing import channel_exists as routing_channel_exists, join_agent as routing_join_agent
    project_name = ctx.obj.get("project") if ctx.obj else None
    if not project_name:
        typer.echo("Error: No project selected. Run 'zchat project create <name>'.", err=True)
        raise typer.Exit(1)

    channel = normalize_channel_name(channel)

    # Verify channel is registered in routing.toml
    pdir = project_dir(project_name)
    if not routing_channel_exists(pdir, channel):
        typer.echo(
            f"Error: Channel '{channel}' not registered. "
            f"Run `zchat channel create {channel}` first.",
            err=True,
        )
        raise typer.Exit(1)

    mgr = _get_agent_manager(ctx)
    scoped = mgr.scoped(agent)

    # Check agent exists in state
    agents = mgr._agents
    if scoped not in agents:
        typer.echo(f"Error: Agent '{scoped}' not found. Run `zchat agent create {agent}` first.", err=True)
        raise typer.Exit(1)

    # 1. 更新 agent state 中的 channels 列表（用于重启时 IRC JOIN）
    current_channels: list[str] = list(agents[scoped].get("channels", []))
    if channel not in current_channels:
        current_channels.append(channel)
        agents[scoped]["channels"] = current_channels
        mgr._save_state()

    # 2. routing.toml 设 entry_agent（首个 / --as-entry）；roster 由 IRC NAMES 反映
    try:
        routing_join_agent(pdir, channel, scoped, as_entry=as_entry)
    except ValueError as e:
        # channel_exists 已验证，此路径理论上不会触发
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    status = agents[scoped].get("status", "offline")
    if status == "running":
        typer.echo(
            f"Agent '{scoped}' joined '{channel}' (state + routing updated).\n"
            f"Restart agent for channel to take effect: zchat agent restart {agent}"
        )
    else:
        typer.echo(f"Agent '{scoped}' will join '{channel}' on next start.")


# ============================================================
# channel commands
# ============================================================

@channel_app.command("create")
def cmd_channel_create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name (with or without #)"),
    bot: Optional[str] = typer.Option(None, "--bot",
                                       help="Bot name (must be registered via `zchat bot add` first)"),
    external_chat: Optional[str] = typer.Option(None, "--external-chat",
                                                help="External platform chat ID (e.g. oc_xxx)"),
    entry_agent: Optional[str] = typer.Option(None, "--entry-agent",
                                              help="Entry agent nick (router will @ this agent in copilot mode)"),
):
    """Register a channel in routing.toml.

    Channel will be created on the IRC server automatically when an agent JOINs.
    """
    from zchat.cli.routing import add_channel as routing_add_channel
    project_name = ctx.obj.get("project") if ctx.obj else None
    if not project_name:
        typer.echo("Error: No project selected. Run 'zchat project create <name>'.", err=True)
        raise typer.Exit(1)

    channel_name = normalize_channel_name(name)
    pdir = project_dir(project_name)
    try:
        routing_add_channel(
            pdir,
            channel_name,
            bot=bot,
            external_chat_id=external_chat,
            entry_agent=entry_agent,
        )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Channel '{channel_name}' registered in project '{project_name}'.")


@channel_app.command("list")
def cmd_channel_list(ctx: typer.Context):
    """List all registered channels in current project (reads routing.toml)."""
    from zchat.cli.routing import list_channels as routing_list_channels
    project_name = ctx.obj.get("project") if ctx.obj else None
    if not project_name:
        typer.echo("Error: No project selected. Run 'zchat project create <name>'.", err=True)
        raise typer.Exit(1)

    pdir = project_dir(project_name)
    channels = routing_list_channels(pdir)
    if not channels:
        typer.echo("No channels registered. Run 'zchat channel create <name>'.")
        return

    for ch in channels:
        ch_id = ch["channel_id"]
        ext_chat = ch.get("external_chat_id", "")
        bot = ch.get("bot", "")
        entry = ch.get("entry_agent", "")
        typer.echo(f"  {ch_id}\tbot={bot}\text_chat={ext_chat}\tentry={entry}")


@channel_app.command("remove")
def cmd_channel_remove(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name (with or without #)"),
    stop_agents: bool = typer.Option(False, "--stop-agents",
                                      help="Also stop all agent processes in this channel"),
):
    """Remove a channel from routing.toml (and optionally stop its agents)."""
    from zchat.cli.routing import remove_channel as routing_remove_channel, load_routing
    project_name = ctx.obj.get("project") if ctx.obj else None
    if not project_name:
        typer.echo("Error: No project selected.", err=True)
        raise typer.Exit(1)

    channel_name = normalize_channel_name(name)
    pdir = project_dir(project_name)

    # V6+: routing.toml 不存 agents 列表；agent 归属要 stop 需先从 IRC NAMES /
    # agent state 里查，这里先 remove channel，由 caller 自己 `zchat agent stop
    # <nick>` 清理（或未来接 list_peers）。
    routing_remove_channel(pdir, channel_name)
    typer.echo(f"Channel '{channel_name}' removed from routing.toml.")

    if stop_agents:
        mgr = _get_agent_manager(ctx)
        channel_bare = channel_name.lstrip("#")
        stopped = 0
        for agent_name, info in mgr.list_agents().items():
            if channel_bare in (info.get("channels") or []):
                try:
                    mgr.stop(agent_name)
                    typer.echo(f"Stopped agent '{agent_name}'.")
                    stopped += 1
                except Exception as e:
                    typer.echo(f"Warning: failed to stop '{agent_name}': {e}", err=True)
        if stopped == 0:
            typer.echo(f"No running agents in '{channel_name}' found.")


@channel_app.command("set-entry")
def cmd_channel_set_entry(
    ctx: typer.Context,
    channel: str = typer.Argument(..., help="Channel name"),
    nick: str = typer.Argument(..., help="Agent nick to set as entry_agent"),
):
    """Explicitly set the entry_agent for a channel."""
    from zchat.cli.routing import set_entry_agent
    project_name = ctx.obj.get("project") if ctx.obj else None
    if not project_name:
        typer.echo("Error: No project selected.", err=True)
        raise typer.Exit(1)

    channel_name = normalize_channel_name(channel)
    pdir = project_dir(project_name)
    try:
        set_entry_agent(pdir, channel_name, nick)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"entry_agent of '{channel_name}' set to '{nick}'.")


# ============================================================
# bot commands (V6: 注册外部平台 bot 到 routing.toml [bots])
# ============================================================

@bot_app.command("add")
def cmd_bot_add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Bot name (logical identifier used in routing.toml)"),
    credential: Optional[str] = typer.Option(None, "--credential", "-c",
                                              help="Path to credential JSON (with app_id + app_secret). "
                                                   "Relative to project dir; defaults to credentials/<name>.json if exists."),
    template: Optional[str] = typer.Option(None, "--template",
                                            help="Default agent template for lazy-create"),
    lazy: bool = typer.Option(False, "--lazy",
                               help="Enable lazy-create on this bot"),
    supervises: Optional[str] = typer.Option(None, "--supervises",
                                              help="Comma-separated bot names this bot monitors (supervision). V7+ 支持 tag:/pattern: 前缀"),
):
    """Register a bot in routing.toml [bots].

    Credentials must come from a JSON file with `{app_id, app_secret}`:

      - --credential <path>: explicit path (relative to project dir).
      - Auto-detect: if --credential omitted, looks for credentials/<name>.json.

    V7+: app_id is no longer stored in routing.toml — credential file is the
    single source of truth.
    """
    from zchat.cli.routing import add_bot as routing_add_bot
    import json as _json
    from pathlib import Path as _Path

    project_name = ctx.obj.get("project") if ctx.obj else None
    if not project_name:
        typer.echo("Error: No project selected.", err=True)
        raise typer.Exit(1)

    pdir = _Path(project_dir(project_name))

    # Auto-detect default credential file if --credential omitted
    if not credential:
        default_cred = pdir / "credentials" / f"{name}.json"
        if default_cred.is_file():
            credential = f"credentials/{name}.json"
            typer.echo(f"Using default credential file: {credential}")
        else:
            typer.echo(
                f"Error: --credential <path> required (or place credentials/{name}.json in project dir).",
                err=True,
            )
            raise typer.Exit(1)

    cred_path = _Path(credential)
    if not cred_path.is_absolute():
        cred_path = pdir / credential
    if not cred_path.is_file():
        typer.echo(f"Error: credential file not found: {cred_path}", err=True)
        raise typer.Exit(1)
    try:
        cred_data = _json.loads(cred_path.read_text(encoding="utf-8"))
    except Exception as e:
        typer.echo(f"Error: failed to parse credential JSON ({cred_path}): {e}", err=True)
        raise typer.Exit(1)
    resolved_app_id = cred_data.get("app_id")
    if not resolved_app_id:
        typer.echo(f"Error: credential JSON missing 'app_id' field: {cred_path}", err=True)
        raise typer.Exit(1)
    if not cred_data.get("app_secret"):
        typer.echo(
            f"Warning: credential JSON missing 'app_secret'; bridge may fail to authenticate.",
            err=True,
        )
    try:
        cred_rel = str(cred_path.relative_to(pdir))
    except ValueError:
        cred_rel = str(cred_path)  # absolute path fallback

    supervises_list: Optional[list[str]] = None
    if supervises:
        supervises_list = [s.strip() for s in supervises.split(",") if s.strip()]
    try:
        routing_add_bot(
            pdir, name,
            credential_file=cred_rel,
            default_agent_template=template,
            lazy_create_enabled=lazy,
            supervises=supervises_list,
        )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    msg = f"Bot '{name}' registered (app_id={resolved_app_id}, lazy={lazy}"
    if supervises_list:
        msg += f", supervises={supervises_list}"
    typer.echo(msg + ").")


@bot_app.command("list")
def cmd_bot_list(ctx: typer.Context):
    """List all registered bots in current project."""
    from zchat.cli.routing import list_bots as routing_list_bots
    import json as _json
    from pathlib import Path as _Path
    project_name = ctx.obj.get("project") if ctx.obj else None
    if not project_name:
        typer.echo("Error: No project selected.", err=True)
        raise typer.Exit(1)

    pdir = _Path(project_dir(project_name))
    bots = routing_list_bots(pdir)
    if not bots:
        typer.echo("No bots registered. Run 'zchat bot add <name> --credential <path>'.")
        return
    for b in bots:
        sup = b.get("supervises") or []
        sup_str = f"\tsupervises={sup}" if sup else ""
        cred_rel = b.get("credential_file") or ""
        # 显示 app_id：从 credential JSON 读，读不到显示 "?"
        app_id_disp = "?"
        if cred_rel:
            cred_path = _Path(cred_rel)
            if not cred_path.is_absolute():
                cred_path = pdir / cred_rel
            if cred_path.is_file():
                try:
                    app_id_disp = _json.loads(cred_path.read_text(encoding="utf-8")).get("app_id", "?")
                except Exception:
                    pass
        typer.echo(
            f"  {b['name']}\tapp_id={app_id_disp}\tcred={cred_rel}"
            f"\ttemplate={b.get('default_agent_template','')}{sup_str}"
            f"\tlazy={b.get('lazy_create_enabled', False)}"
        )


@bot_app.command("remove")
def cmd_bot_remove(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Bot name"),
    delete_secret: bool = typer.Option(False, "--delete-secret",
                                        help="Also delete credentials/<name>.json"),
):
    """Remove a bot from routing.toml [bots] (does not touch channels referencing it)."""
    from zchat.cli.routing import remove_bot as routing_remove_bot, list_channels
    project_name = ctx.obj.get("project") if ctx.obj else None
    if not project_name:
        typer.echo("Error: No project selected.", err=True)
        raise typer.Exit(1)

    from pathlib import Path as _Path
    pdir = _Path(project_dir(project_name))
    refs = [c["channel_id"] for c in list_channels(pdir) if c.get("bot") == name]
    if refs:
        typer.echo(
            f"Warning: bot '{name}' is referenced by channels: {', '.join(refs)}",
            err=True,
        )
    routing_remove_bot(pdir, name)
    if delete_secret:
        cred_path = pdir / "credentials" / f"{name}.json"
        if cred_path.exists():
            cred_path.unlink()
            typer.echo(f"Deleted {cred_path}")
    typer.echo(f"Bot '{name}' removed from routing.toml.")


# ============================================================
# shutdown
# ============================================================

@app.command("up")
def cmd_up(
    ctx: typer.Context,
    only: Optional[str] = typer.Option(None, "--only",
                                        help="Comma-separated subset to start: irc,weechat,cs,bridges,agents"),
):
    """Start all services declared in routing.toml (ergo + WeeChat + cs + N bridges + missing agents).

    The set of bridges = unique bots in [bots]; the set of agents = unique entry_agent in [channels].
    Idempotent: safe to re-run.
    """
    from zchat.cli.routing import load_routing as _load_routing
    from zchat.cli import zellij as _zj
    import os as _os
    import time as _time

    project_name = ctx.obj.get("project") if ctx.obj else None
    if not project_name:
        typer.echo("Error: No project selected. Run 'zchat project create <name>'.", err=True)
        raise typer.Exit(1)

    parts = set((only or "irc,weechat,cs,bridges,agents").split(","))
    from pathlib import Path as _P
    pdir = _P(project_dir(project_name))
    routing = _load_routing(pdir)
    bots = (routing.get("bots") or {})
    channels = (routing.get("channels") or {})

    # 1. ergo + WeeChat（zchat 已有命令）
    if "irc" in parts:
        irc = _get_irc_manager(ctx)
        irc.daemon_start()
        typer.echo("ergo: started")

    # 2. 确保 zellij session 存在（cs/bridge/agent tab 都需要）
    session = _get_zellij_session(ctx)
    if not _zj.session_exists(session):
        _zj.ensure_session(session)
        typer.echo(f"zellij session: {session}")

    if "weechat" in parts:
        cfg = ctx.obj.get("config") or {}
        nick = cfg.get("username") or _os.environ.get("USER")
        irc = _get_irc_manager(ctx)
        if not _zj.tab_exists(session, "chat"):
            try:
                weechat_cmd = irc.build_weechat_cmd(nick_override=nick)
                _zj.new_tab(session, "chat", command=weechat_cmd)
                typer.echo("weechat: started")
            except Exception as e:
                typer.echo(f"weechat: skip ({e})", err=True)

    from zchat.cli.routing import routing_path as _routing_path
    from pathlib import Path as _Path
    cs_dir = str(_Path(__file__).resolve().parent.parent.parent / "zchat-channel-server")
    routing_file = str(_routing_path(pdir))

    def _ensure_tab(tab: str, cmd: str, label: str,
                     kill_pattern: str | None = None,
                     kill_port: int | None = None) -> None:
        """创建 tab；若 tab 已存在先关；可选 kill 残留进程/端口后再重建。"""
        if _zj.tab_exists(session, tab):
            try:
                _zj.close_tab(session, tab)
                _time.sleep(0.3)
            except Exception:
                pass
        # 关 tab 后 child process 可能还没 release 端口/资源，显式 kill
        if kill_pattern:
            import subprocess as _sp
            _sp.run(["pkill", "-f", kill_pattern], check=False,
                    stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
        if kill_port:
            import subprocess as _sp
            _sp.run(["fuser", "-k", f"{kill_port}/tcp"], check=False,
                    stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
            _time.sleep(0.5)
        _zj.new_tab(session, tab, command=cmd)
        typer.echo(f"{label}: started")

    # 2. channel-server tab
    if "cs" in parts:
        cs_log = pdir / "cs.log"
        cs_cmd = (
            f"export IRC_SERVER=127.0.0.1 IRC_PORT=6667 "
            f"WS_HOST=127.0.0.1 WS_PORT=9999 CS_NICK=cs-bot "
            f"CS_ROUTING_CONFIG={routing_file}; "
            f"cd {cs_dir} && uv run python -m channel_server 2>&1 | tee {cs_log}"
        )
        _ensure_tab("cs", cs_cmd, "cs",
                    kill_pattern="python.*-m channel_server",
                    kill_port=9999)
        _time.sleep(2)

    # 3. 每个 bot 一个 bridge tab
    if "bridges" in parts:
        for bot_name in bots:
            tab = f"bridge-{bot_name}"
            log_file = pdir / f"bridge-{bot_name}.log"
            br_cmd = (
                f"cd {cs_dir} && uv run python -u -m feishu_bridge "
                f"--bot {bot_name} --routing {routing_file} 2>&1 | tee {log_file}"
            )
            _ensure_tab(tab, br_cmd, f"bridge-{bot_name}",
                        kill_pattern=f"feishu_bridge --bot {bot_name}")

    # 4. 每个 channel.entry_agent 缺失的 agent
    if "agents" in parts:
        mgr = _get_agent_manager(ctx)
        existing = mgr.list_agents()
        for ch_id, ch in channels.items():
            entry = ch.get("entry_agent")
            if not entry:
                continue
            # entry_agent 形如 "yaosh-fast-001"，剥前缀作 short name
            short = entry.split("-", 1)[1] if "-" in entry else entry
            scoped = mgr.scoped(short)
            # 只跳过真正 running 的；offline / dangling 条目要重建
            if scoped in existing and existing[scoped].get("status") == "running":
                continue
            # 清理 stale state 条目 + 残留 zellij tab，避免重建后双 tab
            if scoped in existing:
                try:
                    mgr.stop(scoped, force=True)
                except Exception:
                    pass
                mgr._agents.pop(scoped, None)
                mgr._save_state()
            # 无论 state 是否有条目，zellij 里可能还有同名死 tab（上次 crash 残留）
            if _zj.tab_exists(session, scoped):
                try:
                    _zj.close_tab(session, scoped)
                    _time.sleep(0.2)
                except Exception:
                    pass
            # 找 bot 拿默认 template
            bot_name = ch.get("bot")
            template = (bots.get(bot_name) or {}).get("default_agent_template", "claude")
            try:
                clean_ch = ch_id.lstrip("#")
                mgr.create(short, channels=[clean_ch], agent_type=template)
                typer.echo(f"agent {short}: started in #{clean_ch} (type={template})")
            except Exception as e:
                typer.echo(f"agent {short}: failed ({e})", err=True)

    typer.echo("up: complete")


@app.command("down")
def cmd_down(ctx: typer.Context):
    """Alias for shutdown — stop all services + zellij session."""
    cmd_shutdown(ctx)


@app.command("shutdown")
def cmd_shutdown(ctx: typer.Context):
    """Stop all agents + WeeChat + ergo + Zellij session."""
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
    # Kill Zellij session
    try:
        session_name = _get_zellij_session(ctx)
        from zchat.cli import zellij
        zellij.kill_session(session_name)
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
# update / upgrade
# ============================================================

@app.command("update")
def cmd_update():
    """Check for new versions (does not install)."""
    state = load_update_state()
    typer.echo(f"Channel: {state['channel']}")
    typer.echo("Checking...")
    state = check_for_updates(state)
    save_update_state(state)

    if state["update_available"]:
        typer.echo(f"zchat:          {state['zchat']['installed_ref'] or '?'} → {state['zchat']['remote_ref']}")
        typer.echo(f"channel-server: {state['channel_server']['installed_ref'] or '?'} → {state['channel_server']['remote_ref']}")
        typer.echo("\nRun `zchat upgrade` to install.")
    else:
        typer.echo("Already up to date.")


@app.command("upgrade")
def cmd_upgrade(
    channel: Optional[str] = typer.Option(None, help="Override update channel (main/dev/release)"),
):
    """Download and install the latest version."""
    global_cfg = load_global_config()
    ch = channel or global_cfg["update"]["channel"]

    state = load_update_state()
    state["channel"] = ch
    state = check_for_updates(state)

    if not state["update_available"]:
        typer.echo("Already up to date.")
        save_update_state(state)
        return

    typer.echo(f"Upgrading from channel '{ch}'...")
    ok = run_upgrade(ch)
    if ok:
        state["zchat"]["installed_ref"] = state["zchat"]["remote_ref"]
        state["channel_server"]["installed_ref"] = state["channel_server"]["remote_ref"]
        state["update_available"] = False
        save_update_state(state)
        typer.echo("Done. Restart any running zchat commands to use the new version.")
    else:
        typer.echo("Error: Upgrade failed. Run `zchat upgrade` to retry.")
        raise typer.Exit(1)


# ============================================================
# config
# ============================================================

@config_app.command("get")
def cmd_config_get(key: str):
    """Get a global config value."""
    cfg = load_global_config()
    val = get_config_value(cfg, key)
    if val is None:
        typer.echo(f"Key '{key}' not found.")
        raise typer.Exit(1)
    typer.echo(str(val))


@config_app.command("set")
def cmd_config_set(key: str, value: str):
    """Set a global config value."""
    if key == "update.channel" and value not in ("main", "dev", "release"):
        typer.echo(f"Error: channel must be one of: main, dev, release")
        raise typer.Exit(1)
    cfg = load_global_config()
    set_config_value(cfg, key, value)
    save_global_config(cfg)
    typer.echo(f"{key} = {get_config_value(cfg, key)}")
    if key == "update.channel":
        state = load_update_state()
        state["channel"] = value
        state["zchat"] = {"installed_ref": "", "remote_ref": ""}
        state["channel_server"] = {"installed_ref": "", "remote_ref": ""}
        state["update_available"] = False
        save_update_state(state)


@config_app.command("list")
def cmd_config_list():
    """Show all global config values."""
    cfg = load_global_config()
    for section, values in cfg.items():
        if isinstance(values, dict):
            for k, v in values.items():
                typer.echo(f"{section}.{k} = {v}")


# ============================================================
# voice commands
# ============================================================

@voice_app.command("test")
def cmd_voice_test(
    ctx: typer.Context,
    channel: str = typer.Option("#test-voice", "--channel",
                                  help="临时绑死的 IRC channel（dev-mode 跳过 JWT）"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port"),
    loopback: bool = typer.Option(True, "--loopback/--no-loopback",
                                    help="L0：mic→ASR→TTS→speaker 本地回环，不连 CS"),
    asr: str = typer.Option("stub", "--asr",
                              help="ASR engine: stub | whisper_cpp | volcengine"),
    tts: str = typer.Option("stub", "--tts",
                              help="TTS engine: stub | volcengine | piper | edge_tts"),
    open_browser: bool = typer.Option(True, "--open/--no-open",
                                        help="自动打开浏览器"),
    jwt_secret: str = typer.Option("", "--jwt-secret",
                                     help="JWT 验签密钥；为空自动读 $VOICE_JWT_SECRET"),
    cs_url: str = typer.Option("ws://127.0.0.1:9999", "--cs-url",
                                 help="channel_server WS 地址（非 loopback 模式下必填）"),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
):
    """启动 voice_bridge 测试实例 (L0 loopback / L1 with agent)。

    示例：
      # L0：说啥听啥，验证 ASR/TTS pipeline
      zchat voice test --loopback --channel '#test-voice'

      # L1：连 CS，绑到现有 channel（需先 zchat up 起 CS + agent）
      zchat voice test --no-loopback --channel '#conv-001'
    """
    import os as _os
    import shutil
    import subprocess
    import webbrowser
    from pathlib import Path

    cmd_bin = shutil.which("zchat-voice-bridge")
    args: list[str] = []
    if cmd_bin:
        args = [cmd_bin]
    else:
        # fallback: python -m voice_bridge via uv run
        project_cs = Path(__file__).resolve().parent.parent.parent / "zchat-channel-server"
        args = ["uv", "run", "--project", str(project_cs), "python", "-m", "voice_bridge"]

    args += [
        "--host", host,
        "--port", str(port),
        "--cs-url", cs_url,
        "--asr", asr,
        "--tts", tts,
        "--dev-mode",
    ]
    if channel:
        args += ["--channel", channel.lstrip("#")]
    if loopback:
        args += ["--loopback"]
    effective_secret = jwt_secret or _os.environ.get("VOICE_JWT_SECRET", "")
    if effective_secret:
        args += ["--jwt-secret", effective_secret]
    if verbose:
        args += ["-v"]

    url = f"http://{host}:{port}/?channel={channel.lstrip('#')}&customer=dev-user"
    typer.echo(f"Starting voice_bridge: {' '.join(args)}")
    typer.echo(f"Open in browser: {url}")

    if open_browser:
        # 延迟 1s 打开，等 server 监听就绪
        import threading
        import time
        def _open_later():
            time.sleep(1.0)
            try:
                webbrowser.open(url)
            except Exception:
                pass
        threading.Thread(target=_open_later, daemon=True).start()

    try:
        proc = subprocess.run(args)
        raise typer.Exit(proc.returncode)
    except KeyboardInterrupt:
        raise typer.Exit(0)


@voice_app.command("status")
def cmd_voice_status(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port"),
):
    """查 voice_bridge health endpoint。"""
    import urllib.request
    import urllib.error
    url = f"http://{host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            typer.echo(f"{url} → {resp.status} {resp.read().decode().strip()}")
    except urllib.error.URLError as e:
        typer.echo(f"{url} unreachable: {e}")
        raise typer.Exit(1)


# ============================================================
# plugin discovery
# ============================================================

# Registry: which command args get selection lists in the palette plugin.
# "source" = runtime data (resolved by plugin from Zellij events)
# "choices_from" = static data (resolved by CLI at config generation time)
_ARG_SOURCES = {
    "agent stop": {"name": "running_agents"},
    "agent focus": {"name": "running_agents"},
    "agent hide": {"name": "running_agents"},
    "agent restart": {"name": "running_agents"},
    "agent send": {"name": "running_agents"},
    "agent status": {"name": "running_agents"},
    "project use": {"name": "projects"},
    "project remove": {"name": "projects"},
    "project show": {"name": "projects"},
    "project create": {"server": "servers"},
}


@app.command("list-commands", hidden=True)
def cmd_list_commands():
    """Output all CLI commands as JSON (for plugin/integration discovery).

    Includes arg sources and pre-resolved choices where available.
    """
    typer.echo(_get_commands_json())


if __name__ == "__main__":
    app()
