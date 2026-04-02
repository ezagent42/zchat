"""Update checking and upgrade logic."""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone, date

from zchat.cli.project import ZCHAT_DIR

UPDATE_STATE_FILE = os.path.join(ZCHAT_DIR, "update.json")

_ZCHAT_REPO = "https://github.com/ezagent42/zchat.git"
_CHANNEL_REPO = "https://github.com/ezagent42/claude-zchat-channel.git"

_DEFAULT_STATE = {
    "last_check": "",
    "channel": "main",
    "zchat": {"installed_ref": "", "remote_ref": ""},
    "channel_server": {"installed_ref": "", "remote_ref": ""},
    "update_available": False,
}


def load_update_state(path: str = UPDATE_STATE_FILE) -> dict:
    """Load update state from JSON file. Returns defaults if missing."""
    if os.path.isfile(path):
        with open(path) as f:
            data = json.load(f)
        for key, default in _DEFAULT_STATE.items():
            data.setdefault(key, default if not isinstance(default, dict) else dict(default))
        for pkg in ("zchat", "channel_server"):
            if isinstance(data.get(pkg), dict):
                data[pkg].setdefault("installed_ref", "")
                data[pkg].setdefault("remote_ref", "")
        return data
    return json.loads(json.dumps(_DEFAULT_STATE))


def save_update_state(state: dict, path: str = UPDATE_STATE_FILE) -> None:
    """Save update state to JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def should_check_today(state: dict) -> bool:
    """Return True if no check has been done today."""
    last = state.get("last_check", "")
    if not last:
        return True
    try:
        last_date = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").date()
        return last_date < date.today()
    except ValueError:
        return True


def _check_remote_git(repo_url: str, branch: str) -> str | None:
    """Get latest commit hash (7 chars) from a git remote. Returns None on failure."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", repo_url, f"refs/heads/{branch}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split()[0][:7]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _check_remote_pypi(package: str) -> str | None:
    """Get latest version from PyPI. Returns None on failure."""
    try:
        url = f"https://pypi.org/pypi/{package}/json"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data["info"]["version"]
    except Exception:
        return None


def check_for_updates(state: dict) -> dict:
    """Check remote versions and update state. Does not download anything."""
    channel = state["channel"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state["last_check"] = now

    if channel in ("main", "dev"):
        zchat_ref = _check_remote_git(_ZCHAT_REPO, channel)
        channel_ref = _check_remote_git(_CHANNEL_REPO, channel)
        if zchat_ref:
            state["zchat"]["remote_ref"] = zchat_ref
        if channel_ref:
            state["channel_server"]["remote_ref"] = channel_ref
    elif channel == "release":
        zchat_ver = _check_remote_pypi("zchat")
        channel_ver = _check_remote_pypi("zchat-channel-server")
        if zchat_ver:
            state["zchat"]["remote_ref"] = zchat_ver
        if channel_ver:
            state["channel_server"]["remote_ref"] = channel_ver

    # If installed_ref is empty (fresh install), set it to remote_ref
    for pkg in ("zchat", "channel_server"):
        if not state[pkg]["installed_ref"] and state[pkg]["remote_ref"]:
            state[pkg]["installed_ref"] = state[pkg]["remote_ref"]

    state["update_available"] = (
        (state["zchat"]["remote_ref"] != "" and
         state["zchat"]["remote_ref"] != state["zchat"]["installed_ref"])
        or
        (state["channel_server"]["remote_ref"] != "" and
         state["channel_server"]["remote_ref"] != state["channel_server"]["installed_ref"])
    )
    return state


def _build_install_args(channel: str) -> list[str]:
    """Build uv tool install package specs for the given channel."""
    if channel in ("main", "dev"):
        return [
            f"zchat @ git+{_ZCHAT_REPO}@{channel}",
            f"zchat-channel-server @ git+{_CHANNEL_REPO}@{channel}",
        ]
    else:
        return ["zchat", "zchat-channel-server"]


def run_upgrade(channel: str) -> bool:
    """Run uv tool install --force for both packages. Returns True on success.

    Atomic: if second fails, rolls back the first.
    """
    specs = _build_install_args(channel)
    installed: list[str] = []
    for spec in specs:
        result = subprocess.run(
            ["uv", "tool", "install", "--force", spec],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            state = load_update_state()
            old_channel = state.get("channel", channel)
            old_specs = _build_install_args(old_channel)
            for old_spec in old_specs[:len(installed)]:
                subprocess.run(
                    ["uv", "tool", "install", "--force", old_spec],
                    capture_output=True, text=True,
                )
            return False
        installed.append(spec)
    return True


def _background_check_main() -> None:
    """Entry point for background update check (called via subprocess)."""
    import sys
    auto_upgrade = "--auto-upgrade" in sys.argv
    state = load_update_state()
    state = check_for_updates(state)
    if state.get("update_available") and auto_upgrade:
        ok = run_upgrade(state["channel"])
        if ok:
            state["zchat"]["installed_ref"] = state["zchat"]["remote_ref"]
            state["channel_server"]["installed_ref"] = state["channel_server"]["remote_ref"]
            state["update_available"] = False
    save_update_state(state)


if __name__ == "__main__":
    _background_check_main()
