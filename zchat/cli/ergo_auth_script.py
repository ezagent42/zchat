#!/usr/bin/env python3
"""Ergo auth-script: validate SASL PLAIN credentials against Keycloak userinfo.

Protocol (stdin/stdout JSON):
  Input:  {"accountName": "alice", "passphrase": "<access_token>"}
  Output: {"success": true, "accountName": "alice"}
          or {"success": false, "error": "reason"}

Config via env:
  KEYCLOAK_USERINFO_URL — Keycloak userinfo endpoint
"""
import json
import os
import sys

import httpx

# Inline the separator constant to avoid zchat_protocol dependency at runtime
# (ergo spawns this script as a subprocess — zchat venv may not be available)
AGENT_SEPARATOR = "-"


def validate_credentials(
    account_name: str,
    passphrase: str,
    userinfo_url: str,
    http_client: httpx.Client | None = None,
) -> dict:
    """Validate a SASL credential pair against Keycloak.

    Returns dict with 'success' bool and 'accountName' or 'error'.
    """
    client = http_client or httpx.Client()
    try:
        resp = client.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {passphrase}"},
            timeout=8.0,
        )
        if resp.status_code != 200:
            return {"success": False, "error": f"Keycloak returned {resp.status_code}"}
        userinfo = resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

    preferred_username = userinfo.get("preferred_username", "")

    # For agents (e.g., "alice-agent0"), check that the owner matches
    if AGENT_SEPARATOR in account_name:
        owner = account_name.split(AGENT_SEPARATOR, 1)[0]
    else:
        owner = account_name

    if owner != preferred_username:
        return {
            "success": False,
            "error": f"Username mismatch: token is for '{preferred_username}', not '{owner}'",
        }

    return {"success": True, "accountName": account_name}


def _read_config() -> str:
    """Read userinfo URL from config file (written alongside this script by zchat)."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth_script_config.json")
    if os.path.isfile(config_path):
        with open(config_path) as f:
            return json.load(f).get("userinfo_url", "")
    # Fallback to env var
    return os.environ.get("KEYCLOAK_USERINFO_URL", "")


def main():
    """Entry point when run as ergo auth-script subprocess."""
    userinfo_url = _read_config()
    if not userinfo_url:
        print(json.dumps({"success": False, "error": "No userinfo URL configured"}))
        sys.exit(0)

    try:
        input_data = json.loads(sys.stdin.readline())
    except (json.JSONDecodeError, EOFError):
        print(json.dumps({"success": False, "error": "Invalid input"}))
        sys.exit(0)

    result = validate_credentials(
        account_name=input_data.get("accountName", ""),
        passphrase=input_data.get("passphrase", ""),
        userinfo_url=userinfo_url,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
