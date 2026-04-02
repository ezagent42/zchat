# Better Distribution: curl | bash + Auto-Update

## Problem

当前分发依赖 PyPI + Homebrew formula 手动更新，安装耗时长、分发速度慢。用户需要多步操作（brew tap → brew install → 手动装 ergo/weechat/tmux）。

## Goals

1. 一条命令完成安装：`curl -fsSL <url> | bash`
2. 自动更新机制，不依赖 Homebrew 升级
3. 支持 macOS + Linux
4. 支持 main / dev / release 三个版本通道

## Non-Goals

- 预编译二进制分发（PyInstaller/Nuitka）
- Windows 支持
- 移除 Homebrew formula（保留但不再作为主推通道）

---

## Architecture

### 安装脚本 (`install.sh`)

入口命令：

```bash
curl -fsSL https://raw.githubusercontent.com/ezagent42/zchat/main/install.sh | bash
# 指定通道：
curl ... | bash -s -- --channel release
```

执行流程：

1. 检测 OS (macOS / Linux)
2. 安装 Homebrew（如果没有）— Linux 上先检查 tmux/weechat 是否已通过系统包管理器安装，仅在缺失时才安装 Homebrew
3. `brew install tmux weechat ezagent42/zchat/ergo`（跳过已安装的）
4. 安装 uv（如果没有）— `curl -LsSf https://astral.sh/uv/install.sh | sh`
5. `uv python install 3.11`（如果系统无 3.11+）
6. `uv tool install "zchat @ git+https://github.com/ezagent42/zchat.git@main"`
7. `uv tool install "zchat-channel-server @ git+https://github.com/ezagent42/claude-zchat-channel.git@main"`
8. `uv tool install tmuxp`
9. 检测 claude CLI — 未安装则打印安装指引
10. `zchat doctor` 验证
11. 打印成功信息 + 快速开始指引

zchat 和 zchat-channel-server 各自独立 `uv tool install`（方案 A），隔离干净、升级独立。

安装源根据 `--channel` 参数：

| 通道 | zchat 安装源 | zchat-channel-server 安装源 |
|------|-------------|---------------------------|
| `main`（默认） | `git+https://github.com/ezagent42/zchat.git@main` | `git+https://github.com/ezagent42/claude-zchat-channel.git@main` |
| `dev` | `...@dev` | `...@dev` |
| `release` | `zchat` (PyPI latest) | `zchat-channel-server` (PyPI latest) |

### 自动更新机制

#### 命令

| 命令 | 行为 |
|------|------|
| `zchat update` | 检查远程版本，更新 `update.json`，打印是否有新版本可用。不下载。 |
| `zchat upgrade` | 先 update，再下载安装。已是最新则提示无需升级。 |
| `zchat upgrade --channel dev` | 临时用指定通道升级。 |

移除现有 `zchat self-update` 命令。

#### 自动检查流程

任何 `zchat` 命令启动时，后台 fork 检查更新：

```
zchat <any command>
│
├─ 前台：正常执行用户命令
└─ 后台 fork：
      ├─ 读取 ~/.zchat/update.json
      ├─ 今天已检查过？→ 跳过（每天第一次执行时检查）
      ├─ 根据 channel 检查远程版本（5 秒超时）
      │   ├─ main/dev → git ls-remote 获取最新 commit hash
      │   └─ release → PyPI JSON API
      ├─ 网络失败？→ 静默跳过，保留 update.json 现有状态
      ├─ 本地 == 远程？→ 跳过
      └─ 有更新：
          ├─ auto_upgrade = true（默认）→ 直接执行 uv tool upgrade，下次启动生效
          └─ auto_upgrade = false → 仅写入 update.json，下次启动打印提示
```

当 `auto_upgrade = false` 时，用户下次执行任何 `zchat` 命令时，如果 `update_available: true`，在输出末尾打印一行提示：

```
💡 New version available. Run `zchat upgrade` to update.
```

当 `auto_upgrade = true`（默认）时，后台自动执行升级。`zchat upgrade` 始终同时升级 zchat 和 zchat-channel-server，视为原子操作 — 任一失败则回滚（重新安装旧版本）。

#### 版本通道检查方式

| 通道 | 版本检查 | 版本标识 |
|------|---------|---------|
| `main` | `git ls-remote ... refs/heads/main` | commit hash 前 7 位 |
| `dev` | `git ls-remote ... refs/heads/dev` | commit hash 前 7 位 |
| `release` | `GET https://pypi.org/pypi/zchat/json` | 语义版本号 |

#### 配置

全局配置 `~/.zchat/config.toml`：

```toml
[update]
channel = "main"          # main | dev | release
auto_upgrade = true       # true: 后台自动升级; false: 仅检查+提示
```

切换通道：

```bash
zchat config set update.channel release
```

`zchat config` 是新增的全局配置子命令组，操作 `~/.zchat/config.toml`（区别于现有的 per-project config）。支持 `get` / `set` / `list`。

切换后下次 `zchat upgrade` 从新通道重新安装（`uv tool install --force`）。切换通道会清空 `update.json` 中的版本引用。

#### 状态文件 (`~/.zchat/update.json`)

分别跟踪两个包的版本，确保状态一致：

```json
{
  "last_check": "2026-04-02T00:00:00Z",
  "channel": "main",
  "zchat": {
    "installed_ref": "abc1234",
    "remote_ref": "def5678"
  },
  "channel_server": {
    "installed_ref": "111aaaa",
    "remote_ref": "222bbbb"
  },
  "update_available": true
}
```

通道切换时（`zchat config set update.channel release`），清空 `installed_ref` 和 `remote_ref`，下次 `zchat upgrade` 强制重新安装。

### start.sh 环境修复

**问题：** `start.sh:10` 用裸 `python3` 调用 `importlib.metadata` 查找 zchat-channel-server 包路径，uv tool venv 下系统 python3 找不到该包。

**修复：** zchat CLI 在 `zchat agent create` 时通过 `uv tool dir` 定位 zchat-channel-server 的 venv，然后在其 site-packages 中查找包路径，写入 agent `.env`：

```python
# agent_manager.py
import subprocess, glob

def _find_channel_pkg_dir() -> str | None:
    """Locate zchat-channel-server package dir in its uv tool venv."""
    result = subprocess.run(
        ["uv", "tool", "dir"], capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    tool_dir = result.stdout.strip()
    # uv tool venvs: <tool_dir>/zchat-channel-server/...
    patterns = glob.glob(
        f"{tool_dir}/zchat-channel-server/lib/python*/site-packages/zchat_channel_server"
    )
    return patterns[0] if patterns else None
```

注意：`importlib.metadata` 无法跨 venv 查找，因为 zchat 和 zchat-channel-server 在独立的 uv tool venv 中。必须通过 `uv tool dir` 找到 venv 路径后在文件系统层面定位。

`start.sh` 改为直接读环境变量：

```bash
# 旧: python3 -c "from importlib.metadata import files ..."
# 新:
if [ -n "$CHANNEL_PKG_DIR" ] && [ -d "$CHANNEL_PKG_DIR/.claude-plugin" ]; then
  cp -r "$CHANNEL_PKG_DIR/.claude-plugin" .claude-plugin
  cp -r "$CHANNEL_PKG_DIR/commands" commands
fi
```

### doctor 增强

在现有检查项基础上增加：

| 检查项 | 方式 | 未安装提示 |
|--------|------|-----------|
| uv | `shutil.which("uv")` + 版本 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Python 3.11+ | `python3 --version` | `uv python install 3.11` |
| tmuxp | `shutil.which("tmuxp")` + 版本 | `uv tool install tmuxp` |
| 更新状态 | 读 `update.json` | `zchat upgrade` |

每个未通过项输出安装提示：

```
✗ tmux not found
  → brew install tmux
✓ uv 0.6.x
✓ Python 3.11.x
```

---

## Files Changed

| 文件 | 变更 |
|------|------|
| `install.sh`（新建） | 安装脚本 |
| `zchat/cli/app.py` | 移除 `self-update`，添加 `update` / `upgrade` / `config` 命令，启动时后台检查 |
| `zchat/cli/update.py`（新建） | 更新检查 + 升级逻辑 |
| `zchat/cli/config.py`（新建） | 全局配置子命令组（get/set/list），操作 `~/.zchat/config.toml` |
| `zchat/cli/agent_manager.py` | agent create 时通过 `uv tool dir` 定位 channel-server 包路径，写入 `CHANNEL_PKG_DIR` |
| `zchat/cli/templates/claude/start.sh` | 用 `$CHANNEL_PKG_DIR` 替代 python3 查找 |
| `zchat/cli/doctor.py` | 增加 uv / Python / tmuxp / 更新状态检查 |
| `tests/unit/test_update.py`（新建） | update/upgrade 逻辑单元测试 |
| `tests/pre_release/test_07_self_update.py` | 重命名/改为测试 upgrade |

### 关于 zchat-protocol

`zchat-protocol` 是 zchat 和 zchat-channel-server 的 Python 依赖（声明在各自的 `pyproject.toml` 中）。`uv tool install` 时通过依赖解析自动安装到各自的 venv，无需单独的 `uv tool install` 步骤。现有 `self-update` 中单独更新 protocol 的逻辑不再需要。
