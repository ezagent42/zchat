---
type: test-plan
id: test-plan-005
status: executed
producer: skill-2
created_at: "2026-04-13T00:00:00Z"
related:
  - eval-doc: eval-wsl2-proxy-003
  - issue: https://github.com/ezagent42/zchat/issues/40
---

# Test Plan: claude.sh WSL2 proxy 自动重写（fix #40）

## 来源
- eval-doc: `eval-wsl2-proxy-003`
- 修复代码位置: `claude.sh:78-89`

## 测试范围

`claude.sh` 中 WSL2 proxy 重写逻辑：

```bash
if grep -qi microsoft /proc/version 2>/dev/null; then
    WSL_HOST_IP=$(ip route show default 2>/dev/null | awk '{print $3; exit}')
    if [ -n "$WSL_HOST_IP" ] && [ "$WSL_HOST_IP" != "127.0.0.1" ]; then
        [ -n "$http_proxy" ]  && export http_proxy="${http_proxy//127.0.0.1/$WSL_HOST_IP}"
        ...
    fi
fi
```

## 测试策略说明

`claude.sh` 是纯 bash 脚本，自动化测试需要 [bats-core](https://github.com/bats-core/bats-core)。
项目目前未引入 bats，且核心逻辑（WSL2 检测、`ip route`）需要真实 WSL2 环境才能端到端验证。

**推荐策略**：
- TC-01 ~ TC-04：**人工验证**（需 WSL2 环境），记录结果到本文档
- TC-05 ~ TC-06：可提取为独立 bash 函数后用 bats 自动化（待后续引入 bats）

## Test Cases

| TC-ID | 场景 | 测试类型 | 优先级 | 前置条件 | 操作 | 断言 |
|-------|------|---------|-------|---------|------|------|
| TC-01 | WSL2 下 127.0.0.1 代理被自动重写 | 人工/WSL2 | P0 | WSL2 环境；`claude.local.env` 设 `http_proxy=http://127.0.0.1:7890`；Clash 在 Windows 侧运行 | 执行 `./claude.sh`，观察是否成功连接 Claude API | 无 `ECONNREFUSED`，Claude 正常启动 |
| TC-02 | 重写后 proxy 地址为 Windows host IP | 人工/WSL2 | P0 | 同上 | 在 `claude.sh` 中 `echo $http_proxy` 输出重写后的值 | 地址为 `172.x.x.x:7890`，非 `127.0.0.1` |
| TC-03 | 非 WSL2 环境下 proxy 不被修改 | 人工/Linux | P1 | 原生 Linux 或 macOS；`/proc/version` 不含 `microsoft` | 执行 `./claude.sh`，检查 proxy 变量 | proxy 值与 `claude.local.env` 原始值相同 |
| TC-04 | WSL2 下未设置 proxy 时正常启动 | 人工/WSL2 | P1 | WSL2 环境；`claude.local.env` 中无 proxy 设置 | 执行 `./claude.sh` | 正常启动，无报错 |
| TC-05 | `/proc/version` 含 `microsoft` 时检测为 WSL2 | bash 单元 | P1 | mock `/proc/version` 内容 | 运行检测逻辑 | `grep -qi microsoft` 返回 0 |
| TC-06 | `ip route` 无输出时不重写（降级安全） | bash 单元 | P1 | mock `ip route` 返回空 | 运行重写逻辑 | proxy 变量不变，不报错 |

## 人工验证记录

| TC-ID | 验证时间 | 验证人 | 结果 | 备注 |
|-------|---------|-------|------|------|
| TC-01 | 2026-04-13 | zyli | PASS | WSL2 (kernel 6.6.87.2-microsoft-standard-WSL2)，http_proxy 重写成功，无 127.0.0.1 |
| TC-02 | 2026-04-13 | zyli | PASS | 重写后地址为 198.18.0.2:7890（Windows host IP） |
| TC-03 | 2026-04-13 | zyli | SKIP | 需要原生 Linux/macOS 机器；当前环境仅有 Windows + WSL2，无法真实验证 |
| TC-04 | 2026-04-13 | zyli | PASS | 无 proxy 变量时静默跳过，无报错 |

## 自动化路径（后续）

引入 bats-core 后，TC-05/TC-06 可实现为：

```bash
# tests/bash/test_claude_sh_wsl2.bats
@test "WSL2 proxy rewrite replaces 127.0.0.1" {
  source scripts/wsl2_proxy_rewrite.sh  # 需提取为独立函数
  export http_proxy="http://127.0.0.1:7890"
  WSL_HOST_IP="172.30.240.1"
  rewrite_proxy
  [ "$http_proxy" = "http://172.30.240.1:7890" ]
}
```
