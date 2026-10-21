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
    decoded_payload = decode_access_token(token=token)

    assert decoded_payload.subject == subject


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


def test_create_access_token_includes_jti_and_iat() -> None:
    user_id = uuid.uuid4()
    subject = str(user_id)

    token = create_access_token(subject)

    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    assert payload["sub"] == subject
    assert isinstance(payload["jti"], str)
    assert isinstance(payload["iat"], int)
    assert isinstance(payload["exp"], int)


def test_decode_access_token_returns_payload() -> None:
    user_id = uuid.uuid4()
    subject = str(user_id)
    token = create_access_token(subject)

    payload = decode_access_token(token)

    assert payload.subject == subject
    assert payload.jti
    assert payload.expires_at.tzinfo is not None


def test_decode_access_token_requires_jti() -> None:
    token = jwt.encode(
        {
            "sub": "user-id",
            "exp": 9999999999,
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(ValueError, match="Token jti must be a string"):
        decode_access_token(token)


@pytest.mark.parametrize(
    "claim,value",
    [("sub", ""), ("jti", ""), ("iat", None), ("iat", "123"),
     ("iat", True), ("exp", True), ("exp", 9999999999.5)],
)
def test_decode_rejects_invalid_claim_types(claim, value):
    payload = {"sub": str(uuid.uuid4()), "jti": str(uuid.uuid4()),
               "iat": 1, "exp": 9999999999}
    payload[claim] = value
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises((ValueError, jwt.PyJWTError)):
        decode_access_token(token)


def test_access_tokens_have_distinct_jtis():
    subject = str(uuid.uuid4())
    first = decode_access_token(create_access_token(subject))
    second = decode_access_token(create_access_token(subject))
    assert first.jti != second.jti
    assert first.issued_at < first.expires_at
