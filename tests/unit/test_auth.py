import time

from zchat.cli.auth import save_token, load_cached_token


def test_save_token_creates_file_with_restricted_perms(tmp_path):
    token_data = {
        "access_token": "test-token",
        "refresh_token": "test-refresh",
        "expires_at": time.time() + 3600,
        "username": "alice",
    }
    save_token(str(tmp_path), token_data)
    auth_file = tmp_path / "auth.json"
    assert auth_file.exists()
    assert oct(auth_file.stat().st_mode & 0o777) == "0o600"


def test_load_cached_token_returns_valid_token(tmp_path):
    token_data = {
        "access_token": "test-token",
        "refresh_token": "test-refresh",
        "expires_at": time.time() + 3600,
        "username": "alice",
    }
    save_token(str(tmp_path), token_data)
    result = load_cached_token(str(tmp_path))
    assert result is not None
    assert result["access_token"] == "test-token"
    assert result["username"] == "alice"


def test_load_cached_token_returns_none_when_expired(tmp_path):
    token_data = {
        "access_token": "expired-token",
        "refresh_token": "test-refresh",
        "expires_at": time.time() - 10,
        "username": "alice",
    }
    save_token(str(tmp_path), token_data)
    result = load_cached_token(str(tmp_path))
    assert result is None


def test_load_cached_token_returns_none_when_missing(tmp_path):
    result = load_cached_token(str(tmp_path))
    assert result is None


import httpx

from zchat.cli.auth import discover_oidc_endpoints, device_code_flow


def test_discover_oidc_endpoints():
    discovery_doc = {
        "token_endpoint": "https://kc.test/token",
        "device_authorization_endpoint": "https://kc.test/device",
        "userinfo_endpoint": "https://kc.test/userinfo",
    }
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=discovery_doc))
    client = httpx.Client(transport=transport)
    endpoints = discover_oidc_endpoints("https://kc.test/realms/zchat", client=client)
    assert endpoints["token_endpoint"] == "https://kc.test/token"
    assert endpoints["device_authorization_endpoint"] == "https://kc.test/device"
    assert endpoints["userinfo_endpoint"] == "https://kc.test/userinfo"


def test_device_code_flow_success(tmp_path, capsys):
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "well-known" in url:
            return httpx.Response(200, json={
                "token_endpoint": "https://kc.test/token",
                "device_authorization_endpoint": "https://kc.test/device",
                "userinfo_endpoint": "https://kc.test/userinfo",
            })
        if url == "https://kc.test/device":
            return httpx.Response(200, json={
                "device_code": "dev-code-123",
                "user_code": "ABCD-1234",
                "verification_uri": "https://kc.test/device",
                "interval": 0,
                "expires_in": 600,
            })
        if url == "https://kc.test/token":
            call_count["n"] += 1
            if call_count["n"] < 2:
                return httpx.Response(400, json={"error": "authorization_pending"})
            return httpx.Response(200, json={
                "access_token": "at-12345",
                "refresh_token": "rt-67890",
                "expires_in": 300,
                "id_token": "dummy",
            })
        if url == "https://kc.test/userinfo":
            return httpx.Response(200, json={
                "preferred_username": "alice",
                "email": "alice@test.com",
            })
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    result = device_code_flow(
        issuer="https://kc.test/realms/zchat",
        client_id="zchat-cli",
        http_client=client,
    )
    assert result["access_token"] == "at-12345"
    assert result["refresh_token"] == "rt-67890"
    assert result["username"] == "alice"
    assert result["client_id"] == "zchat-cli"
    assert "expires_at" in result
    captured = capsys.readouterr()
    assert "ABCD-1234" in captured.out


from zchat.cli.auth import refresh_token_if_needed, get_credentials


def test_refresh_token_if_needed_refreshes_expired(tmp_path):
    save_token(str(tmp_path), {
        "access_token": "old-token",
        "refresh_token": "valid-refresh",
        "expires_at": time.time() - 10,
        "username": "alice",
        "userinfo_endpoint": "https://kc.test/userinfo",
    })

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "token" in url:
            return httpx.Response(200, json={
                "access_token": "new-token",
                "refresh_token": "new-refresh",
                "expires_in": 300,
            })
        if "userinfo" in url:
            return httpx.Response(200, json={"preferred_username": "alice"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    result = refresh_token_if_needed(
        str(tmp_path),
        token_endpoint="https://kc.test/token",
        client_id="zchat-cli",
        http_client=client,
    )
    assert result is not None
    assert result["access_token"] == "new-token"


def test_get_credentials_returns_username_and_token(tmp_path):
    save_token(str(tmp_path), {
        "access_token": "good-token",
        "refresh_token": "refresh",
        "expires_at": time.time() + 3600,
        "username": "alice",
    })
    username, token = get_credentials(str(tmp_path))
    assert username == "alice"
    assert token == "good-token"


def test_get_credentials_returns_none_when_no_token(tmp_path):
    result = get_credentials(str(tmp_path))
    assert result is None
