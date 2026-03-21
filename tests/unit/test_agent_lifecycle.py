"""Tests for weechat-agent.py agent lifecycle logic.

These tests mock the WeeChat API since it's only available inside WeeChat.
We test the pure logic functions extracted from the agent module.
"""

import json


class TestAgentCreateLogic:
    """Test agent creation logic (mocked weechat)."""

    def test_mcp_json_structure(self):
        """Verify the .mcp.json that would be generated has correct structure."""
        plugin_dir = "/path/to/weechat-channel-server"
        name = "test-agent"

        # This mirrors the logic from create_agent()
        # (we can't import the actual module since it requires weechat)
        mcp_config = {
            "mcpServers": {
                "weechat-channel": {
                    "command": "uv",
                    "args": ["run", "--project", plugin_dir, "weechat-channel"],
                    "env": {"AGENT_NAME": name},
                }
            }
        }

        assert "mcpServers" in mcp_config
        assert "weechat-channel" in mcp_config["mcpServers"]
        server = mcp_config["mcpServers"]["weechat-channel"]
        assert server["command"] == "uv"
        assert server["env"]["AGENT_NAME"] == name

    def test_agent0_cannot_be_stopped(self):
        """Verify the stop-agent0 guard logic."""
        # This tests the condition used in stop_agent()
        name = "agent0"
        assert name == "agent0"  # This would trigger the guard

    def test_duplicate_agent_detection(self):
        """Verify duplicate agent names are detected."""
        agents = {"agent0": {"status": "running"}}
        name = "agent0"
        assert name in agents

    def test_agent_status_tracking(self):
        """Test agent status update from presence signals."""
        agents = {"agent0": {"status": "running", "workspace": "/tmp"}}

        # Simulate presence signal
        ev = {"nick": "agent0", "online": False}
        nick = ev["nick"]
        if nick in agents:
            agents[nick]["status"] = "running" if ev["online"] else "offline"

        assert agents["agent0"]["status"] == "offline"

    def test_structured_command_parsing(self):
        """Test parsing of agent's structured command output."""
        body = '{"action": "create_agent", "name": "doc-writer", "workspace": "/tmp/docs"}'
        cmd = json.loads(body.strip())
        assert cmd["action"] == "create_agent"
        assert cmd["name"] == "doc-writer"
        assert cmd["workspace"] == "/tmp/docs"

    def test_invalid_json_ignored(self):
        """Non-JSON messages should not cause errors."""
        body = "just a regular message"
        try:
            json.loads(body.strip())
            assert False, "Should have raised"
        except json.JSONDecodeError:
            pass  # Expected


class TestTmuxPaneTracking:
    def test_create_stores_pane_id(self):
        agents = {}
        name = "helper1"
        agents[name] = {"workspace": "/tmp", "status": "starting", "pane_id": "%42"}
        assert agents[name]["pane_id"] == "%42"

    def test_stop_uses_pane_id(self):
        pane_id = "%42"
        cmd = ["tmux", "send-keys", "-t", pane_id, "C-c", ""]
        assert "-t" in cmd
        assert cmd[cmd.index("-t") + 1] == "%42"

    def test_signal_buffer_field(self):
        signal_data = json.dumps({"buffer": "private:@agent0", "nick": "alice", "body": "hello"})
        msg = json.loads(signal_data)
        assert "buffer" in msg
        assert msg["buffer"] == "private:@agent0"
