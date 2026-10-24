from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.dependencies import get_current_user, get_token_store
from app.core.rate_limits import limit_login, limit_registration, limit_questions, limit_uploads
from app.services.token_store import TokenStore, TokenStoreUnavailable


@pytest.mark.parametrize("limiter,setting,window", [
    (limit_login, "login_requests_per_minute", 60),
    (limit_registration, "register_requests_per_hour", 3600),
    (limit_questions, "question_requests_per_minute", 60),
    (limit_uploads, "upload_requests_per_hour", 3600),
])
def test_rate_limits_reject_before_side_effects(limiter, setting, window, monkeypatch):
    application = FastAPI()
    work = Mock()
    counters = {}
    store = Mock(spec=TokenStore)

    def allow(key, limit, duration):
        assert duration == window
        counters[key] = counters.get(key, 0) + 1
        return counters[key] <= limit

    store.allow_request.side_effect = allow
    user = SimpleNamespace(id=uuid4())
    application.dependency_overrides[get_token_store] = lambda: store
    application.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(settings, setting, 1)

    @application.post("/work", dependencies=[Depends(limiter)])
    def endpoint():
        work()
        return {"ok": True}

    client = TestClient(application)
    assert client.post("/work").status_code == 200
    response = client.post("/work", headers={"X-Forwarded-For": "spoofed-ip"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == str(window)
    work.assert_called_once()
    if limiter in (limit_questions, limit_uploads):
        user.id = uuid4()
        assert client.post("/work").status_code == 200


def test_rate_limit_fails_closed_when_redis_unavailable():
    application = FastAPI()
    store = Mock(spec=TokenStore)
    store.allow_request.side_effect = TokenStoreUnavailable()
    application.dependency_overrides[get_token_store] = lambda: store

    from app.main import token_store_unavailable_handler
    application.add_exception_handler(TokenStoreUnavailable, token_store_unavailable_handler)

    @application.post("/login", dependencies=[Depends(limit_login)])
    def endpoint():
        pytest.fail("Must not authenticate without rate limit storage")

    assert TestClient(application).post("/login").status_code == 503


@pytest.mark.parametrize("path,limiter", [
    ("/auth/login", limit_login),
    ("/auth/token/login", limit_login),
    ("/auth/register", limit_registration),
    ("/chats/{id}/questions", limit_questions),
    ("/chats/{id}/questions/stream", limit_questions),
    ("/documents/upload", limit_uploads),
    ("/documents/{id}/retry", limit_uploads),
])
def test_production_routes_enforce_limits(path, limiter, monkeypatch):
    from app.main import app
    from app.core.dependencies import get_auth_service, get_chat_service, get_document_service

    app.dependency_overrides.pop(limiter)
    store = Mock(spec=TokenStore)
    store.allow_request.return_value = False
    service = Mock()
    app.dependency_overrides[get_token_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    for dependency in (get_auth_service, get_chat_service, get_document_service):
        app.dependency_overrides[dependency] = lambda: service
    monkeypatch.setattr(settings, "auth_json_tokens_enabled", True)
    monkeypatch.setattr(settings, "auth_csrf_trusted_origins", "https://app.example.com")
    headers = {} if path.startswith("/auth/token/") else {
        "Origin": "https://app.example.com", "X-CSRF-Protection": "1",
    }
    try:
        kwargs = {"json": {"email": "test@example.com", "password": "password123", "content": "Question?"}}
        if path == "/documents/upload":
            kwargs = {"files": {"file": ("test.pdf", b"%PDF-1.7", "application/pdf")}}
        response = TestClient(app).post(path.format(id=uuid4()), headers=headers, **kwargs)
        assert response.status_code == 429
        assert service.mock_calls == []
    finally:
        app.dependency_overrides.clear()
