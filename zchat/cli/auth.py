"""OIDC authentication: device code flow, token caching, credential management."""
import json
import os
import time

import httpx


AUTH_FILE = "auth.json"


def save_token(project_dir: str, token_data: dict):
    """Save token data to auth.json with restricted permissions (0600)."""
    auth_path = os.path.join(project_dir, AUTH_FILE)
    fd = os.open(auth_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(token_data, f, indent=2)


def load_cached_token(project_dir: str) -> dict | None:
    """Load cached token if it exists and is not expired. Returns None otherwise."""
    auth_path = os.path.join(project_dir, AUTH_FILE)
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
    """Fetch OIDC discovery document and return endpoint URLs."""
    url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
    c = client or httpx.Client()
    resp = c.get(url)
    resp.raise_for_status()
    return resp.json()


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
        data={"client_id": client_id, "scope": "openid profile email"},
    )
    resp.raise_for_status()
    device = resp.json()

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

    return {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", ""),
        "expires_at": time.time() + token_data.get("expires_in", 300),
        "username": userinfo.get("preferred_username", ""),
        "client_id": client_id,
        "token_endpoint": endpoints["token_endpoint"],
        "userinfo_endpoint": endpoints["userinfo_endpoint"],
    }
