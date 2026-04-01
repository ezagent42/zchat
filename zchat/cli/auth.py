"""OIDC authentication: device code flow, token caching, credential management."""
import json
import os
import time

import httpx


AUTH_FILE = "auth.json"


def _global_auth_dir() -> str:
    """Return the global zchat directory for auth storage (~/.zchat/)."""
    from zchat.cli.project import ZCHAT_DIR
    return ZCHAT_DIR


def get_username(base_dir: str | None = None) -> str:
    """Return the globally configured username.

    Reads username directly from auth.json, bypassing token expiry
    validation. Username is an identity, not a credential — it remains
    valid even when the access token has expired or when using
    --method local (which has no token at all).
    """
    if base_dir is None:
        base_dir = _global_auth_dir()
    auth_path = os.path.join(base_dir, AUTH_FILE)
    if not os.path.isfile(auth_path):
        raise RuntimeError(
            "No username configured. Run one of:\n"
            "  zchat auth login                              # OIDC authentication\n"
            "  zchat auth login --method local --username <name>  # Local mode"
        )
    with open(auth_path) as f:
        data = json.load(f)
    username = data.get("username", "")
    if not username:
        raise RuntimeError(
            "No username configured. Run one of:\n"
            "  zchat auth login                              # OIDC authentication\n"
            "  zchat auth login --method local --username <name>  # Local mode"
        )
    return username


def save_token(base_dir: str, token_data: dict):
    """Save token data to auth.json with restricted permissions (0600)."""
    os.makedirs(base_dir, exist_ok=True)
    auth_path = os.path.join(base_dir, AUTH_FILE)
    fd = os.open(auth_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(token_data, f, indent=2)


def load_cached_token(base_dir: str) -> dict | None:
    """Load cached token if it exists and is not expired. Returns None otherwise."""
    auth_path = os.path.join(base_dir, AUTH_FILE)
    if not os.path.isfile(auth_path):
        return None
    try:
        with open(auth_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("expires_at", 0) < time.time():
        return None
    return data


def discover_oidc_endpoints(issuer: str, client: httpx.Client | None = None) -> dict:
    """Fetch OIDC discovery document and return endpoint URLs.

    Tries standard path first, then /oidc/ prefix (Logto uses this).
    """
    c = client or httpx.Client()
    base = issuer.rstrip("/")
    for path in [
        f"{base}/.well-known/openid-configuration",
        f"{base}/oidc/.well-known/openid-configuration",
    ]:
        resp = c.get(path)
        if resp.status_code == 200:
            return resp.json()
    # All paths failed — raise with the last response
    resp.raise_for_status()
    return resp.json()  # unreachable, but satisfies type checker


def _print_qr(url: str):
    """Print QR code to terminal using segno (if available) or skip."""
    try:
        import segno
        import io
        qr = segno.make(url)
        buf = io.StringIO()
        qr.terminal(out=buf, compact=True)
        print(buf.getvalue())
    except ImportError:
        # segno not installed — just show URL
        print(f"\n  {url}\n")


def _sanitize_irc_nick(raw: str) -> str:
    """Sanitize a string into a valid IRC nick (RFC 2812).

    Keeps letters, digits, and - _ \\ [ ] { } ^ |
    Strips everything else (. / @ : ! # etc.).
    Ensures the first character is a letter or allowed special char.
    """
    import re
    nick = re.sub(r"[^A-Za-z0-9\-_\\\[\]\{\}\^|]", "", raw)
    # First char must be a letter or special (not digit or -)
    nick = nick.lstrip("0123456789-")
    return nick or "user"


def _extract_username(userinfo: dict) -> str:
    """Extract username from OIDC userinfo with fallback chain.

    Priority: username → preferred_username → email (local part) → sub
    Skips 'name' — it may be a full name with spaces or non-ASCII chars.
    Result is sanitized to be a valid IRC nick.
    """
    for field in ("username", "preferred_username"):
        val = userinfo.get(field)
        if val:
            return _sanitize_irc_nick(val)
    email = userinfo.get("email", "")
    if email:
        return _sanitize_irc_nick(email.split("@")[0])
    return _sanitize_irc_nick(userinfo.get("sub", ""))


def device_code_flow(
    issuer: str,
    client_id: str,
    http_client: httpx.Client | None = None,
) -> dict:
    """Run OIDC device code flow. Returns dict with access_token, refresh_token, username, expires_at."""
    client = http_client or httpx.Client()
    endpoints = discover_oidc_endpoints(issuer, client=client)

    resp = client.post(
        endpoints["device_authorization_endpoint"],
        data={"client_id": client_id, "scope": "openid offline_access profile email"},
    )
    resp.raise_for_status()
    device = resp.json()

    # Show verification URL + QR code if verification_uri_complete is available
    complete_uri = device.get("verification_uri_complete", "")
    if complete_uri:
        _print_qr(complete_uri)
        print(f"  Scan the QR code, or open: {complete_uri}\n")
    else:
        print(f"\nOpen this URL in your browser:\n  {device['verification_uri']}")
        print(f"\nEnter code: {device['user_code']}\n")
    print("Waiting for authentication...")

    interval = device.get("interval", 5)
    deadline = time.time() + device.get("expires_in", 600)
    token_url = endpoints["token_endpoint"]
    while time.time() < deadline:
        time.sleep(interval)
        resp = client.post(token_url, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client_id,
            "device_code": device["device_code"],
        })
        if resp.status_code == 200:
            token_data = resp.json()
            break
        body = resp.json()
        error = body.get("error", "")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        raise RuntimeError(f"Device code flow failed: {body}")
    else:
        raise RuntimeError("Device code expired. Please try again.")

    userinfo_resp = client.get(
        endpoints["userinfo_endpoint"],
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    userinfo_resp.raise_for_status()
    userinfo = userinfo_resp.json()

    email = userinfo.get("email", "")
    return {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", ""),
        "expires_at": time.time() + token_data.get("expires_in", 300),
        "email": email,
        "username": email.split("@")[0] if "@" in email else _extract_username(userinfo),
        "client_id": client_id,
        "token_endpoint": endpoints["token_endpoint"],
        "userinfo_endpoint": endpoints["userinfo_endpoint"],
    }


def refresh_token_if_needed(
    base_dir: str,
    token_endpoint: str,
    client_id: str,
    http_client: httpx.Client | None = None,
) -> dict | None:
    """Refresh the access token using the refresh_token. Returns updated token data or None."""
    auth_path = os.path.join(base_dir, AUTH_FILE)
    if not os.path.isfile(auth_path):
        return None
    with open(auth_path) as f:
        data = json.load(f)
    refresh_tok = data.get("refresh_token")
    if not refresh_tok:
        return None
    client = http_client or httpx.Client()
    resp = client.post(token_endpoint, data={
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_tok,
    })
    if resp.status_code != 200:
        return None
    new_tokens = resp.json()
    data["access_token"] = new_tokens["access_token"]
    data["refresh_token"] = new_tokens.get("refresh_token", refresh_tok)
    data["expires_at"] = time.time() + new_tokens.get("expires_in", 300)
    save_token(base_dir, data)
    return data


def get_credentials(
    base_dir: str | None = None,
    client_id: str = "",
    http_client: httpx.Client | None = None,
) -> tuple[str, str] | None:
    """Return (username, access_token) if valid credentials exist.

    Uses global ~/.zchat/auth.json by default.
    Auto-refreshes if access_token is expired but refresh_token + token_endpoint are available.
    client_id is read from stored auth.json if not provided (saved during device_code_flow).
    Returns None if no valid credentials can be obtained.
    """
    if base_dir is None:
        base_dir = _global_auth_dir()
    data = load_cached_token(base_dir)
    if data is None:
        auth_path = os.path.join(base_dir, AUTH_FILE)
        if not os.path.isfile(auth_path):
            return None
        with open(auth_path) as f:
            stored = json.load(f)
        token_endpoint = stored.get("token_endpoint", "")
        cid = client_id or stored.get("client_id", "")
        if token_endpoint and cid and stored.get("refresh_token"):
            data = refresh_token_if_needed(
                base_dir, token_endpoint=token_endpoint,
                client_id=cid, http_client=http_client,
            )
        if data is None:
            return None
    username = data.get("username", "")
    token = data.get("access_token", "")
    if not username or not token:
        return None
    return (username, token)
