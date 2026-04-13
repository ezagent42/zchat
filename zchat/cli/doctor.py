# zchat/cli/doctor.py
"""Environment diagnostics and component setup."""
from __future__ import annotations

import shutil
import socket
import subprocess
import urllib.request
from pathlib import Path

import typer

from zchat.cli.project import list_projects, load_project_config, resolve_project

WEECHAT_PLUGIN_URL = "https://raw.githubusercontent.com/ezagent42/weechat-zchat-plugin/main/zchat.py"

# WeeChat plugin directories (in priority order)
_WEECHAT_DIRS = [
    Path("~/.local/share/weechat").expanduser(),
    Path("~/.weechat").expanduser(),
]


def _weechat_autoload_dir() -> str | None:
    """Find the WeeChat python autoload directory, or None."""
    for base in _WEECHAT_DIRS:
        if base.is_dir():
            return str(base / "python" / "autoload")
    return None


def _weechat_plugin_installed() -> str | None:
    """Return path to installed zchat.py plugin, or None."""
    for base in _WEECHAT_DIRS:
        path = base / "python" / "autoload" / "zchat.py"
        if path.is_file():
            return str(path)
    return None


_VERSION_CMDS = {
    "uv": ["--version"],       # "uv 0.6.x"
    "python3": ["--version"],  # "Python 3.11.x"
    "tmux": ["-V"],            # "tmux 3.6a"
    "tmuxp": ["--version"],    # "tmuxp, version 1.x.x"
    "claude": ["--version"],   # "2.1.86 (Claude Code)"
    "zchat-channel": None,     # MCP server, no --version
    "ergo": ["--version"],     # "ergo-2.18.0"
    "weechat": ["--version"],  # "4.8.2"
}


def _check_command(name: str) -> tuple[bool, str]:
    """Check if a command exists and return (found, version_or_empty)."""
    path = shutil.which(name)
    if not path:
        return False, ""
    args = _VERSION_CMDS.get(name, ["--version"])
    if args is None:
        return True, ""  # command exists but has no version flag
    try:
        out = subprocess.run([name] + args, capture_output=True, text=True, timeout=5)
        version = (out.stdout.strip() or out.stderr.strip()).split("\n")[0]
        # Strip program name prefix
        for prefix in [f"{name} ", f"{name}-", "zellij "]:
            if version.lower().startswith(prefix.lower()):
                version = version[len(prefix):]
                break
        return True, version[:40]
    except Exception:
        return True, ""


def run_doctor():
    """Check all dependencies and report status."""
    current = resolve_project()

    checks = [
        ("uv", True, "curl -LsSf https://astral.sh/uv/install.sh | sh"),
        ("python3", True, "uv python install 3.11"),
        ("zellij", True, "brew install zellij"),
        ("claude", True, "https://docs.anthropic.com/en/docs/claude-code"),
        ("zchat-channel", True, "uv tool install zchat-channel-server"),
        ("ergo", False, "brew install ezagent42/zchat/ergo"),
        ("weechat", False, "brew install weechat"),
    ]

    required_ok = 0
    required_total = 0
    optional_missing = 0
    optional_total = 0

    for name, required, hint in checks:
        found, version = _check_command(name)
        label = "required" if required else "optional"
        if required:
            required_total += 1
        else:
            optional_total += 1

        if found:
            ver = f"  {version}" if version else ""
            typer.echo(f"  ✓ {name:<16}{ver}  ({label})")
            if required:
                required_ok += 1
        else:
            typer.echo(f"  ✗ {name:<16}  ({label}, {hint})")
            if not required:
                optional_missing += 1

    # Check weechat plugin
    plugin_path = _weechat_plugin_installed()
    if plugin_path:
        typer.echo(f"  ✓ weechat plugin    installed  (optional)")
    else:
        typer.echo(f"  ✗ weechat plugin    (optional, run: zchat setup weechat)")
        optional_missing += 1
    optional_total += 1

    # Check pytest availability
    try:
        out = subprocess.run(
            ["uv", "run", "python", "-m", "pytest", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if "pytest" in out.stdout:
            ver = out.stdout.strip().split("\n")[0]
            typer.echo(f"  ✓ pytest            {ver}  (optional)")
        else:
            raise RuntimeError
    except Exception:
        typer.echo(f"  ✗ pytest            (optional, run: uv sync)")
        optional_missing += 1
    optional_total += 1

    # Check IRC port free — read from active project config, fall back to 6667
    irc_port = 6667
    if current:
        try:
            cfg = load_project_config(current)
            irc_port = cfg.get("irc", {}).get("port", 6667)
        except Exception:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        port_in_use = s.connect_ex(("127.0.0.1", irc_port)) == 0
    if port_in_use:
        typer.echo(f"  ✗ port {irc_port}         in use — local ergo may fail to bind  (optional)")
        optional_missing += 1
    else:
        typer.echo(f"  ✓ port {irc_port}         free  (optional)")
    optional_total += 1

    # Check submodules initialised
    root = Path(__file__).parent.parent.parent
    submodules = {
        "zchat-channel-server": root / "zchat-channel-server" / "pyproject.toml",
        "zchat-protocol": root / "zchat-protocol" / "pyproject.toml",
    }
    for name, marker in submodules.items():
        if marker.is_file():
            typer.echo(f"  ✓ {name:<16}  (optional)")
        else:
            typer.echo(f"  ✗ {name:<16}  (optional, run: git submodule update --init)")
            optional_missing += 1
        optional_total += 1

    typer.echo("")

    # Project info
    projects = list_projects()
    if projects:
        typer.echo(f"  Projects: {', '.join(projects)}")
        if current:
            typer.echo(f"  Active:   {current}")
    else:
        typer.echo("  No projects configured. Run: zchat project create <name>")

    # Update status
    try:
        from zchat.cli.update import load_update_state
        state = load_update_state()
        if state.get("update_available"):
            typer.echo(f"  💡 Update available — run: zchat upgrade")
        elif state.get("last_check"):
            typer.echo(f"  ✓ Up to date (checked: {state['last_check'][:10]})")
    except Exception:
        pass

    typer.echo("")
    req_status = "✓" if required_ok == required_total else "✗"
    typer.echo(f"  {req_status} {required_ok}/{required_total} required  |  {optional_missing}/{optional_total} optional missing")

    if required_ok < required_total:
        raise typer.Exit(1)


def setup_weechat(force: bool = False):
    """Download and install the WeeChat zchat plugin."""
    # Check weechat is installed
    if not shutil.which("weechat"):
        typer.echo("Error: weechat not found. Install it first:")
        typer.echo("  brew install weechat")
        raise typer.Exit(1)

    autoload = _weechat_autoload_dir()
    if not autoload:
        # WeeChat installed but no config dir yet — use default
        autoload = str(_WEECHAT_DIRS[0] / "python" / "autoload")

    target = str(Path(autoload) / "zchat.py")

    if Path(target).is_file() and not force:
        overwrite = typer.confirm(f"Plugin already exists at {target}. Overwrite?", default=False)
        if not overwrite:
            typer.echo("Skipped.")
            return

    Path(autoload).mkdir(parents=True, exist_ok=True)

    typer.echo(f"Downloading zchat.py from GitHub...")
    try:
        urllib.request.urlretrieve(WEECHAT_PLUGIN_URL, target)
    except Exception as e:
        typer.echo(f"Error downloading plugin: {e}")
        raise typer.Exit(1)

    typer.echo(f"Installed to {target}")
    typer.echo("Plugin will load automatically next time WeeChat starts.")
