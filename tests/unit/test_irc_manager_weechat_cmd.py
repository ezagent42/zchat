"""
测试 irc_manager.py build_weechat_cmd() 中 WeeChat server cache 强制更新逻辑（fix #42）

覆盖 plan-weechat-cache-007 中 TC-01 ~ TC-06。

核心断言：/server add 之后必须有 /set addresses、/set ssl、/set nicks
来覆盖 WeeChat 缓存，防止切换服务器后仍连接旧地址。
"""
import os
import unittest
from unittest.mock import MagicMock, patch

from zchat.cli.irc_manager import IrcManager


def _make_manager(server="127.0.0.1", port=6667, tls=False, nick="testuser"):
    """构造最小化的 IrcManager，mock 掉文件系统和认证依赖。"""
    config = {
        "irc": {"server": server, "port": port, "tls": tls},
        "default_channels": ["#general"],
        "agents": {"username": nick},
        "env_file": "",
    }
    state_file = "/tmp/zchat_test_state/state.json"

    mgr = IrcManager.__new__(IrcManager)
    mgr.config = config
    mgr._state_file = state_file
    mgr._find_weechat_plugin = MagicMock(return_value=None)
    return mgr


def _build_cmd(server="127.0.0.1", port=6667, tls=False, nick="testuser"):
    mgr = _make_manager(server=server, port=port, tls=tls, nick=nick)
    with patch("zchat.cli.auth.get_username", return_value=nick), \
         patch("zchat.cli.auth.get_credentials", return_value=None), \
         patch("os.makedirs"):
        return mgr.build_weechat_cmd(nick_override=nick)


class TestWeechatCmdAddresses(unittest.TestCase):
    """TC-01: 命令中包含 /set addresses"""

    def test_set_addresses_present(self):
        cmd = _build_cmd(server="127.0.0.1", port=6667)
        self.assertIn('/set irc.server.', cmd)
        self.assertIn('.addresses "127.0.0.1/6667"', cmd)

    def test_set_addresses_after_server_add(self):
        """TC-05: /set addresses 必须出现在 /server add 之后"""
        cmd = _build_cmd(server="127.0.0.1", port=6667)
        add_pos = cmd.index("/server add")
        addr_pos = cmd.index(".addresses")
        self.assertGreater(addr_pos, add_pos)


class TestWeechatCmdSsl(unittest.TestCase):
    """TC-02/03: /set ssl 值随 TLS 配置变化"""

    def test_ssl_off_when_tls_false(self):
        """TC-02: TLS=False 时生成 ssl off"""
        cmd = _build_cmd(tls=False)
        self.assertIn(".ssl off", cmd)
        self.assertNotIn(".ssl on", cmd)

    def test_ssl_on_when_tls_true(self):
        """TC-03: TLS=True 时生成 ssl on"""
        cmd = _build_cmd(tls=True)
        self.assertIn(".ssl on", cmd)
        self.assertNotIn(".ssl off", cmd)


class TestWeechatCmdNicks(unittest.TestCase):
    """TC-04: 命令中包含 /set nicks"""

    def test_set_nicks_present(self):
        cmd = _build_cmd(nick="testuser")
        self.assertIn('.nicks "testuser"', cmd)

    def test_set_nicks_reflects_nick_override(self):
        cmd = _build_cmd(nick="alice")
        self.assertIn('.nicks "alice"', cmd)


class TestWeechatCmdServerChange(unittest.TestCase):
    """TC-06: server/port 变更后命令反映新值"""

    def test_new_server_reflected_in_addresses(self):
        cmd = _build_cmd(server="new.host", port=7000)
        self.assertIn('.addresses "new.host/7000"', cmd)

    def test_new_server_reflected_in_server_add(self):
        cmd = _build_cmd(server="new.host", port=7000)
        self.assertIn("/server add", cmd)
        self.assertIn("new.host/7000", cmd)


if __name__ == "__main__":
    unittest.main()
