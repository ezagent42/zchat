# E2E 测试记录：Quick Start 流程

**日期**：2026-04-08 ~ 2026-04-09
**测试者**：yaosh
**环境**：WSL2 Ubuntu, ergo 2.18.0 (Homebrew), zellij 0.44.1, zchat main 分支
**结果**：通信验证通过（第二轮）

---

## Bug 列表

### Bug 1：ergo languages 目录缺失 [严重]

**分类**：安装 / 首次启动
**影响**：ergo 无法启动，整个系统不可用

**现象**：`irc daemon start` 报错：
```
Config file did not load successfully: Could not load languages: open languages: no such file or directory
```

**原因**：Homebrew 安装的 ergo 只包含二进制，不包含 `languages/` 目录。`daemon_start()` 中只从 `~/.local/share/ergo/languages` 复制，覆盖面不够。

**修复状态**：`fix/language-dir` 分支已实现自动下载（从 GitHub release），未合入 main。

**临时绕过**：
```bash
wget -qO- https://github.com/ergochat/ergo/releases/download/v2.18.0/ergo-2.18.0-linux-x86_64.tar.gz | tar xz -C /tmp
mkdir -p ~/.zchat/projects/<name>/ergo
cp -r /tmp/ergo-2.18.0-linux-x86_64/languages ~/.zchat/projects/<name>/ergo/languages
```

> 注意：每次 `rm -rf` 项目目录重建后都需要重新复制。

---

### Bug 2：start.sh 不创建 Zellij session [严重]

**分类**：启动流程
**影响**：`start.sh` 执行到最后 `zellij attach` 时报 session 不存在

**现象**：
```
Launching Zellij session 'zchat-yaosh-local'...
No session with the name 'zchat-yaosh-local' found!
```

**原因**：`start.sh` 逐步调用 `irc start`、`agent create`，这些命令内部用 `zellij.new_tab()` 创建 tab，但**前提是 session 已存在**。`ensure_session()` 只在 `_create_project_zellij_session()`（由 `project use` 触发）中调用，`start.sh` 没走这个路径。

**修复建议**：在 `start.sh` 中 `irc start` 之前加 `ensure_session()` 调用，或让 `new_tab()` 内部自动 ensure。

**临时绕过**：
```bash
nohup zellij -s zchat-<project> &>/dev/null &
sleep 2
```

---

### Bug 3：`project use` 过早触发启动流程 [中等]

**分类**：启动流程
**影响**：在 ergo/Zellij 未准备好时就尝试启动，导致级联失败

**现象**：执行 `project use yaosh-local` 后自动触发 ergo 启动 + Zellij session 创建，如果 languages 目录缺失或 Zellij session 创建失败，会报错。

**原因**：`project use` 内部调用 `_create_project_zellij_session()`，包含 ergo 启动和 Zellij session 创建。

**临时绕过**：不用 `project use`，所有命令用 `--project <name>` 手动指定。

---

### Bug 4：全局 zchat 与本地源码版本不一致 [中等]

**分类**：开发环境
**影响**：全局 `zchat`（dev122）行为与本地源码不同，容易混淆

**现象**：
- 全局 `zchat` 有旧配置格式检查（`old config format` 报错循环）
- 全局 `zchat` 没有 languages 自动下载修复
- 全局 `zchat` 的 `project create` 交互选项与本地源码不同

**临时绕过**：开发/测试时统一使用本地源码：
```bash
alias zdev="uv run python -m zchat.cli"
zdev --project <name> <command>
```

---

### Bug 5：`agent create --workspace` 未生效（换行导致） [用户操作]

**分类**：CLI 使用
**影响**：workspace 参数丢失，agent 工作目录使用默认路径

**现象**：
```bash
ZCHAT_ZELLIJ_SESSION=zchat-yaosh-local zdev --project yaosh-local agent create agent0
  --workspace ~/workspace
# --workspace 被当成第二条命令：--workspace: command not found
```

**原因**：终端换行导致 shell 将 `--workspace ~/workspace` 当成独立命令。

**正确用法**：必须在一行内写完：
```bash
ZCHAT_ZELLIJ_SESSION=zchat-yaosh-local zdev --project yaosh-local agent create agent0 --workspace ~/workspace
```

---

### Bug 6：`~/workspace` 目录不存在导致 FileNotFoundError [轻微]

**分类**：agent 创建
**影响**：agent 启动失败

**现象**：
```
FileNotFoundError: [Errno 2] No such file or directory: '/home/yaosh/workspace/.zchat-env'
```

**修复建议**：`agent create` 应自动 `mkdir -p workspace`。

**临时绕过**：
```bash
mkdir -p ~/workspace
```

---

### Bug 7：Zellij 快捷键 Alt+1/2/3 无效 [轻微]

**分类**：Zellij 集成
**影响**：无法用预期快捷键切换 tab

**现象**：在 WSL2 终端中 Alt+数字键无响应。

**原因**：可能是 WSL2 / Windows Terminal 的 Alt 键绑定冲突。

**临时绕过**：`Ctrl+t` 进入 tab 模式，然后按数字键切换。或鼠标点击 tab 栏。

---

### Bug 8：Zellij session 残留（EXITED 状态） [轻微]

**分类**：清理
**影响**：重新创建 session 时冲突

**现象**：`project use` 或 `start.sh` 创建的 session 异常退出后变为 EXITED 状态，`delete-session` 需要 `--force` 参数。

**临时绕过**：
```bash
zellij delete-session <name> --force
```

---

### Bug 9：ergo languages 手动复制路径陷阱 [轻微]

**分类**：手动绕过操作
**影响**：ergo 仍然启动失败，languages 文件散落在 ergo/ 根目录

**现象**：按指南执行 `cp -r /tmp/.../languages ~/.zchat/projects/yaosh-local/ergo/`，如果 `ergo/` 目录已存在且内含 `ergo.yaml`，`cp -r` 会将 languages 内容**展开**到 `ergo/` 下，而不是创建 `ergo/languages/` 子目录。ergo 期望路径 `languages/` 相对于 `ergo.yaml` 所在目录。

**原因**：`cp -r src dst/` 的行为取决于 `dst/src_basename` 是否已存在。`daemon_start()` 先生成 `ergo/ergo.yaml`，之后 `cp -r .../languages ergo/` 发现 `ergo/languages` 不存在时创建子目录（正确），但如果 `ergo/` 目录被删重建后时序不同就可能出错。

**正确操作**：显式指定目标为子目录名：
```bash
cp -r /tmp/ergo-2.18.0-linux-x86_64/languages ~/.zchat/projects/yaosh-local/ergo/languageslanguages
```

**修复步骤**（如果已错误复制）：
```bash
rm -f ~/.zchat/projects/yaosh-local/ergo/*.lang.* ~/.zchat/projects/yaosh-local/ergo/README.md
cp -r /tmp/ergo-2.18.0-linux-x86_64/languages ~/.zchat/projects/yaosh-local/ergo/languageslanguages
```

---

## 首次通信失败分析（第一轮测试 04-08）

### 现象

WeeChat #general 中 @mention agent0，agent0 在 Claude Code tab 中处理了请求，但回复**没有出现在 IRC 频道**。WeeChat 显示只有 1 个用户在线（agent 未 JOIN）。

### 诊断

1. channel-server 进程在跑（pid 可见）
2. `.mcp.json` 和 `.claude/settings.local.json` 正确生成
3. `SessionStart:startup hook error` — `.ready` 文件未创建
4. `.mcp.json` 中注入了 `HTTP_PROXY` 和 `HTTPS_PROXY`

### 可能原因

1. **HTTP_PROXY 干扰本地 IRC 连接**：channel-server 环境变量中有 `HTTP_PROXY=http://172.30.240.1:7897`，Python 的 `irc` 库或底层 socket 可能尝试通过代理连接 `127.0.0.1:6667`
2. **SessionStart hook 错误**：原因未确定，可能与 Claude Code 版本或 hook 格式有关

### 第二轮测试（04-09）结果

完全清理后重新按步骤执行，**通信正常**。说明第一轮失败可能是：
- 残留状态干扰（旧 session / 旧进程）
- 或 `Ctrl+c` 打断 `agent create` 时 channel-server 未完成初始化

---

## 验证通过的完整流程

```bash
alias zdev="uv run python -m zchat.cli"

# 1. 同步依赖
uv sync

# 2. 创建项目
zdev project create yaosh-local  # 选 Local

# 3. 准备 ergo languages
mkdir -p ~/.zchat/projects/yaosh-local/ergo
cp -r /tmp/ergo-2.18.0-linux-x86_64/languages ~/.zchat/projects/yaosh-local/ergo/languages

# 4. 启动 ergo
zdev --project yaosh-local irc daemon start

# 5. 创建 Zellij session
zellij delete-session zchat-yaosh-local --force 2>/dev/null
nohup zellij -s zchat-yaosh-local &>/dev/null &
sleep 2 && zellij list-sessions

# 6. 启动 WeeChat
ZCHAT_ZELLIJ_SESSION=zchat-yaosh-local zdev --project yaosh-local irc start

# 7. 创建 Agent（等 30-60 秒）
ZCHAT_ZELLIJ_SESSION=zchat-yaosh-local zdev --project yaosh-local agent create agent0 --workspace ~/workspace

# 8. 进入 Zellij
zellij attach zchat-yaosh-local
# Tab 切换：Ctrl+t + 数字键
# 在 WeeChat #general 中：@yaosh-agent0 你好
```

---

## 测试进度

- [x] Step 1: uv sync
- [x] Step 2: project create
- [x] Step 3: ergo languages（手动下载）
- [x] Step 4: irc daemon start
- [x] Step 5: Zellij session（nohup）
- [x] Step 6: irc start
- [x] Step 7: agent create
- [x] Step 8: zellij attach
- [x] Step 9: 通信测试 — **通过**（第二轮 04-09）
