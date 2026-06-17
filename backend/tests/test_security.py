from datetime import datetime, timedelta, timezone
import uuid

import jwt
import pytest

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token


def test_create_access_token_can_be_decoded() -> None:
    user_id = uuid.uuid4()
    subject = str(user_id)

    token = create_access_token(subject=subject)
    decoded_subject = decode_access_token(token=token)

    assert decoded_subject == subject


def test_decode_access_token_rejects_expired_token() -> None:
    user_id = uuid.uuid4()
    subject = str(user_id)

    expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    payload = {
        "sub": subject,
        "exp": expires_at,
    }
    token = jwt.encode(
        payload,
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token=token)


def test_decode_access_token_rejects_invalid_signature() -> None:
    user_id = uuid.uuid4()
    subject = str(user_id)

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes,
    )

    payload = {
        "sub": subject,
        "exp": expires_at,
    }

    token = jwt.encode(
        payload,
        settings.secret_key + "123",
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token=token)


def test_decode_access_token_rejects_missing_subject() -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes,
    )

    payload = {
        "exp": expires_at,
    }

    token = jwt.encode(
        payload,
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(ValueError, match="Token subject must be a string"):
        decode_access_token(token=token)
