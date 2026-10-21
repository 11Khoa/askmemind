from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.security import create_opaque_token, hash_password, hash_token
from app.database import engine
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.password_reset_service import PasswordResetService
from app.services.reset_email_service import ResetEmailService
from unittest.mock import Mock


def test_concurrent_refresh_only_rotates_once_and_replay_revokes_successor():
    user_id, raw = uuid4(), create_opaque_token()
    with Session(engine) as db:
        db.add(
            User(
                id=user_id,
                email=f"{user_id}@example.com",
                hashed_password=hash_password("password123"),
            )
        )
        db.commit()
        RefreshTokenRepository(db).create_refresh_token(
            user_id, hash_token(raw), datetime.now(timezone.utc) + timedelta(days=1)
        )
    barrier = Barrier(2)

    def refresh():
        with Session(engine) as db:
            service = AuthService(UserRepository(db), RefreshTokenRepository(db))
            barrier.wait(timeout=10)
            try:
                return service.refresh(raw)
            except ValueError:
                return None

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: refresh(), range(2)))
        assert sum(result is not None for result in results) == 1
        with Session(engine) as db:
            tokens = db.query(RefreshToken).filter_by(user_id=user_id).all()
            assert len(tokens) == 2
            assert all(token.revoked_at is not None for token in tokens)
    finally:
        with Session(engine) as db:
            db.execute(delete(User).where(User.id == user_id))
            db.commit()


def test_concurrent_reset_consumes_token_once():
    user_id, raw = uuid4(), create_opaque_token()
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add(
            User(
                id=user_id,
                email=f"{user_id}@example.com",
                hashed_password=hash_password("password123"),
            )
        )
        db.commit()
        PasswordResetRepository(db).issue(
            user_id, hash_token(raw), now + timedelta(minutes=15), now
        )
    barrier = Barrier(2)

    def reset():
        with Session(engine) as db:
            service = PasswordResetService(
                UserRepository(db),
                PasswordResetRepository(db),
                Mock(spec=ResetEmailService),
            )
            barrier.wait(timeout=10)
            try:
                service.reset(raw, "new-password123")
                return True
            except ValueError:
                return False

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: reset(), range(2)))
        assert results.count(True) == 1
        with Session(engine) as db:
            assert db.get(User, user_id).token_version == 1
    finally:
        with Session(engine) as db:
            db.execute(delete(User).where(User.id == user_id))
            db.commit()
