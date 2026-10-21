from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.dependencies import get_db
from app.core.security import hash_token
from app.main import app
from app.models.refresh_token import RefreshToken
from app.models.user import User


@pytest.fixture
def auth_client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def login(client):
    credentials = {"email": "lifecycle@example.com", "password": "test-password-123"}
    assert client.post("/auth/register", json=credentials).status_code == 201
    response = client.post("/auth/login", json=credentials)
    assert response.status_code == 200
    return response.json()


def test_rotation_and_replay_revoke_replacement(auth_client, db_session):
    first = login(auth_client)
    original = db_session.query(RefreshToken).filter_by(
        token_hash=hash_token(first["refresh_token"]),
    ).one()
    response = auth_client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert response.status_code == 200
    second = response.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert second["access_token"] != first["access_token"]
    db_session.refresh(original)
    assert original.revoked_at is not None
    replacement = db_session.get(RefreshToken, original.replaced_by_token_id)
    assert replacement.token_hash == hash_token(second["refresh_token"])
    assert replacement.expires_at == original.expires_at
    assert auth_client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    assert auth_client.post("/auth/refresh", json={"refresh_token": second["refresh_token"]}).status_code == 401


def test_refresh_rejects_expired_and_unknown_tokens(auth_client, db_session):
    tokens = login(auth_client)
    token = db_session.query(RefreshToken).filter_by(token_hash=hash_token(tokens["refresh_token"])).one()
    token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    for raw in [tokens["refresh_token"], "x" * 43]:
        assert auth_client.post("/auth/refresh", json={"refresh_token": raw}).status_code == 401


def test_disabled_user_cannot_login_refresh_or_authenticate(auth_client, db_session):
    tokens = login(auth_client)
    user = db_session.query(User).filter_by(email="lifecycle@example.com").one()
    user.is_active = False
    db_session.commit()
    assert auth_client.post("/auth/login", json={"email": user.email, "password": "test-password-123"}).status_code == 401
    assert auth_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert auth_client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}).status_code == 401


def test_logout_revokes_refresh_token(auth_client):
    tokens = login(auth_client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    body = {"refresh_token": tokens["refresh_token"]}
    assert auth_client.post("/auth/logout", headers=headers, json=body).status_code == 204
    assert auth_client.post("/auth/refresh", json=body).status_code == 401


def test_logout_cannot_revoke_another_users_token(auth_client):
    first = login(auth_client)
    other = {"email": "other@example.com", "password": "test-password-123"}
    assert auth_client.post("/auth/register", json=other).status_code == 201
    second = auth_client.post("/auth/login", json=other).json()
    response = auth_client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {first['access_token']}"},
        json={"refresh_token": second["refresh_token"]},
    )
    assert response.status_code == 401
    assert auth_client.post("/auth/refresh", json={"refresh_token": second["refresh_token"]}).status_code == 200
