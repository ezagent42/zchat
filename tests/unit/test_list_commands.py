"""Tests for the hidden list-commands CLI command."""
import json

from typer.testing import CliRunner
from zchat.cli.app import app

runner = CliRunner()


def test_list_commands_returns_json():
    result = runner.invoke(app, ["list-commands"])
    assert result.exit_code == 0, result.output
    commands = json.loads(result.output)
    assert isinstance(commands, list)
    names = [c["name"] for c in commands]
    assert "agent create" in names
    assert "shutdown" in names


def test_list_commands_includes_args():
    result = runner.invoke(app, ["list-commands"])
    commands = json.loads(result.output)
    agent_create = next(c for c in commands if c["name"] == "agent create")
    arg_names = [a["name"] for a in agent_create["args"]]
    assert "name" in arg_names


def test_list_commands_includes_source():
    result = runner.invoke(app, ["list-commands"])
    commands = json.loads(result.output)
    agent_stop = next(c for c in commands if c["name"] == "agent stop")
    name_arg = next(a for a in agent_stop["args"] if a["name"] == "name")
    assert name_arg["source"] == "running_agents"


def test_list_commands_no_source_for_free_input():
    result = runner.invoke(app, ["list-commands"])
    commands = json.loads(result.output)
    agent_create = next(c for c in commands if c["name"] == "agent create")
    name_arg = next(a for a in agent_create["args"] if a["name"] == "name")
    assert "source" not in name_arg


def test_agent_list_json_flag_exists():
    """agent list --json should be a recognized option."""
    result = runner.invoke(app, ["agent", "list", "--json", "--help"])
    # --help exits 0 and shows the option
    assert result.exit_code == 0
    # Strip ANSI escape codes before checking — rich/typer may insert color
    # sequences that split "--json" into "-" + ANSI + "-json".
    import re
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "--json" in plain


def test_list_commands_excludes_hidden():
    """list-commands itself is hidden and should not appear."""
    result = runner.invoke(app, ["list-commands"])
    commands = json.loads(result.output)
    names = [c["name"] for c in commands]
    assert "list-commands" not in names


def test_list_commands_includes_choices():
    """Args with static sources should include choices from defaults.toml."""
    from zchat.cli.app import _get_commands_json
    from zchat.cli.defaults import server_presets
    commands = json.loads(_get_commands_json())
    proj_create = next(c for c in commands if c["name"] == "project create")
    server_arg = next(a for a in proj_create["args"] if a["name"] == "server")
    assert "choices" in server_arg
    # Values should match preset names from defaults.toml
    presets = server_presets()
    values = {c["value"] for c in server_arg["choices"]}
    for preset_name in presets:
        assert preset_name in values
    # Each choice carries the label from defaults.toml
    for choice in server_arg["choices"]:
        if choice["value"] in presets:
            assert choice["label"] == presets[choice["value"]]["label"]
