from datetime import datetime, timedelta, timezone
import logging
import uuid

from app.core.config import settings
from app.core.logging import log_event
from app.core.security import (
    create_access_token, create_opaque_token, hash_token, hash_password, verify_password,
)
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.models.user import User
from app.schemas.user import TokenResponse
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        refresh_token_repository: RefreshTokenRepository,
    ):
        self.user_repository = user_repository
        self.refresh_token_repository = refresh_token_repository

    def register_user(self, email: str, password: str) -> User:
        existing_user = self.user_repository.get_user_by_email(email=email)

        if existing_user is not None:
            raise ValueError("Email already registered")

        hashed_password = hash_password(password)

        return self.user_repository.create_user(
            email=email,
            hashed_password=hashed_password,
        )

    def login_user(self, email: str, password: str) -> TokenResponse:
        user = self.user_repository.get_user_by_email(email=email)

        if user is None or not user.is_active:
            raise ValueError("Invalid email or password")

        password_is_valid = verify_password(password, user.hashed_password)

        if password_is_valid is False:
            raise ValueError("Invalid email or password")

        refresh_token = create_opaque_token()
        self.refresh_token_repository.create_refresh_token(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(
                days=settings.refresh_token_expire_days,
            ),
        )
        return TokenResponse(
            access_token=create_access_token(subject=str(user.id)),
            refresh_token=refresh_token,
        )

    def refresh(self, raw_token: str) -> TokenResponse:
        digest = hash_token(raw_token)
        token = self.refresh_token_repository.get_by_token_hash(digest)
        if token is None:
            raise ValueError("Invalid or expired refresh token")

        # Lock the user first: rotation, logout and password reset share this order.
        user = self.user_repository.get_user_for_update(token.user_id)
        token = self.refresh_token_repository.get_for_update(digest)
        now = datetime.now(timezone.utc)
        if user is None or not user.is_active or token is None:
            raise ValueError("Invalid or expired refresh token")
        if token.revoked_at is not None:
            # Conservative replay response: revoke all of this user's refresh sessions.
            self.refresh_token_repository.revoke_all_for_user(user.id, now)
            log_event(logger, logging.WARNING, "auth.refresh.replay_detected", user_id=str(user.id))
            raise ValueError("Invalid or expired refresh token")
        if token.expires_at <= now:
            raise ValueError("Invalid or expired refresh token")

        replacement = create_opaque_token()
        self.refresh_token_repository.rotate(token, hash_token(replacement), now)
        return TokenResponse(
            access_token=create_access_token(str(user.id)),
            refresh_token=replacement,
        )

    def logout(self, user_id: uuid.UUID, raw_token: str) -> None:
        self.user_repository.get_user_for_update(user_id)
        token = self.refresh_token_repository.get_for_update(hash_token(raw_token))
        if token is None or token.user_id != user_id:
            raise ValueError("Invalid refresh token")
        if token.revoked_at is None:
            self.refresh_token_repository.revoke_refresh_token(
                token, datetime.now(timezone.utc),
            )
