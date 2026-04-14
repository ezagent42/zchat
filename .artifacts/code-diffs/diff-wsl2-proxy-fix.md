---
type: code-diff
id: code-diff-003
status: merged
producer: manual
created_at: "2026-04-13T14:27:00Z"
commit: 6a17dec
related:
  - eval-doc: eval-wsl2-proxy-003
  - issue: https://github.com/ezagent42/zchat/issues/40
---

# Code Diff: WSL2 proxy 自动重写（fix #40）

## 提交信息

```
commit 6a17dec
fix: WSL2 proxy auto-rewrite in claude.sh (fixes #40)

In WSL2, 127.0.0.1 refers to WSL's own loopback, not the Windows host.
Auto-detect WSL2 via /proc/version and rewrite proxy env vars to use
the Windows host IP from `ip route show default`.

Also add claude.local.env.example with WSL2 proxy config notes.
```

## 变更文件

- `claude.sh` +14 行
- `claude.local.env.example` +2 行（文档更新）

## Diff

```diff
--- a/claude.sh
+++ b/claude.sh
@@ -75,6 +75,20 @@ else
     fi
 fi
 
+# WSL2: rewrite 127.0.0.1 proxy to Windows host IP
+# In WSL2, 127.0.0.1 is WSL's own loopback, not the Windows host.
+# The proxy (Clash/v2ray) runs on Windows, so we need the host IP.
+# Use default gateway (ip route) — resolv.conf may point to custom DNS, not the host.
+if grep -qi microsoft /proc/version 2>/dev/null; then
+    WSL_HOST_IP=$(ip route show default 2>/dev/null | awk '{print $3; exit}')
+    if [ -n "$WSL_HOST_IP" ] && [ "$WSL_HOST_IP" != "127.0.0.1" ]; then
+        [ -n "$http_proxy" ]  && export http_proxy="${http_proxy//127.0.0.1/$WSL_HOST_IP}"
+        [ -n "$https_proxy" ] && export https_proxy="${https_proxy//127.0.0.1/$WSL_HOST_IP}"
+        [ -n "$HTTP_PROXY" ]  && export HTTP_PROXY="${HTTP_PROXY//127.0.0.1/$WSL_HOST_IP}"
+        [ -n "$HTTPS_PROXY" ] && export HTTPS_PROXY="${HTTPS_PROXY//127.0.0.1/$WSL_HOST_IP}"
+    fi
+fi
+
 # Source MCP server secrets (API keys, tokens)
 [ -f "$SCRIPT_DIR/.mcp.env" ] && set -a && source "$SCRIPT_DIR/.mcp.env" && set +a
```

```diff
--- a/claude.local.env.example
+++ b/claude.local.env.example
@@ -4,3 +4,5 @@
 # Proxy (required if behind a proxy)
+# Use 127.0.0.1 here — claude.sh auto-rewrites it to the Windows host IP in WSL2.
+# Make sure the proxy allows LAN connections (Clash: "Allow LAN", v2rayN: "允许局域网连接").
 http_proxy=http://127.0.0.1:7890
 https_proxy=http://127.0.0.1:7890
```

## 影响模块

- `claude.sh:78-90` — WSL2 检测 + proxy 重写逻辑（新增）
- `claude.local.env.example` — 用户配置说明（文档补充）
