---
type: eval-doc
id: eval-wsl2-proxy-003
status: confirmed
producer: skill-5
created_at: "2026-04-13T00:00:00Z"
mode: verify
feature: claude.sh WSL2 proxy 自动重写
submitter: zyli
related:
  - issue: https://github.com/ezagent42/zchat/issues/40
---

# Eval: claude.sh WSL2 代理地址 127.0.0.1 导致 ECONNREFUSED

## 基本信息
- 模式：验证
- 提交人：zyli
- 日期：2026-04-13
- 状态：confirmed（已确认为 bug，fix 已合并）

## Testcase 表格

| # | 场景 | 前置条件 | 操作步骤 | 预期效果 | 实际效果 | 差异描述 | 优先级 |
|---|------|---------|---------|---------|---------|---------|--------|
| 1 | WSL2 下使用 127.0.0.1 代理启动 claude.sh | WSL2 环境；`claude.local.env` 中设置 `http_proxy=http://127.0.0.1:7890`；代理软件（Clash）运行在 Windows 侧 | 执行 `./claude.sh` | Claude 正常启动，通过 Windows 侧代理连接 API | `ECONNREFUSED` 报错，Claude 无法连接 API | WSL2 中 `127.0.0.1` 指向 WSL 自身 loopback，而非 Windows host；代理端口未在 WSL 内监听 | P0 |
| 2 | WSL2 自动检测并重写代理 IP | 同上 | `claude.sh` 运行时自动从 `ip route` 获取 Windows host IP，替换 `127.0.0.1` | 代理变量被重写为正确的 host IP，Claude 正常连接 | fix 已引入（commit `6a17dec`）：`claude.sh:78-89` 检测 `/proc/version` 含 `microsoft` 后自动重写 proxy 变量 | 无差异，fix 已验证逻辑正确 | P0 |
| 3 | 非 WSL2 环境不受影响 | Linux 原生或 macOS 环境；`/proc/version` 中不含 `microsoft` | 执行 `./claude.sh` | 代理变量不被修改，行为与修复前完全一致 | fix 通过 `grep -qi microsoft /proc/version` 判断环境，非 WSL2 不执行重写 | 无差异 | P1 |
| 4 | WSL2 下未设置代理变量 | WSL2 环境；`claude.local.env` 中无 proxy 设置 | 执行 `./claude.sh` | 正常启动，不触发重写逻辑 | fix 中以 `[ -n "$http_proxy" ]` 做判断，空值不处理 | 无差异 | P1 |

## 证据区

### 日志/错误信息（修复前）

```
Error: connect ECONNREFUSED 127.0.0.1:7890
    at TCPConnectWrap.afterConnect [as oncomplete] (node:net:1494:16)
```

### 复现环境

- 操作系统：WSL2 Ubuntu，Kernel `6.6.87.2-microsoft-standard-WSL2`
- 代理软件：Clash（运行在 Windows，监听 `127.0.0.1:7890`）
- 配置：`claude.local.env` 中 `http_proxy=http://127.0.0.1:7890`

## 分流结论

**分类**：确认 bug

**判断理由**：
- `claude.sh` 直接透传 `claude.local.env` 中的代理变量，未处理 WSL2 网络隔离
- WSL2 的网络架构决定了 `127.0.0.1` 必然失败，属于可预测的平台兼容性问题
- 影响中国大陆等需要代理的 WSL2 用户群体，严重性 P0

## 后续行动

- [x] eval-doc 已注册到 registry.json（eval-doc-004）
- [x] 确认为 bug（status: confirmed）
- [x] 修复代码已合并（commit `6a17dec`）
- [x] code-diff 已注册（code-diff-003）
- [x] test-plan 已生成（plan-wsl2-proxy-005，Skill 2）
- [x] 测试代码已编写（test_wsl2_proxy_rewrite.py，Skill 3）
- [x] test-diff 已注册（test-diff-002）
- [x] 测试报告已生成（e2e-report-002，12/12 pass + TC-01~04 人工验证 PASS）
- [x] GitHub issue #40 关联此 eval-doc
