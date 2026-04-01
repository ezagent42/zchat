# Remote IRC Test Coverage

**Date:** 2026-04-01

## Problem

Current tests only cover local ergo without TLS/SASL. The nick bug (SASL login overriding agent nick) was not caught because no test verified the agent's nick after SASL authentication against a real ergo with auth-script.

## Design

### 1. IrcProbe TLS+SASL Support

Add optional `tls` and `sasl` parameters to `IrcProbe.__init__()` and `connect()`:

```python
def __init__(self, server, port, nick="e2e-probe", tls=False, sasl_login=None, sasl_pass=None):
```

When `tls=True`, wrap the connection with SSL. When `sasl_login` is provided, pass it to `connect()` as SASL credentials.

### 2. Pre-release: Remote IRC Test Module

**New:** `tests/pre_release/test_04b_remote_irc.py`

**Pre-condition:** TCP check to `zchat.inside.h2os.cloud:6697`. Skip if not reachable.

**Fixtures:** `remote_irc_probe` in conftest — connects to remote ergo with TLS+SASL using OIDC credentials from `auth.json`.

**Tests:**
- `test_remote_irc_connect` — WeeChat connects to remote ergo, verify `[Zi]` in capture-pane
- `test_remote_agent_nick` — `agent create agent0`, verify nick is `{username}-agent0` via remote irc_probe WHOIS

### 3. Unit Tests

Already covered: `test_ergo_auth_script.py` has `test_auth_script_valid_agent` and `test_auth_script_rejects_wrong_owner`.

### 4. E2E

No changes — local ergo without SASL. Existing `wait_for_nick("alice-agent0")` provides basic nick assertion.

### Files Changed

| File | Change |
|------|--------|
| `tests/shared/irc_probe.py` | Add TLS + SASL support |
| `tests/pre_release/conftest.py` | Add `remote_irc_probe` fixture |
| `tests/pre_release/test_04b_remote_irc.py` | New: remote IRC connection + agent nick tests |
