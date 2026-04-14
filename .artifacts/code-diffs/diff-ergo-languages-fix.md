---
type: code-diff
id: code-diff-004
status: merged
producer: manual
created_at: "2026-04-13T14:35:00Z"
commits:
  - f57eb46
  - b30ebd5
related:
  - eval-doc: eval-ergo-languages-004
  - issue: https://github.com/ezagent42/zchat/issues/41
---

# Code Diff: ergo languages 目录多路径查找（fix #41）

## 提交信息

```
commit f57eb46
fix: ergo languages dir multi-path search (fixes #41)

Search ~/.local/share/ergo, brew --prefix ergo share, and next to
ergo binary — so Homebrew installs work without manual workaround.

commit b30ebd5
fix: tests and app.py cleanup for issue #41 follow-up

- Fix os import in test_irc_manager_languages.py (TC-01/02/08)
- Fix os.path.realpath mock signature (**kw) for Python 3.13 compat
- Cherry-pick app.py --no-attach option so test_project_use_command passes
```

## 变更文件

- `zchat/cli/irc_manager.py` — languages copy 逻辑重写（单路径 → 多路径查找）
- `zchat/cli/app.py` — `--no-attach` 选项补充（b30ebd5）
- `tests/unit/test_irc_manager_languages.py` — 新增（f57eb46 创建，b30ebd5 修复）

## 核心 Diff（irc_manager.py）

```diff
-        # Copy languages from system ergo install if needed
-        system_ergo = os.path.expanduser("~/.local/share/ergo")
-        if os.path.isdir(os.path.join(system_ergo, "languages")) and \
-           not os.path.isdir(os.path.join(ergo_data_dir, "languages")):
-            import shutil
-            shutil.copytree(os.path.join(system_ergo, "languages"),
-                            os.path.join(ergo_data_dir, "languages"))
+        # Copy languages from system ergo install if needed.
+        # Search multiple locations: ~/.local/share/ergo (manual install),
+        # brew --prefix ergo share (Homebrew), and next to the ergo binary.
+        if not os.path.isdir(os.path.join(ergo_data_dir, "languages")):
+            import shutil
+            lang_candidates = [
+                os.path.expanduser("~/.local/share/ergo/languages"),
+            ]
+            try:
+                brew_result = subprocess.run(
+                    ["brew", "--prefix", "ergo"],
+                    capture_output=True, text=True, timeout=5,
+                )
+                if brew_result.returncode == 0:
+                    brew_prefix = brew_result.stdout.strip()
+                    lang_candidates.append(os.path.join(brew_prefix, "share", "languages"))
+                    lang_candidates.append(os.path.join(brew_prefix, "languages"))
+            except (FileNotFoundError, subprocess.TimeoutExpired):
+                pass
+            ergo_bin = shutil.which("ergo")
+            if ergo_bin:
+                lang_candidates.append(os.path.join(os.path.dirname(ergo_bin), "..", "share", "ergo", "languages"))
+                lang_candidates.append(os.path.join(os.path.dirname(ergo_bin), "languages"))
+            for candidate in lang_candidates:
+                candidate = os.path.realpath(candidate)
+                if os.path.isdir(candidate):
+                    shutil.copytree(candidate, os.path.join(ergo_data_dir, "languages"))
+                    break
```

## 影响模块

- `zchat/cli/irc_manager.py` — `daemon_start()` 中的 languages copy 逻辑（多路径查找）
- `zchat/cli/app.py` — `--no-attach` 选项
