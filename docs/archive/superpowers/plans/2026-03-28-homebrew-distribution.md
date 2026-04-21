# zchat Homebrew Tap Distribution Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable test users to install zchat via `brew install ezagent42/zchat/zchat` on macOS.

**Architecture:** Publish three Python packages to PyPI in dependency order (zchat-protocol → zchat-channel-server → zchat), then create a Homebrew tap with a Python formula using `virtualenv_install_with_resources`. Add `zchat-channel-server` as a runtime dependency of `zchat` so one formula installs both CLI commands (`zchat` and `zchat-channel`). Include a separate formula for ergo (IRC server) since it's not in homebrew-core.

**Tech Stack:** PyPI (hatchling), Homebrew tap (Ruby formula), GitHub Actions (CI/CD)

**Dependency chain (no cycles):**
```
zchat-protocol  (zero deps, pure Python)
    ↑
zchat-channel-server  (+ mcp[cli], irc)
    ↑
zchat  (+ libtmux, typer[all])  ← Homebrew formula target
```

**System dependencies:**
- `tmux` — in homebrew-core ✅
- `ergo` — NOT in homebrew-core, need custom formula in our tap
- `claude` — NOT in Homebrew, user must install separately (documented)
- `weechat` — in homebrew-core ✅ (optional, for IRC client UI)

---

## Chunk 1: PyPI Publishing Preparation

### Task 1: Add package metadata to zchat-protocol

**Files:**
- Modify: `zchat-protocol/pyproject.toml`

- [ ] **Step 1: Add license, authors, URLs to zchat-protocol/pyproject.toml**

```toml
[project]
name = "zchat-protocol"
version = "0.1.0"
description = "Protocol definitions for zchat multi-agent collaboration"
requires-python = ">=3.11"
dependencies = []
license = "MIT"
authors = [{ name = "ezagent42" }]

[project.urls]
Homepage = "https://github.com/ezagent42/zchat-protocol"
Repository = "https://github.com/ezagent42/zchat-protocol"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[dependency-groups]
dev = [
    "pytest>=9.0.2",
]
```

- [ ] **Step 2: Create LICENSE file in zchat-protocol/**

Use MIT license. The file must exist for PyPI upload.

- [ ] **Step 3: Verify build**

Run: `cd zchat-protocol && uv build`
Expected: `dist/zchat_protocol-0.1.0.tar.gz` and `dist/zchat_protocol-0.1.0-py3-none-any.whl` created

- [ ] **Step 4: Commit in zchat-protocol submodule**

```bash
cd zchat-protocol
git add pyproject.toml LICENSE
git commit -m "feat: add PyPI metadata and license for distribution"
```

---

### Task 2: Add package metadata to zchat-channel-server

**Files:**
- Modify: `zchat-channel-server/pyproject.toml`

- [ ] **Step 1: Add license, authors, URLs and update zchat-protocol dependency**

The key change: remove `[tool.uv.sources]` local path override so PyPI builds resolve `zchat-protocol` from PyPI. Keep `[tool.uv.sources]` in a comment or separate `uv.toml` for local dev.

```toml
[project]
name = "zchat-channel-server"
version = "0.2.0"
description = "Claude Code Channel MCP server bridging IRC and Claude Code"
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]>=1.2.0",
    "irc>=20.0",
    "zchat-protocol>=0.1.0",
]
license = "MIT"
authors = [{ name = "ezagent42" }]

[project.urls]
Homepage = "https://github.com/ezagent42/claude-zchat-channel"
Repository = "https://github.com/ezagent42/claude-zchat-channel"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["."]
only-include = ["server.py", "message.py"]

[project.scripts]
zchat-channel = "server:entry_point"

[project.optional-dependencies]
test = [
    "pytest",
    "pytest-asyncio",
    "pytest-order>=1.3.0",
    "pytest-timeout",
]

[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
]
```

- [ ] **Step 2: Create uv.toml for local dev path override**

Create `zchat-channel-server/uv.toml`:
```toml
[sources]
zchat-protocol = { path = "../zchat-protocol", editable = true }
```

This keeps local dev working (`uv sync` reads uv.toml) while PyPI builds ignore it.

- [ ] **Step 3: Create LICENSE file**

- [ ] **Step 4: Verify local dev still works after uv.toml migration**

Run: `cd zchat-channel-server && uv sync && uv run pytest tests/ -v`
Expected: deps resolve correctly, tests pass

- [ ] **Step 5: Verify build**

Run: `cd zchat-channel-server && uv build`
Expected: wheel and sdist created successfully

- [ ] **Step 6: Commit in zchat-channel-server submodule**

```bash
cd zchat-channel-server
git add pyproject.toml uv.toml LICENSE
git commit -m "feat: add PyPI metadata, move uv sources to uv.toml"
```

---

### Task 3: Update zchat (main repo) pyproject.toml

**Files:**
- Modify: `pyproject.toml` (root)

- [ ] **Step 1: Add metadata, add zchat-channel-server as dependency, move uv sources to uv.toml**

```toml
[project]
name = "zchat"
version = "0.1.0"
description = "Multi-agent collaboration over IRC"
requires-python = ">=3.11"
dependencies = [
    "libtmux>=0.55,<0.56",
    "typer[all]>=0.9.0",
    "zchat-protocol>=0.1.0",
    "zchat-channel-server>=0.2.0",
]
license = "MIT"
authors = [{ name = "ezagent42" }]

[project.urls]
Homepage = "https://github.com/ezagent42/zchat"
Repository = "https://github.com/ezagent42/zchat"

[project.scripts]
zchat = "zchat.cli.app:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
    "pytest-order>=1.3.0",
    "pytest-timeout>=2.4.0",
]
```

- [ ] **Step 2: Create uv.toml for local dev path overrides**

Create `uv.toml` (root):
```toml
[sources]
zchat-protocol = { path = "zchat-protocol", editable = true }
zchat-channel-server = { path = "zchat-channel-server", editable = true }
```

- [ ] **Step 3: Create LICENSE file in root**

- [ ] **Step 4: Verify local dev still works**

Run: `uv sync && uv run zchat --help`
Expected: CLI help output, all commands listed

- [ ] **Step 5: Verify build**

Run: `uv build`
Expected: wheel and sdist created (deps listed as PyPI names, not local paths)

- [ ] **Step 6: Run unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.toml LICENSE
git commit -m "feat: add PyPI metadata, add zchat-channel-server dep, move uv sources to uv.toml"
```

---

## Chunk 2: PyPI Publishing & GitHub Actions

### Task 4: Create GitHub Actions workflow for zchat-protocol

**Files:**
- Create: `zchat-protocol/.github/workflows/publish.yml`

- [ ] **Step 1: Write publish workflow triggered by version tags**

```yaml
name: Publish to PyPI
on:
  push:
    tags: ["v*"]

permissions:
  id-token: write  # trusted publishing

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

- [ ] **Step 2: Commit in submodule**

```bash
cd zchat-protocol
git add .github/workflows/publish.yml
git commit -m "ci: add PyPI publish workflow"
```

- [ ] **Step 3: Configure PyPI trusted publisher**

Manual step: On pypi.org, add trusted publisher for `zchat-protocol`:
- Owner: `ezagent42`
- Repository: `zchat-protocol`
- Workflow: `publish.yml`
- Environment: `pypi`

- [ ] **Step 4: Tag and push to trigger first publish**

```bash
cd zchat-protocol
git tag v0.1.0
git push origin main --tags
```

- [ ] **Step 5: Verify package on PyPI**

Run: `pip install zchat-protocol==0.1.0`
Expected: installs successfully from PyPI

---

### Task 5: Create GitHub Actions workflow for zchat-channel-server

**Files:**
- Create: `zchat-channel-server/.github/workflows/publish.yml`

- [ ] **Step 1: Write publish workflow (same pattern as Task 4)**

Same YAML as Task 4 Step 1.

- [ ] **Step 2: Commit, configure trusted publisher, tag and push**

```bash
cd zchat-channel-server
git add .github/workflows/publish.yml
git commit -m "ci: add PyPI publish workflow"
git tag v0.2.0
git push origin main --tags
```

- [ ] **Step 3: Verify**

Run: `pip install zchat-channel-server==0.2.0`
Expected: installs successfully, `zchat-channel` command available

---

### Task 6: Create GitHub Actions workflow for zchat (main repo)

**Files:**
- Create: `.github/workflows/publish.yml`
- Create: `.github/workflows/test.yml`

- [ ] **Step 1: Write publish workflow**

Same pattern as Task 4 Step 1.

- [ ] **Step 2: Write test workflow**

```yaml
name: Tests
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: true
      - uses: astral-sh/setup-uv@v4
      - run: brew install tmux
      - run: uv sync
      - run: uv run pytest tests/unit/ -v
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/
git commit -m "ci: add PyPI publish and test workflows"
```

- [ ] **Step 4: Configure trusted publisher, tag and push**

```bash
git tag v0.1.0
git push origin main --tags
```

- [ ] **Step 5: Verify**

Run: `pip install zchat==0.1.0`
Expected: installs `zchat`, `zchat-channel` commands both available

---

## Chunk 3: Homebrew Tap

### Task 7: Create homebrew-zchat repository

**Files:**
- Create: `README.md` in the new repo

- [ ] **Step 1: Create `ezagent42/homebrew-zchat` repo on GitHub**

```bash
gh repo create ezagent42/homebrew-zchat --public --description "Homebrew tap for zchat"
```

- [ ] **Step 2: Add README**

````markdown
# homebrew-zchat

Homebrew tap for [zchat](https://github.com/ezagent42/zchat) — multi-agent collaboration over IRC.

## Install

```bash
brew tap ezagent42/zchat
brew install zchat

# Optional: local IRC server
brew install ezagent42/zchat/ergo

# Optional: IRC client UI
brew install weechat
```

## Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) — required for running agents
- tmux — installed automatically by the formula

## Quick Start

```bash
tmux new -s zchat
zchat project create local
zchat irc daemon start
zchat agent create agent0
```
````

- [ ] **Step 3: Commit initial repo structure**

```bash
git add README.md
git commit -m "init: homebrew tap for zchat"
git push origin main
```

---

### Task 8: Create ergo formula

ergo (IRC server) is not in homebrew-core. Pre-built macOS binaries are available at `https://github.com/ergochat/ergo/releases`.

**Files:**
- Create: (in `ezagent42/homebrew-zchat`) `Formula/ergo.rb`

- [ ] **Step 1: Find latest ergo release URLs and SHAs**

Download arm64 and x86_64 macOS binaries from the latest release, compute sha256:

```bash
curl -sL https://github.com/ergochat/ergo/releases/download/v2.14.0/ergo-2.14.0-darwin-arm64.tar.gz | shasum -a 256
curl -sL https://github.com/ergochat/ergo/releases/download/v2.14.0/ergo-2.14.0-darwin-x86_64.tar.gz | shasum -a 256
```

Note: verify actual release filenames — ergo may use `macos` or `darwin` in the archive name. Check the release page.

- [ ] **Step 2: Write ergo formula (pre-built binary)**

```ruby
class Ergo < Formula
  desc "Modern IRC server written in Go"
  homepage "https://ergo.chat"
  license "MIT"
  version "2.14.0"

  on_arm do
    url "https://github.com/ergochat/ergo/releases/download/v2.14.0/ergo-2.14.0-darwin-arm64.tar.gz"
    sha256 "<sha256-arm64>"
  end

  on_intel do
    url "https://github.com/ergochat/ergo/releases/download/v2.14.0/ergo-2.14.0-darwin-x86_64.tar.gz"
    sha256 "<sha256-x86_64>"
  end

  def install
    bin.install "ergo"
    # Install default config if not already present
    etc.install "default.yaml" => "ergo.yaml" if buildpath.join("default.yaml").exist? && !(etc/"ergo.yaml").exist?
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/ergo version")
  end
end
```

- [ ] **Step 3: Test formula locally**

```bash
brew install --formula ./Formula/ergo.rb
ergo version
```

---

### Task 9: Create zchat Homebrew formula

This is the main formula. It uses Homebrew's Python virtualenv support to install zchat + all Python deps.

**Files:**
- Create: (in `ezagent42/homebrew-zchat`) `Formula/zchat.rb`

- [ ] **Step 1: Generate resource stanzas for all Python dependencies**

Use `poet` (homebrew-pypi-poet) to generate resource blocks:

```bash
pip install homebrew-pypi-poet
poet zchat
```

This outputs `resource` blocks for every transitive Python dependency.

- [ ] **Step 2: Write zchat formula**

```ruby
class Zchat < Formula
  include Language::Python::Virtualenv

  desc "Multi-agent collaboration over IRC — CLI for Claude Code agents"
  homepage "https://github.com/ezagent42/zchat"
  url "https://files.pythonhosted.org/packages/source/z/zchat/zchat-0.1.0.tar.gz"
  sha256 "<sha256>"
  license "MIT"

  depends_on "python@3.12"
  depends_on "tmux"

  # --- paste poet output here ---
  # resource "zchat-protocol" do
  #   url "https://files.pythonhosted.org/..."
  #   sha256 "..."
  # end
  #
  # resource "zchat-channel-server" do ...
  # resource "typer" do ...
  # resource "libtmux" do ...
  # ... (all transitive deps)

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      zchat requires Claude Code CLI to run agents.
      Install it from: https://docs.anthropic.com/en/docs/claude-code

      For local IRC server, install ergo:
        brew install ezagent42/zchat/ergo

      For IRC client UI, install WeeChat:
        brew install weechat
    EOS
  end

  test do
    assert_match "Usage", shell_output("#{bin}/zchat --help")
  end
end
```

- [ ] **Step 3: Test formula locally**

```bash
brew install --build-from-source ./Formula/zchat.rb
zchat --help
zchat-channel --help  # should also be available
```

- [ ] **Step 4: Commit and push**

```bash
git add Formula/
git commit -m "feat: add zchat and ergo formulas"
git push origin main
```

- [ ] **Step 5: Test full install flow**

```bash
brew tap ezagent42/zchat
brew install zchat
zchat --help
```

---

## Chunk 4: Formula Auto-Update (CI/CD)

### Task 10: Add workflow to auto-update Homebrew formula on release

When a new version of zchat is tagged and published to PyPI, automatically update the formula's URL and SHA in the homebrew-zchat repo.

**Files:**
- Create: `.github/workflows/update-homebrew.yml` (in zchat main repo)

- [ ] **Step 1: Write update-homebrew workflow**

```yaml
name: Update Homebrew Formula
on:
  workflow_run:
    workflows: ["Publish to PyPI"]
    types: [completed]

jobs:
  update:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Get version from tag
        id: version
        run: |
          VERSION="${GITHUB_REF#refs/tags/v}"
          echo "version=$VERSION" >> "$GITHUB_OUTPUT"

      - name: Get PyPI SHA256
        id: sha
        run: |
          VERSION="${{ steps.version.outputs.version }}"
          sleep 30  # wait for PyPI to propagate
          URL="https://files.pythonhosted.org/packages/source/z/zchat/zchat-${VERSION}.tar.gz"
          SHA=$(curl -sL "$URL" | shasum -a 256 | cut -d' ' -f1)
          echo "sha256=$SHA" >> "$GITHUB_OUTPUT"
          echo "url=$URL" >> "$GITHUB_OUTPUT"

      - name: Update formula in homebrew-zchat
        uses: peter-evans/repository-dispatch@v3
        with:
          token: ${{ secrets.HOMEBREW_TAP_TOKEN }}
          repository: ezagent42/homebrew-zchat
          event-type: update-formula
          client-payload: |
            {
              "version": "${{ steps.version.outputs.version }}",
              "url": "${{ steps.sha.outputs.url }}",
              "sha256": "${{ steps.sha.outputs.sha256 }}"
            }
```

- [ ] **Step 2: Add receiver workflow in homebrew-zchat repo**

Create `.github/workflows/update-formula.yml` in `ezagent42/homebrew-zchat`:

```yaml
name: Update Formula
on:
  repository_dispatch:
    types: [update-formula]

permissions:
  contents: write

jobs:
  update:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4

      - name: Update zchat formula
        run: |
          VERSION="${{ github.event.client_payload.version }}"
          URL="${{ github.event.client_payload.url }}"
          SHA="${{ github.event.client_payload.sha256 }}"
          sed -i '' "s|url \".*\"|url \"$URL\"|" Formula/zchat.rb
          sed -i '' "s|sha256 \".*\"|sha256 \"$SHA\"|" Formula/zchat.rb

      - name: Regenerate resources
        run: |
          pip install homebrew-pypi-poet
          VERSION="${{ github.event.client_payload.version }}"
          # This step may need manual review for complex resource updates
          poet zchat==$VERSION > /tmp/resources.txt

      - name: Commit and push
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add Formula/zchat.rb
          git commit -m "bump zchat to ${{ github.event.client_payload.version }}"
          git push
```

- [ ] **Step 3: Create HOMEBREW_TAP_TOKEN secret**

Manual step: Create a GitHub PAT with `repo` scope for `ezagent42/homebrew-zchat`, add as secret `HOMEBREW_TAP_TOKEN` in the zchat repo.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/update-homebrew.yml
git commit -m "ci: add Homebrew formula auto-update on release"
```

---

## Execution Order

```
Task 1 (protocol metadata)  ─┐
Task 2 (channel-server meta) ─┼─→ Task 4 (protocol publish) ─→ Task 5 (channel publish) ─┐
Task 3 (zchat metadata)     ─┘                                                            │
                                                                                           ├─→ Task 6 (zchat publish)
Task 7 (create tap repo) ────→ Task 8 (ergo formula)                                      │
                               Task 9 (zchat formula) ←────────────────────────────────────┘
                               Task 10 (auto-update CI)
```

Tasks 1, 2, 3 are independent → parallel.
Task 7 is independent of PyPI work → parallel with Tasks 1-3.
Task 4 must complete before Task 5 (channel-server depends on protocol on PyPI).
Task 5 must complete before Task 6.
Task 8 can run after Task 7 (no PyPI dependency, just binary download).
Task 9 requires Task 6 (needs PyPI URLs and SHAs for zchat formula).
Task 10 depends on Tasks 6 and 7.

---

## User Actions Required (cannot be automated)

1. **PyPI trusted publisher setup** — configure on pypi.org for each of the 3 repos
2. **GitHub PAT** — create and add as `HOMEBREW_TAP_TOKEN` secret
3. **Install Claude Code** — not automatable via Homebrew, must be documented
4. **Test the full flow** — `brew install ezagent42/zchat/zchat` on a clean machine

## Post-Distribution Checklist

- [ ] Update main README with `brew install` instructions
- [ ] Update CLAUDE.md with distribution notes
- [ ] Tag all submodules to matching versions
- [ ] Test on Intel and Apple Silicon Macs
- [ ] Verify `zchat-channel` command is on PATH after install
