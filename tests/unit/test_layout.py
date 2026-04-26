"""Tests for KDL layout generation."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from zchat.cli.layout import generate_layout, write_layout


def test_generate_layout_with_weechat_only():
    config = {"default_channels": ["#general"]}
    state = {"agents": {}}
    weechat_cmd = 'weechat -r "/server add test 127.0.0.1/6667"'

    kdl = generate_layout(config, state, weechat_cmd=weechat_cmd)
    assert "layout {" in kdl
    assert 'tab name="chat"' in kdl
    assert "weechat" in kdl
    assert 'tab name="ctl"' in kdl


def test_generate_layout_with_project_prefix():
    config = {}
    state = {"agents": {}}
    kdl = generate_layout(config, state, weechat_cmd="weechat", project_name="local")
    assert 'tab name="local/chat"' in kdl
    assert 'tab name="local/ctl"' in kdl


def test_generate_layout_with_agents():
    config = {}
    state = {
        "agents": {
            "alice-agent0": {
                "tab_name": "alice-agent0",
                "workspace": "/tmp/ws",
                "status": "running",
            },
            "alice-helper": {
                "tab_name": "alice-helper",
                "workspace": "/tmp/ws2",
                "status": "offline",
            },
        }
    }
    kdl = generate_layout(config, state, weechat_cmd="weechat")
    assert 'tab name="alice-agent0"' in kdl
    assert "/tmp/ws" in kdl
    # Offline agents should NOT be included
    assert "alice-helper" not in kdl


def test_generate_layout_has_default_tab_template():
    config = {}
    state = {"agents": {}}
    kdl = generate_layout(config, state)
    assert "default_tab_template" in kdl
    assert "zellij:tab-bar" in kdl
    assert "zellij:status-bar" in kdl


def test_generate_layout_has_zchat_status_plugin_when_wasm_present():
    """Layout 包含 zchat-status wasm 插件（仅当 wasm 文件存在时）。"""
    config = {}
    state = {"agents": {}}
    with patch("zchat.cli.layout._wasm_present", return_value=True):
        kdl = generate_layout(config, state)
    assert "zchat-status.wasm" in kdl


def test_generate_layout_skips_zchat_status_when_wasm_missing():
    """Layout 不包含 wasm 插件（wasm 文件不存在）。"""
    config = {}
    state = {"agents": {}}
    with patch("zchat.cli.layout._wasm_present", return_value=False):
        kdl = generate_layout(config, state)
    assert "zchat-status.wasm" not in kdl


def test_write_layout_creates_file(tmp_path):
    config = {}
    state = {"agents": {}}
    path = write_layout(tmp_path, config, state, weechat_cmd="weechat")
    assert path.exists()
    assert path.name == "layout.kdl"
    content = path.read_text()
    assert "layout {" in content


def test_generate_layout_escapes_quotes():
    config = {}
    state = {"agents": {}}
    cmd = 'weechat -r "/server add \\"test\\" 127.0.0.1"'
    kdl = generate_layout(config, state, weechat_cmd=cmd)
    # Should not have unescaped quotes breaking KDL
    assert "layout {" in kdl


def test_backward_compat_window_name():
    """State with legacy 'window_name' instead of 'tab_name' should still work."""
    config = {}
    state = {
        "agents": {
            "alice-agent0": {
                "window_name": "alice-agent0",
                "workspace": "/tmp/ws",
                "status": "running",
            },
        }
    }
    kdl = generate_layout(config, state, weechat_cmd="weechat")
    assert 'tab name="alice-agent0"' in kdl
