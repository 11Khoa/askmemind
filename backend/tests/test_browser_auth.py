from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.dependencies import get_token_store
from app.core.security import hash_token
from app.main import app, configure_cors
from app.models.refresh_token import RefreshToken
from app.services.token_store import TokenStore, TokenStoreUnavailable

CREDS = {"email": "browser@example.com", "password": "test-password-123"}


def login(client):
    assert client.post("/auth/register", json=CREDS).status_code == 201
    response = client.post("/auth/login", json=CREDS)
    assert response.status_code == 200
    return response


def response_cookie(response):
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie[settings.auth_refresh_cookie_name]


def cookie_header(raw):
    return {"Cookie": f"{settings.auth_refresh_cookie_name}={raw}"}


def test_login_sets_persistent_host_only_httponly_cookie(
    browser_client, db_session, caplog
):
    response = login(browser_client)
    cookie = response_cookie(response)
    assert set(response.json()) == {"access_token", "token_type"}
    assert cookie["httponly"] and cookie["secure"]
    assert cookie["samesite"] == "lax"
    assert cookie["path"] == "/"
    assert not cookie["domain"]
    assert int(cookie["max-age"]) > 0
    token = (
        db_session.query(RefreshToken)
        .filter_by(token_hash=hash_token(cookie.value))
        .one()
    )
    assert parsedate_to_datetime(cookie["expires"]) == token.expires_at.replace(
        microsecond=0
    )
    assert cookie.value not in caplog.text
    assert response.json()["access_token"] not in caplog.text
    assert response.headers["cache-control"] == "no-store"


def test_new_browser_instance_refreshes_with_cookie_without_access_token(
    browser_client,
):
    login(browser_client)
    reopened = TestClient(
        app,
        base_url="https://api.example.com",
        cookies=browser_client.cookies,
        headers=dict(browser_client.headers),
    )
    try:
        response = reopened.post("/auth/refresh")
        assert response.status_code == 200
        assert set(response.json()) == {"access_token", "token_type"}
        assert (
            reopened.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {response.json()['access_token']}"},
            ).status_code
            == 200
        )
    finally:
        reopened.close()


def test_rotation_preserves_absolute_cookie_and_db_expiry(
    browser_client, db_session, monkeypatch
):
    from app.core import browser_auth

    first = login(browser_client)
    old = response_cookie(first)
    original = (
        db_session.query(RefreshToken).filter_by(token_hash=hash_token(old.value)).one()
    )
    expires_at = original.expires_at

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(minutes=10)

    monkeypatch.setattr(browser_auth, "datetime", Later)
    response = browser_client.post("/auth/refresh")
    assert response.status_code == 200
    new = response_cookie(response)
    assert new.value != old.value
    assert new["expires"] == old["expires"]
    assert int(new["max-age"]) <= int(old["max-age"]) - 599
    db_session.refresh(original)
    replacement = db_session.get(RefreshToken, original.replaced_by_token_id)
    assert replacement.expires_at == expires_at
    assert replacement.token_hash == hash_token(new.value)
    assert original.revoked_at is not None


def test_browser_replay_revokes_replacement_and_clears_cookie(
    browser_client, db_session
):
    first = response_cookie(login(browser_client)).value
    second = response_cookie(browser_client.post("/auth/refresh")).value
    replay = browser_client.post("/auth/refresh", headers=cookie_header(first))
    assert replay.status_code == 401
    assert response_cookie(replay)["max-age"] == "0"
    assert (
        browser_client.post("/auth/refresh", headers=cookie_header(second)).status_code
        == 401
    )
    assert all(
        token.revoked_at is not None for token in db_session.query(RefreshToken).all()
    )


@pytest.mark.parametrize(
    "kind", ["missing", "malformed", "unknown", "expired", "revoked"]
)
def test_refresh_rejects_bad_cookies_and_deletes_them(browser_client, db_session, kind):
    raw = response_cookie(login(browser_client)).value
    if kind in {"expired", "revoked"}:
        token = (
            db_session.query(RefreshToken).filter_by(token_hash=hash_token(raw)).one()
        )
        if kind == "expired":
            token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        else:
            token.revoked_at = datetime.now(timezone.utc)
        db_session.commit()
    if kind == "missing":
        browser_client.cookies.clear()
        headers = {}
    else:
        headers = cookie_header(
            "bad" if kind == "malformed" else "x" * 43 if kind == "unknown" else raw
        )
    response = browser_client.post("/auth/refresh", headers=headers)
    assert response.status_code == 401
    deleted = response_cookie(response)
    assert deleted["max-age"] == "0"
    assert deleted["path"] == "/" and deleted["httponly"] and deleted["secure"]
    assert deleted["samesite"] == "lax" and not deleted["domain"]


@pytest.mark.parametrize("cookie", [None, "bad-cookie"])
def test_browser_refresh_never_falls_back_to_json(browser_client, cookie):
    raw = response_cookie(login(browser_client)).value
    browser_client.cookies.clear()
    response = browser_client.post(
        "/auth/refresh",
        json={"refresh_token": raw},
        headers=cookie_header(cookie) if cookie else {},
    )
    assert response.status_code == 401


def test_logout_revokes_refresh_blacklists_access_and_matches_cookie_flags(
    browser_client, db_session
):
    logged_in = login(browser_client)
    cookie = response_cookie(logged_in)
    access = logged_in.json()["access_token"]
    headers = {"Authorization": f"Bearer {access}"}
    response = browser_client.post("/auth/logout", headers=headers)
    assert response.status_code == 204
    assert not response.content
    deleted = response_cookie(response)
    for key in ["path", "domain", "secure", "httponly", "samesite"]:
        assert deleted[key] == cookie[key]
    assert deleted["max-age"] == "0"
    assert not browser_client.cookies
    assert (
        db_session.query(RefreshToken)
        .filter_by(token_hash=hash_token(cookie.value))
        .one()
        .revoked_at
        is not None
    )
    assert browser_client.get("/auth/me", headers=headers).status_code == 401
    assert (
        browser_client.post(
            "/auth/refresh", headers=cookie_header(cookie.value)
        ).status_code
        == 401
    )


def test_logout_invalid_cookie_is_cleared_without_revoking_other_user(
    browser_client, auth_client
):
    first = login(browser_client)
    other = {"email": "other-cookie@example.com", "password": "password123"}
    assert auth_client.post("/auth/register", json=other).status_code == 201
    second = auth_client.post("/auth/token/login", json=other).json()
    headers = {
        **cookie_header(second["refresh_token"]),
        "Authorization": f"Bearer {first.json()['access_token']}",
    }
    response = browser_client.post("/auth/logout", headers=headers)
    assert response.status_code == 401
    assert response_cookie(response)["max-age"] == "0"
    assert (
        auth_client.post(
            "/auth/token/refresh", json={"refresh_token": second["refresh_token"]}
        ).status_code
        == 200
    )


@pytest.mark.parametrize("path", ["/auth/login", "/auth/refresh", "/auth/logout"])
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://app.example.com"},
        {"X-CSRF-Protection": "1"},
        {"Origin": "null", "X-CSRF-Protection": "1"},
        {"Origin": "https://evil.example", "X-CSRF-Protection": "1"},
        {"Origin": "https://app.example.com.evil.test", "X-CSRF-Protection": "1"},
        {"Origin": "https://app.example.com", "X-CSRF-Protection": "wrong"},
    ],
)
def test_csrf_blocks_login_refresh_logout_before_mutating_session(
    browser_client, db_session, path, headers
):
    logged_in = login(browser_client)
    original = response_cookie(logged_in).value
    browser_client.headers.clear()
    response = browser_client.post(
        path, json=CREDS if path.endswith("login") else {}, headers=headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF validation failed"
    assert "set-cookie" not in response.headers
    token = (
        db_session.query(RefreshToken).filter_by(token_hash=hash_token(original)).one()
    )
    assert token.revoked_at is None
    assert token.replaced_by_token_id is None


def test_csrf_rejects_duplicate_origin(browser_client):
    response = browser_client.post(
        "/auth/login",
        json=CREDS,
        headers=[
            ("Origin", "https://app.example.com"),
            ("Origin", "https://evil.example"),
        ],
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "path", ["/auth/token/login", "/auth/token/refresh", "/auth/token/logout"]
)
def test_json_flow_disabled_by_default(auth_client, monkeypatch, path):
    monkeypatch.setattr(settings, "auth_json_tokens_enabled", False)
    assert (
        auth_client.post(
            path, json=CREDS if path.endswith("login") else {"refresh_token": "x" * 43}
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://app.example.com"},
        {"Sec-Fetch-Site": "same-origin"},
        {"Cookie": "anything=value"},
    ],
)
def test_json_flow_cannot_be_used_as_browser_fallback(auth_client, headers):
    assert (
        auth_client.post("/auth/token/login", json=CREDS, headers=headers).status_code
        == 403
    )


def test_local_cookie_can_use_http_and_auth_path(browser_client, monkeypatch):
    monkeypatch.setattr(settings, "auth_refresh_cookie_secure", False)
    monkeypatch.setattr(settings, "auth_refresh_cookie_name", "local_refresh")
    monkeypatch.setattr(settings, "auth_refresh_cookie_path", "/auth")
    monkeypatch.setattr(settings, "auth_csrf_trusted_origins", "http://localhost:5173")
    local = TestClient(
        app,
        base_url="http://localhost:8000",
        headers={"Origin": "http://localhost:5173", "X-CSRF-Protection": "1"},
    )
    try:
        cookie = response_cookie(login(local))
        assert cookie["httponly"] and not cookie["secure"]
        assert cookie["path"] == "/auth"
        refreshed = local.post("/auth/refresh")
        assert refreshed.status_code == 200
        response = local.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"},
        )
        assert response.status_code == 204
        assert response_cookie(response)["path"] == "/auth"
        assert not local.cookies
    finally:
        local.close()


def test_reset_revokes_browser_access_and_refresh_cookie(browser_client, db_session):
    from app.repositories.password_reset_repository import PasswordResetRepository
    from app.repositories.user_repository import UserRepository
    from app.services.password_reset_service import PasswordResetService
    from app.services.reset_email_service import ResetEmailService

    logged_in = login(browser_client)
    access = logged_in.json()["access_token"]
    email = Mock(spec=ResetEmailService)
    service = PasswordResetService(
        UserRepository(db_session), PasswordResetRepository(db_session), email
    )
    service.send_reset(CREDS["email"])
    raw = email.send_reset.call_args.args[1]
    assert (
        browser_client.post(
            "/auth/reset-password",
            json={"token": raw, "new_password": "new-password-123"},
        ).status_code
        == 204
    )
    assert (
        browser_client.get(
            "/auth/me", headers={"Authorization": f"Bearer {access}"}
        ).status_code
        == 401
    )
    response = browser_client.post("/auth/refresh")
    assert response.status_code == 401
    assert response_cookie(response)["max-age"] == "0"


def test_json_client_returns_pair_without_cookie(auth_client):
    assert auth_client.post("/auth/register", json=CREDS).status_code == 201
    response = auth_client.post("/auth/token/login", json=CREDS)
    assert response.status_code == 200
    assert "set-cookie" not in response.headers
    assert set(response.json()) == {"access_token", "refresh_token", "token_type"}


def test_failed_browser_login_never_sets_cookie(browser_client):
    assert browser_client.post("/auth/register", json=CREDS).status_code == 201
    response = browser_client.post(
        "/auth/login", json={**CREDS, "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


def test_redis_outage_returns_503_without_losing_refresh_cookie(browser_client):
    logged_in = login(browser_client)
    original = response_cookie(logged_in).value
    store = Mock(spec=TokenStore)
    store.is_revoked.return_value = False
    store.revoke_access.side_effect = TokenStoreUnavailable()
    app.dependency_overrides[get_token_store] = lambda: store
    response = browser_client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {logged_in.json()['access_token']}"},
    )
    assert response.status_code == 503
    assert "set-cookie" not in response.headers
    assert browser_client.cookies.get(settings.auth_refresh_cookie_name) == original


def test_cors_credentials_preflight_uses_explicit_origins_and_csrf_header():
    cors_app = FastAPI()
    configure_cors(
        cors_app,
        settings.model_copy(update={"backend_cors_origins": "https://app.example.com"}),
    )
    client = TestClient(cors_app)
    headers = {
        "Origin": "https://app.example.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-csrf-protection",
    }
    good = client.options("/auth/refresh", headers=headers)
    assert good.status_code == 200
    assert good.headers["access-control-allow-origin"] == "https://app.example.com"
    assert good.headers["access-control-allow-credentials"] == "true"
    bad = client.options(
        "/auth/refresh", headers={**headers, "Origin": "https://evil.example"}
    )
    assert bad.status_code == 400
    assert "access-control-allow-origin" not in bad.headers
