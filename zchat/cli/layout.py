"""KDL layout generation for Zellij sessions."""
from __future__ import annotations

import os
from pathlib import Path


def _escape_kdl(s: str) -> str:
    """Escape a string for use inside KDL double quotes."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _plugins_dir() -> str:
    """Return the absolute path to the zchat plugins directory."""
    from zchat.cli.project import ZCHAT_DIR
    return os.path.join(ZCHAT_DIR, "plugins")


def generate_layout(
    config: dict,
    state: dict,
    weechat_cmd: str = "",
    project_name: str = "",
) -> str:
    """Generate KDL layout string from project config + agent state.

    The layout always includes a ``default_tab_template`` with tab-bar and
    status-bar plugins, a WeeChat tab (always first), a ctl tab for the CLI,
    and tabs for any previously-running agents (from state).
    """
    lines = ["layout {"]

    # Default tab template with status bars
    lines.append("    default_tab_template {")
    lines.append('        pane size=1 borderless=true {')
    lines.append('            plugin location="zellij:tab-bar"')
    lines.append("        }")
    lines.append("        children")
    plugins = _plugins_dir()
    lines.append('        pane size=1 borderless=true {')
    lines.append(f'            plugin location="file:{plugins}/zchat-status.wasm"')
    lines.append("        }")
    lines.append('        pane size=2 borderless=true {')
    lines.append('            plugin location="zellij:status-bar"')
    lines.append("        }")
    lines.append("    }")

    # WeeChat tab (always first, focused)
    prefix = f"{project_name}/" if project_name else ""
    if weechat_cmd:
        lines.append(f'    tab name="{prefix}chat" focus=true {{')
        lines.append(f'        pane name="weechat" command="bash" {{')
        lines.append(f'            args "-c" "{_escape_kdl(weechat_cmd)}"')
        lines.append("        }")
        lines.append("    }")
    else:
        lines.append(f'    tab name="{prefix}chat" focus=true {{')
        lines.append("        pane")
        lines.append("    }")

    # Ctl tab for CLI
    lines.append(f'    tab name="{prefix}ctl" {{')
    lines.append("        pane")
    lines.append("    }")

    # Agent tabs (from state — restore previously running agents)
    for name, agent in state.get("agents", {}).items():
        if agent.get("status") not in ("running", "starting"):
            continue
        ws = agent.get("workspace", "")
        tab_name = agent.get("tab_name") or agent.get("window_name") or name
        lines.append(f'    tab name="{tab_name}" {{')
        if ws:
            cmd = f"cd {ws} && source .zchat-env && bash start.sh"
            lines.append(f'        pane command="bash" {{')
            lines.append(f'            args "-c" "{_escape_kdl(cmd)}"')
            lines.append("        }")
        else:
            lines.append("        pane")
        lines.append("    }")

    lines.append("}")
    return "\n".join(lines)


def write_layout(
    project_dir: Path,
    config: dict,
    state: dict,
    weechat_cmd: str = "",
    project_name: str = "",
) -> Path:
    """Generate and write layout.kdl to project directory. Returns path."""
    kdl = generate_layout(config, state, weechat_cmd=weechat_cmd, project_name=project_name)
    layout_path = Path(project_dir) / "layout.kdl"
    layout_path.write_text(kdl)
    return layout_path
