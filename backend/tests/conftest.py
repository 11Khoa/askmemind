from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.database import engine


@pytest.fixture
def auth_client(db_session, monkeypatch):
    from unittest.mock import Mock
    from fastapi.testclient import TestClient
    from app.core.dependencies import get_db, get_token_store
    from app.main import app
    from app.services.token_store import TokenStore
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_json_tokens_enabled", True)
    revoked = set()
    store = Mock(spec=TokenStore)
    store.is_revoked.side_effect = lambda jti: jti in revoked
    store.revoke_access.side_effect = lambda payload: revoked.add(payload.jti)
    store.allow_request.return_value = True
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_token_store] = lambda: store
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def auth_tokens(auth_client):
    credentials = {"email": "reset@example.com", "password": "old-password-123"}
    assert auth_client.post("/auth/register", json=credentials).status_code == 201
    return auth_client.post("/auth/token/login", json=credentials).json()


@pytest.fixture
def browser_client(auth_client, monkeypatch):
    from fastapi.testclient import TestClient
    from app.core.config import settings
    from app.main import app

    origin = "https://app.example.com"
    monkeypatch.setattr(settings, "auth_csrf_trusted_origins", origin)
    monkeypatch.setattr(settings, "auth_refresh_cookie_secure", True)
    monkeypatch.setattr(
        settings, "auth_refresh_cookie_name", "__Host-askmemind_refresh"
    )
    monkeypatch.setattr(settings, "auth_refresh_cookie_samesite", "lax")
    monkeypatch.setattr(settings, "auth_refresh_cookie_path", "/")
    client = TestClient(
        app,
        base_url="https://api.example.com",
        headers={"Origin": origin, "X-CSRF-Protection": "1"},
    )
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def db_session() -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()

    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session

    finally:
        session.close()
        transaction.rollback()
        connection.close()
