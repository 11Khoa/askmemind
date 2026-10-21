from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from pydantic import AnyHttpUrl

import pytest

from app.core.config import settings
from app.core.dependencies import get_token_store
from app.core.security import hash_token
from app.main import app
from app.models.password_reset_token import PasswordResetToken
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.user_repository import UserRepository
from app.services.password_reset_service import PasswordResetService
from app.services.reset_email_service import ResetEmailService
from app.services.token_store import TokenStore
from app.tasks.password_reset import send_password_reset


@pytest.fixture
def reset_service(db_session):
    email = Mock(spec=ResetEmailService)
    return PasswordResetService(
        UserRepository(db_session), PasswordResetRepository(db_session), email
    )


def issue(service):
    service.send_reset("reset@example.com")
    return service.email.send_reset.call_args.args[1]


def test_reset_changes_password_and_revokes_all_sessions(
    auth_client, auth_tokens, reset_service, db_session
):
    second_device = auth_client.post(
        "/auth/token/login",
        json={"email": "reset@example.com", "password": "old-password-123"},
    ).json()
    raw = issue(reset_service)
    stored = (
        db_session.query(PasswordResetToken).filter_by(token_hash=hash_token(raw)).one()
    )
    assert stored.token_hash != raw
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
    assert auth_client.get("/auth/me", headers=headers).status_code == 200
    response = auth_client.post(
        "/auth/reset-password", json={"token": raw, "new_password": "new-password-123"}
    )
    assert response.status_code == 204
    assert response.headers["cache-control"] == "no-store"
    assert auth_client.get("/auth/me", headers=headers).status_code == 401
    assert (
        auth_client.post(
            "/auth/token/refresh", json={"refresh_token": auth_tokens["refresh_token"]}
        ).status_code
        == 401
    )
    assert (
        auth_client.post(
            "/auth/token/refresh", json={"refresh_token": second_device["refresh_token"]}
        ).status_code
        == 401
    )
    assert (
        auth_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {second_device['access_token']}"},
        ).status_code
        == 401
    )
    db_session.refresh(stored)
    assert stored.consumed_at is not None
    for password, expected in [("old-password-123", 401), ("new-password-123", 200)]:
        result = auth_client.post(
            "/auth/token/login", json={"email": "reset@example.com", "password": password}
        )
        assert result.status_code == expected
        if expected == 200:
            assert (
                auth_client.get(
                    "/auth/me",
                    headers={
                        "Authorization": f"Bearer {result.json()['access_token']}"
                    },
                ).status_code
                == 200
            )
    assert (
        auth_client.post(
            "/auth/reset-password",
            json={"token": raw, "new_password": "another-password"},
        ).status_code
        == 400
    )


def test_reset_rejects_expired_unknown_and_weak_password(
    auth_client, auth_tokens, reset_service, db_session
):
    raw = issue(reset_service)
    assert (
        auth_client.post(
            "/auth/reset-password", json={"token": raw, "new_password": "weak"}
        ).status_code
        == 422
    )
    stored = (
        db_session.query(PasswordResetToken).filter_by(token_hash=hash_token(raw)).one()
    )
    stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    for token in [raw, "x" * 43]:
        assert (
            auth_client.post(
                "/auth/reset-password",
                json={"token": token, "new_password": "new-password-123"},
            ).status_code
            == 400
        )


def test_new_reset_link_invalidates_previous_link(
    auth_client, auth_tokens, reset_service
):
    first, second = issue(reset_service), issue(reset_service)
    assert first != second
    for token, expected in [(first, 400), (second, 204)]:
        assert (
            auth_client.post(
                "/auth/reset-password",
                json={"token": token, "new_password": "new-password-123"},
            ).status_code
            == expected
        )


def test_unknown_email_does_not_send_mail(reset_service):
    reset_service.send_reset("missing@example.com")
    reset_service.email.send_reset.assert_not_called()


def test_forgot_password_queues_same_response_for_existing_and_unknown(
    auth_client, auth_tokens, monkeypatch
):
    monkeypatch.setattr(ResetEmailService, "is_configured", lambda self: True)
    queue = Mock()
    monkeypatch.setattr(send_password_reset, "apply_async", queue)
    responses = [
        auth_client.post("/auth/forgot-password", json={"email": email})
        for email in [" RESET@example.com ", "missing@example.com"]
    ]
    assert [response.status_code for response in responses] == [202, 202]
    assert responses[0].json() == responses[1].json()
    assert queue.call_count == 2
    assert queue.call_args_list[0].kwargs["kwargs"]["email"] == "reset@example.com"
    assert "token" not in str(responses[0].json())


def test_forgot_password_handles_queue_failure(auth_client, monkeypatch, caplog):
    monkeypatch.setattr(ResetEmailService, "is_configured", lambda self: True)
    monkeypatch.setattr(
        send_password_reset,
        "apply_async",
        Mock(side_effect=RuntimeError("broker offline: private-broker-password")),
    )
    response = auth_client.post(
        "/auth/forgot-password",
        json={"email": "missing@example.com"},
        headers={"X-Request-ID": "reset-queue-diagnostic"},
    )
    assert response.status_code == 503
    assert "broker offline" not in response.text
    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "auth.password_reset.enqueue_failed"
    )
    assert record.event_data["request_id"] == "reset-queue-diagnostic"
    assert record.event_data["error_type"] == "RuntimeError"
    assert "private-broker-password" not in caplog.text
    assert record.exc_info is None


def test_reset_rate_limit_returns_429(auth_client):
    store = Mock(spec=TokenStore)
    store.allow_request.return_value = False
    app.dependency_overrides[get_token_store] = lambda: store
    assert (
        auth_client.post(
            "/auth/reset-password",
            json={"token": "x" * 43, "new_password": "password123"},
        ).status_code
        == 429
    )


def test_email_limit_does_not_reveal_account_existence(auth_client, monkeypatch):
    monkeypatch.setattr(ResetEmailService, "is_configured", lambda self: True)
    queue = Mock()
    monkeypatch.setattr(send_password_reset, "apply_async", queue)
    store = Mock(spec=TokenStore)
    store.allow_request.side_effect = [True, False]
    app.dependency_overrides[get_token_store] = lambda: store
    assert (
        auth_client.post(
            "/auth/forgot-password", json={"email": "missing@example.com"}
        ).status_code
        == 202
    )
    queue.assert_not_called()


def test_unconfigured_recovery_returns_503(auth_client, monkeypatch, caplog):
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "smtp_from_email", "")
    monkeypatch.setattr(settings, "password_reset_url", None)
    monkeypatch.setattr(ResetEmailService, "is_configured", lambda self: False)
    assert (
        auth_client.post(
            "/auth/forgot-password", json={"email": "missing@example.com"}
        ).status_code
        == 503
    )
    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "auth.password_reset.unconfigured"
    )
    assert record.event_data["smtp_host_configured"] is False
    assert record.event_data["smtp_sender_configured"] is False
    assert record.event_data["reset_url_configured"] is False


def test_failed_password_reset_rolls_back_all_changes(
    auth_client, auth_tokens, reset_service, db_session, monkeypatch
):
    from app.models.refresh_token import RefreshToken
    from app.models.user import User

    raw = issue(reset_service)
    token_id = (
        db_session.query(PasswordResetToken)
        .filter_by(token_hash=hash_token(raw))
        .one()
        .id
    )
    user_id = db_session.query(User).filter_by(email="reset@example.com").one().id
    with monkeypatch.context() as patch:
        patch.setattr(
            db_session, "commit", Mock(side_effect=RuntimeError("commit failed"))
        )
        with pytest.raises(RuntimeError):
            reset_service.reset(raw, "new-password123")
    assert db_session.get(User, user_id).token_version == 0
    assert db_session.get(PasswordResetToken, token_id).consumed_at is None
    assert (
        db_session.query(RefreshToken).filter_by(user_id=user_id).one().revoked_at
        is None
    )


def test_email_uses_tls_and_fragment_token(monkeypatch):
    from app.services import reset_email_service as module

    config = settings.model_copy(
        update={
            "smtp_host": "smtp.example.com",
            "smtp_from_email": "auth@example.com",
            "password_reset_url": AnyHttpUrl("https://frontend.example/reset-password"),
        }
    )
    smtp = Mock()
    smtp.__enter__ = Mock(return_value=smtp)
    smtp.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(module.smtplib, "SMTP", Mock(return_value=smtp))
    ResetEmailService(config).send_reset("reset@example.com", "secret-token")
    smtp.starttls.assert_called_once()
    content = smtp.send_message.call_args.args[0].get_content()
    assert "https://frontend.example/reset-password#token=secret-token" in content


def test_worker_uses_own_session_and_closes_on_failure(monkeypatch):
    from celery.exceptions import Retry
    from app.tasks import password_reset as task_module

    db = Mock()
    monkeypatch.setattr(task_module, "SessionLocal", lambda: db)
    service = Mock()
    service.send_reset.side_effect = RuntimeError("sensitive SMTP content")
    monkeypatch.setattr(task_module, "PasswordResetService", Mock(return_value=service))
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(send_password_reset, "retry", retry)
    with pytest.raises(Retry):
        send_password_reset.run("reset@example.com", "request-id")
    db.rollback.assert_called_once()
    db.close.assert_called_once()
    assert str(retry.call_args.kwargs["exc"]) == "Reset email delivery failed"
