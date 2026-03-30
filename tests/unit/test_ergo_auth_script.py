"""Tests for the ergo auth-script (Keycloak token validation)."""
import httpx

from zchat.cli.ergo_auth_script import validate_credentials


def test_auth_script_valid_user():
    """Auth-script accepts valid token where username matches accountName."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization") == "Bearer valid-token":
            return httpx.Response(200, json={"preferred_username": "alice"})
        return httpx.Response(401)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    result = validate_credentials(
        account_name="alice",
        passphrase="valid-token",
        userinfo_url="https://kc.test/userinfo",
        http_client=client,
    )
    assert result["success"] is True
    assert result["accountName"] == "alice"


def test_auth_script_valid_agent():
    """Auth-script accepts token for agent where owner matches preferred_username."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"preferred_username": "alice"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    result = validate_credentials(
        account_name="alice-agent0",
        passphrase="valid-token",
        userinfo_url="https://kc.test/userinfo",
        http_client=client,
    )
    assert result["success"] is True
    assert result["accountName"] == "alice-agent0"


def test_auth_script_rejects_wrong_owner():
    """Auth-script rejects token where preferred_username does not match owner."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"preferred_username": "bob"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    result = validate_credentials(
        account_name="alice-agent0",
        passphrase="bobs-token",
        userinfo_url="https://kc.test/userinfo",
        http_client=client,
    )
    assert result["success"] is False


def test_auth_script_rejects_invalid_token():
    """Auth-script rejects when Keycloak returns 401."""
    transport = httpx.MockTransport(lambda r: httpx.Response(401))
    client = httpx.Client(transport=transport)
    result = validate_credentials(
        account_name="alice",
        passphrase="bad-token",
        userinfo_url="https://kc.test/userinfo",
        http_client=client,
    )
    assert result["success"] is False
