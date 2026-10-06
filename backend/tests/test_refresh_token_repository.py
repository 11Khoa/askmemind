from datetime import datetime, timedelta, timezone

from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository


def test_create_refresh_token(db_session):
    user_repository = UserRepository(db=db_session)
    user = user_repository.create_user(
        email="token@example.com",
        hashed_password="hashed",
    )

    repository = RefreshTokenRepository(db=db_session)
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    token = repository.create_refresh_token(
        user_id=user.id,
        token_hash="a" * 64,
        expires_at=expires_at,
    )

    assert token.id is not None
    assert token.user_id == user.id
    assert token.token_hash == "a" * 64
    assert token.revoked_at is None


def test_get_by_token_hash(db_session):
    user_repository = UserRepository(db=db_session)
    user = user_repository.create_user(
        email="find-token@example.com",
        hashed_password="hashed",
    )

    repository = RefreshTokenRepository(db=db_session)
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    created = repository.create_refresh_token(
        user_id=user.id,
        token_hash="b" * 64,
        expires_at=expires_at,
    )

    found = repository.get_by_token_hash("b" * 64)

    assert found is not None
    assert found.id == created.id


def test_revoke_refresh_token(db_session):
    user_repository = UserRepository(db=db_session)
    user = user_repository.create_user(
        email="revoke-token@example.com",
        hashed_password="hashed",
    )

    repository = RefreshTokenRepository(db=db_session)
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    token = repository.create_refresh_token(
        user_id=user.id,
        token_hash="c" * 64,
        expires_at=expires_at,
    )

    revoked_at = datetime.now(timezone.utc)
    revoked = repository.revoke_refresh_token(
        refresh_token=token,
        revoked_at=revoked_at,
    )

    assert revoked.revoked_at is not None
