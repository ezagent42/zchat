# 发布流程

## 版本号规则

版本号由 `hatch-vcs` 从 git tag 自动派生：

| 场景 | 版本号 | 示例 |
|------|--------|------|
| 打 tag 的 commit | `X.Y.Z` | `0.3.0` |
| tag 之后的 N 个 commit | `X.Y.(Z+1).devN` | `0.3.1.dev21` |
| 下一个 release | 打新 tag `vX.Y.Z` | `v0.4.0` |

**原则：除非明确说明要 release，只推 dev 版本。不手动改版本号。**

## PR 合并后更新 PyPI + Homebrew

### 1. PyPI — 自动发布

每次 push 到 main，CI 自动 build + publish dev 版本到 PyPI。**无需手动操作。**

等 CI 完成（约 1-2 分钟）：
```bash
gh run list -L 1  # 确认 ✅
```

查看发布的版本号：
```bash
uv build 2>&1 | grep "Successfully built"
# → Successfully built dist/zchat-0.3.1.dev21.tar.gz
```

### 2. Homebrew formula — CI 自动更新

PyPI 发布成功后，`publish.yml` 中的 `update-homebrew` job 会自动：
1. 等待 PyPI 索引新版本
2. 获取 sdist URL 和 sha256
3. 更新 `homebrew-zchat/Formula/zchat.rb`
4. Commit 并 push

**无需手动操作。** 如需手动触发，可 re-run workflow。

前置条件：`ezagent42/zchat` repo 中需要 `HOMEBREW_PAT` secret（Fine-grained PAT，对 `homebrew-zchat` 有 Contents read/write 权限）。

### 3. 用户更新

```bash
brew update && brew upgrade zchat
zchat --version  # 确认新版本
```

## 正式 Release（需要明确说明时）

```bash
# 1. 确保 main 干净
git checkout main && git pull

# 2. 打 release tag（这会让 hatch-vcs 生成干净的版本号）
git tag v0.4.0
git push origin v0.4.0

# 3. CI 自动发布到 PyPI (版本号: 0.4.0)
# 4. 更新 Homebrew formula（同上步骤 2）
```

## 子模块发布

`zchat-protocol` 和 `zchat-channel-server` 有独立的 PyPI 包和版本号。
只在它们的代码有改动时才需要发布新版：

```bash
cd zchat-channel-server  # 或 zchat-protocol
# 修改 pyproject.toml 中的 version
git add pyproject.toml && git commit -m "bump version to X.Y.Z"
git tag vX.Y.Z && git push && git push origin vX.Y.Z
# CI 自动发布
```

然后更新 zchat 主包的 `pyproject.toml` 中对应的 `>=X.Y.Z` 依赖版本。

## 注意事项

- **不要手动改 `zchat/_version.py`** — 它由 hatch-vcs 在 build 时自动生成
- **不要打 `.devN` 格式的 tag**（如 `v0.3.1.dev21`）— hatch-vcs 不支持，会导致 build 报错
- **tag 只用 `vX.Y.Z` 格式** — 用于正式 release
- dev 版本号由 hatch-vcs 自动计算（基于最近的 `vX.Y.Z` tag + commit 距离）
- `local_scheme = "no-local-version"` 确保版本号不含 `+gHASH`（PyPI 不接受）
- 不要在 `[tool.hatch.build]` 中用 `force-include` 重复包含 `packages` 已覆盖的目录（会导致 PyPI 400）
