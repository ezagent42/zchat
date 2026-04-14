---
type: test-diff
id: test-diff-002
status: merged
producer: skill-3
created_at: "2026-04-13T15:00:00Z"
commit: 844cbdf
related:
  - test-plan: test-plan-005
  - eval-doc: eval-wsl2-proxy-003
---

# Test Diff: WSL2 proxy 重写单元测试（fix #40）

## 来源
- test-plan: `test-plan-005`（TC-05、TC-06 的自动化部分）
- 新增文件: `tests/unit/test_wsl2_proxy_rewrite.py`

## 测试策略

`claude.sh` 是纯 bash 脚本，直接测试需引入 bats-core（当前未引入）。
将 `claude.sh:78-89` 的核心逻辑等效提取为 Python 函数，用 pytest 单测。

## 新增测试

### 文件：`tests/unit/test_wsl2_proxy_rewrite.py`（+121 行）

| 测试类 | 测试方法 | 覆盖 TC | 断言 |
|-------|---------|---------|------|
| TestWSL2Detection | test_wsl2_kernel_detected | TC-05 | 标准 WSL2 kernel 字符串被检测为 WSL2 |
| TestWSL2Detection | test_wsl2_kernel_case_insensitive | TC-05 | 检测大小写不敏感 |
| TestWSL2Detection | test_native_linux_not_detected | TC-05 | 原生 Linux 不被误判为 WSL2 |
| TestWSL2Detection | test_macos_not_detected | TC-05 | 空字符串（macOS 无 /proc/version）不误判 |
| TestGetWslHostIp | test_standard_ip_route_output | TC-06 | 标准 ip route 输出正确提取 gateway IP |
| TestGetWslHostIp | test_empty_ip_route_output | TC-06 | ip route 无输出时返回空字符串，不崩溃 |
| TestGetWslHostIp | test_malformed_ip_route_output | TC-06 | 格式异常时返回空字符串 |
| TestProxyRewrite | test_http_proxy_rewritten | TC-06 | http_proxy 中 127.0.0.1 被替换 |
| TestProxyRewrite | test_https_proxy_rewritten | TC-06 | https_proxy 中 127.0.0.1 被替换 |
| TestProxyRewrite | test_non_localhost_proxy_unchanged | TC-06 | 非 127.0.0.1 的 proxy 不被修改 |
| TestProxyRewrite | test_host_ip_is_127_skipped | TC-06 | WSL_HOST_IP 本身为 127.0.0.1 时跳过重写 |
| TestProxyRewrite | test_empty_proxy_unchanged | TC-06 | 空 proxy 值不报错 |

## 运行结果

```
uv run --no-sync pytest tests/unit/test_wsl2_proxy_rewrite.py -v
12 passed in 0.04s
```

## 未覆盖项（需真实 WSL2 环境）

TC-01~TC-04 为人工验证，见 `plan-wsl2-proxy-005.md` 人工验证记录，全部 PASS。
