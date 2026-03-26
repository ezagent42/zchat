#!/usr/bin/env python3
# wc-agent/cli.py
"""wc-agent: Claude Code agent lifecycle management CLI."""

import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))
from wc_agent.config import load_config
from wc_agent.agent_manager import AgentManager


def find_config() -> str:
    """Find weechat-claude.toml in current dir or parent dirs."""
    path = os.getcwd()
    while path != "/":
        candidate = os.path.join(path, "weechat-claude.toml")
        if os.path.isfile(candidate):
            return candidate
        path = os.path.dirname(path)
    return "weechat-claude.toml"


def make_manager(args) -> AgentManager:
    config_path = getattr(args, "config", None) or find_config()
    cfg = load_config(config_path)
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmux_session = getattr(args, "tmux_session", None) or "weechat-claude"
    return AgentManager(
        irc_server=cfg["irc"]["server"],
        irc_port=cfg["irc"]["port"],
        irc_tls=cfg["irc"].get("tls", False),
        channel_server_dir=os.path.join(script_dir, "weechat-channel-server"),
        username=cfg["agents"]["username"],
        default_channels=cfg["agents"]["default_channels"],
        tmux_session=tmux_session,
    )


def cmd_start(args):
    if subprocess.run(["pgrep", "-x", "ergo"], capture_output=True).returncode != 0:
        ergo_conf = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ergo.yaml")
        if os.path.isfile(ergo_conf):
            print("Starting ergo IRC server...")
            subprocess.Popen(["ergo", "run", "--conf", ergo_conf],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)
    mgr = make_manager(args)
    workspace = getattr(args, "workspace", None) or os.getcwd()
    info = mgr.create("agent0", workspace=workspace)
    print(f"Created {mgr.scoped('agent0')}")
    print(f"  pane: {info['pane_id']}")
    print(f"  workspace: {info['workspace']}")


def cmd_create(args):
    mgr = make_manager(args)
    info = mgr.create(args.name, workspace=args.workspace)
    print(f"Created {mgr.scoped(args.name)}")
    print(f"  pane: {info['pane_id']}")
    print(f"  workspace: {info['workspace']}")


def cmd_stop(args):
    mgr = make_manager(args)
    name = mgr.scoped(args.name)
    mgr.stop(args.name, force=True)
    print(f"Stopped {name}")


def cmd_restart(args):
    mgr = make_manager(args)
    name = mgr.scoped(args.name)
    mgr.restart(args.name)
    print(f"Restarted {name}")


def cmd_list(args):
    mgr = make_manager(args)
    agents = mgr.list_agents()
    if not agents:
        print("No agents")
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
        channels = ", ".join(info.get("channels", []))
        print(f"  {name}\t{status}\t{uptime}\t{pane}\t{channels}\t{ws}")


def cmd_status(args):
    mgr = make_manager(args)
    info = mgr.get_status(args.name)
    name = mgr.scoped(args.name)
    elapsed = time.time() - info.get("created_at", time.time())
    mins, secs = divmod(int(elapsed), 60)
    print(f"{name}")
    print(f"  status:    {info['status']}")
    print(f"  uptime:    {mins}m {secs}s")
    print(f"  pane:      {info.get('pane_id', '—')}")
    print(f"  workspace: {info.get('workspace', '—')}")
    print(f"  channels:  {', '.join(info.get('channels', []))}")


def cmd_shutdown(args):
    mgr = make_manager(args)
    agents = mgr.list_agents()
    for name in list(agents.keys()):
        if agents[name]["status"] != "offline":
            mgr.stop(name, force=True)
            print(f"Stopped {name}")
    subprocess.run(["pkill", "-x", "ergo"], capture_output=True)
    print("Shutdown complete")


def main():
    parser = argparse.ArgumentParser(prog="wc-agent", description="Claude Code agent lifecycle management")
    parser.add_argument("--config", help="Path to weechat-claude.toml")
    parser.add_argument("--tmux-session", dest="tmux_session", help="tmux session name (default: weechat-claude)")
    sub = parser.add_subparsers(dest="command")

    p_start = sub.add_parser("start", help="Start ergo + primary agent")
    p_start.add_argument("--workspace", help="Agent workspace path")

    p_create = sub.add_parser("create", help="Create new agent")
    p_create.add_argument("name")
    p_create.add_argument("--workspace")

    p_stop = sub.add_parser("stop", help="Stop agent")
    p_stop.add_argument("name")

    p_restart = sub.add_parser("restart", help="Restart agent")
    p_restart.add_argument("name")

    sub.add_parser("list", help="List agents")

    p_status = sub.add_parser("status", help="Agent details")
    p_status.add_argument("name")

    sub.add_parser("shutdown", help="Stop all agents + ergo")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cmds = {
        "start": cmd_start, "create": cmd_create, "stop": cmd_stop,
        "restart": cmd_restart, "list": cmd_list, "status": cmd_status,
        "shutdown": cmd_shutdown,
    }
    try:
        cmds[args.command](args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
