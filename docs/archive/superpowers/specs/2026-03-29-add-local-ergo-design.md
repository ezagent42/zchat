# Add Persistent Local Ergo IRC Service

**Date:** 2026-03-29
**Status:** Draft

## Goal

Deploy a persistent ergo IRC server on the local machine, exposed to the internal network via `zchat.inside.h2os.cloud:6697` (TLS), and update zchat CLI to use it as the default.

## Architecture

```
IRC clients (WeeChat, irssi, etc.)
        │
        │ TLS :6697
        ▼
┌─────────────────────────┐
│ Caddy (L4 TCP proxy)    │  SNI: zchat.inside.h2os.cloud
│ TLS termination         │  Cert: *.inside.h2os.cloud (ACME DNS)
└─────────┬───────────────┘
          │ plaintext :6667
          ▼
┌─────────────────────────┐
│ ergo IRC server          │  127.0.0.1:6667
│ launchd managed          │  Network: zchat
│ ~/.config/ergo/          │  Server: zchat.inside.h2os.cloud
└─────────────────────────┘
```

## Components

### 1. Ergo Persistent Service

- **Config:** `~/.config/ergo/ergo.yaml` (static, not per-project)
- **Data:** `~/.config/ergo/` (database, logs)
- **Listener:** `127.0.0.1:6667` only (Caddy handles external TLS)
- **Network name:** `zchat`
- **Server name:** `zchat.inside.h2os.cloud`
- **launchd:** `~/Library/LaunchAgents/com.h2os.ergo.plist`
  - RunAtLoad: true
  - KeepAlive: true

### 2. Caddy Configuration Changes

Update `~/.config/caddy/Caddyfile`:

- Change TLS from per-domain to wildcard `*.inside.h2os.cloud`
- Keep `hackforger.inside.h2os.cloud` HTTP reverse proxy
- Add L4 TCP listener on `:6697` with TLS termination → `127.0.0.1:6667`

Caddy L4 uses JSON config (not Caddyfile) for TCP proxying, so we convert to JSON config format or use a global L4 listener block.

### 3. zchat CLI Changes

**File:** `zchat/cli/project.py` — `create()` flow

Replace the IRC server configuration prompt:

```
IRC Server:
  1) zchat.inside.h2os.cloud (recommended)
  2) Custom server

> 1   → server=zchat.inside.h2os.cloud, port=6697, tls=true
> 2   → prompt for server, port (existing flow)
```

**File:** `zchat/cli/irc_manager.py` — `daemon_start()`

- If server is not localhost/127.0.0.1/::1 → skip local daemon start (already the case)
- No changes needed to daemon logic itself

### 4. DNS

`zchat.inside.h2os.cloud` must resolve to this machine's internal IP. This is outside scope of this spec (manual DNS record in AliCloud).

## Out of Scope

- TLS client certificates
- Multi-project isolation (shared IRC space, per decision)
- ergo operator/admin accounts (use defaults)
- WebSocket support
