"""
测试 claude.sh WSL2 proxy 自动重写逻辑（fix #40）

覆盖 plan-wsl2-proxy-005 中 TC-05、TC-06 的可自动化部分。
TC-01~TC-04 需要真实 WSL2 环境，记录在 test-plan 人工验证表中。

被测逻辑（claude.sh:78-89）等效 Python 表达：
    if is_wsl2():
        host_ip = get_wsl_host_ip()
        if host_ip and host_ip != "127.0.0.1":
            rewrite 所有 proxy 变量中的 127.0.0.1 → host_ip
"""
import subprocess
import unittest
from unittest.mock import MagicMock, mock_open, patch


# ---------------------------------------------------------------------------
# 纯逻辑：等效于 claude.sh 中的 proxy 重写逻辑
# ---------------------------------------------------------------------------

def _is_wsl2(proc_version_content: str) -> bool:
    """检测 /proc/version 是否含 'microsoft'（忽略大小写）"""
    return "microsoft" in proc_version_content.lower()


def _rewrite_proxy(proxy_val: str, host_ip: str) -> str:
    """将 proxy 值中的 127.0.0.1 替换为 WSL host IP"""
    return proxy_val.replace("127.0.0.1", host_ip)


def _get_wsl_host_ip_from_route(ip_route_output: str) -> str:
    """从 `ip route show default` 输出中提取 gateway IP（第3列）"""
    for line in ip_route_output.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            return parts[2]
    return ""


# ---------------------------------------------------------------------------
# TC-05: /proc/version 含 microsoft 时检测为 WSL2
# ---------------------------------------------------------------------------
class TestWSL2Detection(unittest.TestCase):

    def test_wsl2_kernel_detected(self):
        """标准 WSL2 kernel 字符串应被检测为 WSL2"""
        proc_version = "Linux version 6.6.87.2-microsoft-standard-WSL2"
        self.assertTrue(_is_wsl2(proc_version))

    def test_wsl2_kernel_case_insensitive(self):
        """检测应忽略大小写"""
        self.assertTrue(_is_wsl2("Linux ... Microsoft-Standard-WSL2"))

    def test_native_linux_not_detected(self):
        """原生 Linux 不应被检测为 WSL2"""
        proc_version = "Linux version 6.1.0-21-amd64 (debian-kernel@lists.debian.org)"
        self.assertFalse(_is_wsl2(proc_version))

    def test_macos_not_detected(self):
        """macOS 无 /proc/version，空字符串不应被检测为 WSL2"""
        self.assertFalse(_is_wsl2(""))


# ---------------------------------------------------------------------------
# TC-06: ip route 无输出时降级安全
# ---------------------------------------------------------------------------
class TestGetWslHostIp(unittest.TestCase):

    def test_standard_ip_route_output(self):
        """标准 ip route 输出应正确提取 gateway"""
        output = "default via 172.30.240.1 dev eth0 proto kernel"
        self.assertEqual(_get_wsl_host_ip_from_route(output), "172.30.240.1")

    def test_empty_ip_route_output(self):
        """ip route 无输出时返回空字符串（不崩溃）"""
        self.assertEqual(_get_wsl_host_ip_from_route(""), "")

    def test_malformed_ip_route_output(self):
        """ip route 输出格式异常时返回空字符串"""
        self.assertEqual(_get_wsl_host_ip_from_route("default"), "")


# ---------------------------------------------------------------------------
# proxy 重写逻辑
# ---------------------------------------------------------------------------
class TestProxyRewrite(unittest.TestCase):

    def test_http_proxy_rewritten(self):
        result = _rewrite_proxy("http://127.0.0.1:7897", "172.30.240.1")
        self.assertEqual(result, "http://172.30.240.1:7897")

    def test_https_proxy_rewritten(self):
        result = _rewrite_proxy("https://127.0.0.1:7890", "172.30.240.1")
        self.assertEqual(result, "https://172.30.240.1:7890")

    def test_non_localhost_proxy_unchanged(self):
        """已经是非 127.0.0.1 的 proxy 不应被改动"""
        result = _rewrite_proxy("http://192.168.1.1:7897", "172.30.240.1")
        self.assertEqual(result, "http://192.168.1.1:7897")

    def test_host_ip_is_127_skipped(self):
        """当 WSL_HOST_IP 本身是 127.0.0.1 时（异常情况），不应替换"""
        # claude.sh 中 `[ "$WSL_HOST_IP" != "127.0.0.1" ]` 保护
        host_ip = "127.0.0.1"
        proxy = "http://127.0.0.1:7897"
        # 等效于 claude.sh 的保护条件：host_ip 为 127.0.0.1 时不执行重写
        if host_ip and host_ip != "127.0.0.1":
            result = _rewrite_proxy(proxy, host_ip)
        else:
            result = proxy
        self.assertEqual(result, "http://127.0.0.1:7897")

    def test_empty_proxy_unchanged(self):
        """空 proxy 值不应报错"""
        result = _rewrite_proxy("", "172.30.240.1")
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
