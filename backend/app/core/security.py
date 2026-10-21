import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


@dataclass(frozen=True)
class AccessTokenPayload:
    subject: str
    jti: str
    issued_at: datetime
    expires_at: datetime


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def create_access_token(subject: str) -> str:
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(
        minutes=settings.access_token_expire_minutes,
    )

    payload = {
        "sub": subject,
        "jti": str(uuid.uuid4()),
        "iat": issued_at,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> AccessTokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except (TypeError, OverflowError) as error:
        raise ValueError("Invalid token claims") from error

    subject = payload.get("sub")
    jti = payload.get("jti")
    expires_at = payload.get("exp")
    issued_at = payload.get("iat")

    if not isinstance(subject, str) or not subject:
        raise ValueError("Token subject must be a string")

    if not isinstance(jti, str) or not jti:
        raise ValueError("Token jti must be a string")

    if type(expires_at) is not int:
        raise ValueError("Token expiration must be an integer timestamp")

    if type(issued_at) is not int:
        raise ValueError("Token issued-at must be an integer timestamp")
    if issued_at >= expires_at:
        raise ValueError("Token expiration must be after issued-at")

    try:
        return AccessTokenPayload(
            subject=subject,
            jti=jti,
            issued_at=datetime.fromtimestamp(issued_at, tz=timezone.utc),
            expires_at=datetime.fromtimestamp(expires_at, tz=timezone.utc),
        )
    except (OverflowError, OSError) as error:
        raise ValueError("Invalid token timestamps") from error
