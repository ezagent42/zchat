#!/bin/bash
set -euo pipefail

# zchat installer — bootstraps all dependencies and installs zchat
# Usage: curl -fsSL https://raw.githubusercontent.com/ezagent42/zchat/main/install.sh | bash
#        curl ... | bash -s -- --channel release

CHANNEL="main"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --channel) CHANNEL="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

info()  { echo "==> $*"; }
warn()  { echo "WARNING: $*" >&2; }
error() { echo "ERROR: $*" >&2; exit 1; }

# ---- 1. Detect OS ----
OS="$(uname -s)"
case "$OS" in
  Darwin) PLATFORM="macos" ;;
  Linux)  PLATFORM="linux" ;;
  *)      error "Unsupported OS: $OS" ;;
esac
info "Detected platform: $PLATFORM"

# ---- 2. System dependencies via Homebrew ----
NEED_BREW=false
for cmd in tmux weechat; do
  if ! command -v "$cmd" &>/dev/null; then
    NEED_BREW=true
    break
  fi
done

# ergo always from tap
if ! command -v ergo &>/dev/null; then
  NEED_BREW=true
fi

if [ "$NEED_BREW" = true ]; then
  if ! command -v brew &>/dev/null; then
    info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add brew to PATH for this session
    if [ "$PLATFORM" = "linux" ]; then
      eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv 2>/dev/null || true)"
    fi
  fi

  info "Installing system dependencies via Homebrew..."
  brew tap ezagent42/zchat 2>/dev/null || true

  for pkg in tmux weechat; do
    if ! command -v "$pkg" &>/dev/null; then
      info "  Installing $pkg..."
      brew install "$pkg"
    else
      info "  $pkg already installed, skipping"
    fi
  done

  if ! command -v ergo &>/dev/null; then
    info "  Installing ergo..."
    brew install ezagent42/zchat/ergo
  else
    info "  ergo already installed, skipping"
  fi
fi

# ---- 3. Install uv ----
if ! command -v uv &>/dev/null; then
  info "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
info "uv: $(uv --version)"

# ---- 4. Ensure Python 3.11+ ----
PYTHON_OK=false
if command -v python3 &>/dev/null; then
  PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
  if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 11 ]; then
    PYTHON_OK=true
  fi
fi

if [ "$PYTHON_OK" = false ]; then
  info "Installing Python 3.11 via uv..."
  uv python install 3.11
fi

# ---- 5. Install zchat + channel-server ----
info "Installing zchat (channel: $CHANNEL)..."

case "$CHANNEL" in
  main|dev)
    # zchat-protocol is not on PyPI — must be installed from git.
    # Both zchat and zchat-channel-server depend on it, and their
    # [tool.uv.sources] uses local paths for dev. --no-sources skips
    # those path overrides; --with injects the git source instead.
    PROTO="zchat-protocol @ git+https://github.com/ezagent42/zchat-protocol.git@${CHANNEL}"
    uv tool install --force --no-sources --with "$PROTO" \
      "zchat @ git+https://github.com/ezagent42/zchat.git@${CHANNEL}"
    uv tool install --force --no-sources --with "$PROTO" \
      "zchat-channel-server @ git+https://github.com/ezagent42/claude-zchat-channel.git@${CHANNEL}"
    ;;
  release)
    uv tool install --force zchat
    uv tool install --force zchat-channel-server
    ;;
  *)
    error "Unknown channel: $CHANNEL (expected: main, dev, release)"
    ;;
esac

# ---- 6. Install tmuxp ----
if ! command -v tmuxp &>/dev/null; then
  info "Installing tmuxp..."
  uv tool install tmuxp
fi

# ---- 7. Check Claude CLI ----
if ! command -v claude &>/dev/null; then
  warn "Claude Code CLI not found."
  echo "  Install it from: https://docs.anthropic.com/en/docs/claude-code"
  echo "  zchat agents require Claude Code to run."
fi

# ---- 8. Write initial config ----
ZCHAT_DIR="${ZCHAT_HOME:-$HOME/.zchat}"
mkdir -p "$ZCHAT_DIR"

# Save channel to global config
if [ ! -f "$ZCHAT_DIR/config.toml" ]; then
  cat > "$ZCHAT_DIR/config.toml" <<TOML
[update]
channel = "$CHANNEL"
auto_upgrade = true
TOML
fi

# ---- 9. Initialize update state ----
# Run zchat update to set initial installed refs (prevents false "update available")
info "Initializing update state..."
zchat update >/dev/null 2>&1 || true

# ---- 10. Verify ----
info "Verifying installation..."
echo ""
zchat doctor || true
echo ""

info "Installation complete!"
echo ""
echo "Quick start:"
echo "  zchat project create local"
echo "  zchat irc daemon start"
echo "  zchat irc start"
echo "  zchat agent create agent0"
echo ""
echo "Update channel: $CHANNEL"
echo "  Change with: zchat config set update.channel <main|dev|release>"
echo "  Upgrade:     zchat upgrade"
