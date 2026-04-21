# IRC Connectivity Check Before Start

Ref: ezagent42/zchat#31

## Problem

`zchat irc start` and `zchat agent create` launch processes without checking if the IRC server is reachable. If the server is down, WeeChat/agent starts but silently fails to connect.

## Design

Add a `check_irc_connectivity(server, port, tls=False, timeout=5)` function. Call it in `IrcManager.start_weechat()` and `AgentManager.create()` before launching processes.

### Function

```python
def check_irc_connectivity(server: str, port: int, tls: bool = False, timeout: float = 5) -> None:
    """Raise ConnectionError if IRC server is unreachable."""
    import socket
    import ssl
    try:
        sock = socket.create_connection((server, port), timeout=timeout)
        if tls:
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=server)
        sock.close()
    except OSError as e:
        raise ConnectionError(f"Cannot reach IRC server {server}:{port} — {e}")
```

### Call sites

1. **`IrcManager.start_weechat()`** — check before launching WeeChat. Catch `ConnectionError`, print message, `raise typer.Exit(1)`.
2. **`AgentManager.create()`** — check before spawning tmux window. Let `ConnectionError` propagate (CLI layer catches it).
3. **`zchat irc daemon start`** — NO check (it starts the server itself).

### File placement

Function goes in `zchat/cli/irc_manager.py` as a module-level function (both managers already import from this module or can import cheaply).

## File Changes

1. **Modify: `zchat/cli/irc_manager.py`** — add `check_irc_connectivity()`, call in `start_weechat()`
2. **Modify: `zchat/cli/agent_manager.py`** — call `check_irc_connectivity()` in `create()`
3. **Modify: `zchat/cli/app.py`** — catch `ConnectionError` in `cmd_agent_create`, show user-friendly message
4. **Test: `tests/unit/test_irc_check.py`** — unit tests for the function

## Test Plan

- Unit test: reachable server returns without error
- Unit test: unreachable server raises ConnectionError
- Unit test: TLS connection check
- Existing E2E + pre-release tests must still pass
