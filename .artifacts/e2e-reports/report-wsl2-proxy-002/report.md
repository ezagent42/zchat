---
type: e2e-report
id: e2e-report-002
status: green
producer: skill-4
created_at: "2026-04-13T15:10:00Z"
related:
  - test-plan: test-plan-005
  - test-diff: test-diff-002
  - eval-doc: eval-wsl2-proxy-003
---

# Test Report: WSL2 proxy 重写验证（fix #40）

## 汇总

| 类型 | 总数 | PASS | FAIL | SKIP |
|------|------|------|------|------|
| 单元测试（自动化） | 12 | 12 | 0 | 0 |
| 人工验证（WSL2 环境） | 4 | 4 | 0 | 0 |
| **合计** | **16** | **16** | **0** | **0** |

**结论：绿灯 ✅**

## 自动化测试结果

```
uv run --no-sync pytest tests/unit/test_wsl2_proxy_rewrite.py -v
platform linux -- Python 3.13.12, pytest-9.0.2

tests/unit/test_wsl2_proxy_rewrite.py::TestWSL2Detection::test_macos_not_detected PASSED
tests/unit/test_wsl2_proxy_rewrite.py::TestWSL2Detection::test_native_linux_not_detected PASSED
tests/unit/test_wsl2_proxy_rewrite.py::TestWSL2Detection::test_wsl2_kernel_case_insensitive PASSED
tests/unit/test_wsl2_proxy_rewrite.py::TestWSL2Detection::test_wsl2_kernel_detected PASSED
tests/unit/test_wsl2_proxy_rewrite.py::TestGetWslHostIp::test_empty_ip_route_output PASSED
tests/unit/test_wsl2_proxy_rewrite.py::TestGetWslHostIp::test_malformed_ip_route_output PASSED
tests/unit/test_wsl2_proxy_rewrite.py::TestGetWslHostIp::test_standard_ip_route_output PASSED
tests/unit/test_wsl2_proxy_rewrite.py::TestProxyRewrite::test_empty_proxy_unchanged PASSED
tests/unit/test_wsl2_proxy_rewrite.py::TestProxyRewrite::test_host_ip_is_127_skipped PASSED
tests/unit/test_wsl2_proxy_rewrite.py::TestProxyRewrite::test_http_proxy_rewritten PASSED
tests/unit/test_wsl2_proxy_rewrite.py::TestProxyRewrite::test_https_proxy_rewritten PASSED
tests/unit/test_wsl2_proxy_rewrite.py::TestProxyRewrite::test_non_localhost_proxy_unchanged PASSED

12 passed in 0.04s
```

验证时间：2026-04-14
运行环境：WSL2 (Linux 6.6.87.2-microsoft-standard-WSL2), Python 3.13.12

## 人工验证结果（WSL2 真实环境）

| TC-ID | 结果 | 验证人 | 时间 | 备注 |
|-------|------|-------|------|------|
| TC-01 | PASS | zyli | 2026-04-13 | proxy 重写成功，Claude 正常启动 |
| TC-02 | PASS | zyli | 2026-04-13 | 重写后地址为 198.18.0.2:7890 |
| TC-03 | PASS | zyli | 2026-04-13 | 非 WSL2 环境 proxy 未被修改 |
| TC-04 | PASS | zyli | 2026-04-13 | 无 proxy 设置时静默跳过 |

## 新增 vs 回归

- **新增测试**：12 个单元测试（全部 PASS）
- **回归**：无回归（原有单元测试不受影响）

## Issue 状态

GitHub issue #40 可关闭。修复完整，测试覆盖充分。
