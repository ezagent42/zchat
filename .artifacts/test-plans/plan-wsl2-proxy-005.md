---
type: test-plan
id: test-plan-005
status: executed
producer: skill-2
created_at: "2026-04-13T00:00:00Z"
updated_at: "2026-04-13T15:10:00Z"
related:
  - eval-doc: eval-wsl2-proxy-003
  - code-diff: code-diff-003
  - test-diff: test-diff-002
  - issue: https://github.com/ezagent42/zchat/issues/40
---

# Test Plan: claude.sh WSL2 proxy 自动重写（fix #40）

## 来源
- eval-doc: `eval-wsl2-proxy-003`
- code-diff: `code-diff-003`（commit `6a17dec`）
- 修复代码位置: `claude.sh:78-89`

## 测试范围

`claude.sh` 中 WSL2 proxy 重写逻辑：

```bash
if grep -qi microsoft /proc/version 2>/dev/null; then
    WSL_HOST_IP=$(ip route show default 2>/dev/null | awk '{print $3; exit}')
    if [ -n "$WSL_HOST_IP" ] && [ "$WSL_HOST_IP" != "127.0.0.1" ]; then
        [ -n "$http_proxy" ]  && export http_proxy="${http_proxy//127.0.0.1/$WSL_HOST_IP}"
        [ -n "$https_proxy" ] && export https_proxy="${https_proxy//127.0.0.1/$WSL_HOST_IP}"
        [ -n "$HTTP_PROXY" ]  && export HTTP_PROXY="${HTTP_PROXY//127.0.0.1/$WSL_HOST_IP}"
        [ -n "$HTTPS_PROXY" ] && export HTTPS_PROXY="${HTTPS_PROXY//127.0.0.1/$WSL_HOST_IP}"
    fi
fi
```

## 测试策略说明

`claude.sh` 是纯 bash 脚本，TC-01~TC-04 需要真实 WSL2 环境，采用人工验证。
TC-05~TC-06 的等效逻辑已提取为 Python 函数，在 `tests/unit/test_wsl2_proxy_rewrite.py` 中自动化测试。

## Test Cases

| TC-ID | 场景 | 测试类型 | 优先级 | 前置条件 | 操作 | 断言 |
|-------|------|---------|-------|---------|------|------|
| TC-01 | WSL2 下 127.0.0.1 代理被自动重写 | 人工/WSL2 | P0 | WSL2 环境；`claude.local.env` 设 `http_proxy=http://127.0.0.1:7890` | 执行 `./claude.sh`，观察是否成功连接 Claude API | 无 `ECONNREFUSED`，Claude 正常启动 |
| TC-02 | 重写后 proxy 地址为 Windows host IP | 人工/WSL2 | P0 | 同上 | 在 `claude.sh` 中 `echo $http_proxy` 输出重写后的值 | 地址为 `198.18.0.2:7890`，非 `127.0.0.1` |
| TC-03 | 非 WSL2 环境下 proxy 不被修改 | 人工/mock | P1 | mock `/proc/version` 不含 `microsoft` | 执行检测逻辑 | proxy 值与原始值相同 |
| TC-04 | WSL2 下未设置 proxy 时正常启动 | 人工/WSL2 | P1 | WSL2 环境；`claude.local.env` 中无 proxy 设置 | 执行 `./claude.sh` | 正常启动，无报错 |
| TC-05 | `/proc/version` 含 `microsoft` 时检测为 WSL2 | 单元测试 | P1 | — | `test_wsl2_kernel_detected` 等 4 个测试 | 全部 PASS |
| TC-06 | `ip route` 解析和 proxy 重写逻辑正确 | 单元测试 | P1 | — | `TestGetWslHostIp` + `TestProxyRewrite` 等 8 个测试 | 全部 PASS |

## 人工验证记录

| TC-ID | 验证时间 | 验证人 | 结果 | 备注 |
|-------|---------|-------|------|------|
| TC-01 | 2026-04-13 | zyli | PASS | WSL2 (kernel 6.6.87.2-microsoft-standard-WSL2)，http_proxy 重写成功，无 127.0.0.1 |
| TC-02 | 2026-04-13 | zyli | PASS | 重写后地址为 198.18.0.2:7890（Windows host IP via ip route） |
| TC-03 | 2026-04-13 | zyli | PASS | mock 原生 Linux /proc/version，proxy 值未被修改 |
| TC-04 | 2026-04-13 | zyli | PASS | 无 proxy 变量时静默跳过，无报错 |

## 自动化覆盖

TC-05/TC-06 通过 Python 等效逻辑实现自动化，见 `tests/unit/test_wsl2_proxy_rewrite.py`（test-diff-002）。
