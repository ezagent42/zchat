---
type: code-diff
id: code-diff-005
status: merged
producer: manual
created_at: "2026-04-13T14:35:00Z"
commit: f57eb46
related:
  - eval-doc: eval-weechat-cache-006
  - issue: https://github.com/ezagent42/zchat/issues/42
---

# Code Diff: WeeChat server cache 强制更新（fix #42）

## 提交信息

```
commit f57eb46
fix: ergo languages dir multi-path search (fixes #41)

（同一 commit 中包含 #42 的 WeeChat /set cache 修复）
修复位置：zchat/cli/irc_manager.py _build_weechat_cmd()
```

## 核心 Diff（irc_manager.py:266-276）

```diff
+        # Use /server add for first time, then /set addresses + tls to ensure
+        # config is up-to-date even if WeeChat cached an old server address
+        # (fixes issue where switching IRC servers left WeeChat connecting to
+        # the old one because /server add silently ignores duplicates).
+        tls_on_off = "on" if tls else "off"
         return (
             f"{source_env}weechat -d {weechat_home} -r '"
             f"/server add {srv_name} {server}/{port}{tls_flag} -nicks={nick}"
+            f"; /set irc.server.{srv_name}.addresses \"{server}/{port}\""
+            f"; /set irc.server.{srv_name}.ssl {tls_on_off}"
+            f"; /set irc.server.{srv_name}.nicks \"{nick}\""
             f"; /set irc.server.{srv_name}.autojoin \"{autojoin}\""
```

## 影响模块

- `zchat/cli/irc_manager.py:266-276` — `_build_weechat_cmd()` 追加 `/set` 覆盖缓存
