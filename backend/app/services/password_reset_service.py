import logging
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.logging import log_event
from app.core.security import create_opaque_token, hash_password, hash_token
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.user_repository import UserRepository
from app.services.reset_email_service import ResetEmailService

logger = logging.getLogger(__name__)


class PasswordResetService:
    def __init__(
        self,
        users: UserRepository,
        tokens: PasswordResetRepository,
        email: ResetEmailService,
    ):
        self.users = users
        self.tokens = tokens
        self.email = email

    def send_reset(self, email: str) -> None:
        user = self.users.get_user_by_email(email)
        if user is None:
            return
        user = self.users.get_user_for_update(user.id)
        if user is None or not user.is_active:
            return
        now = datetime.now(timezone.utc)
        raw = create_opaque_token()
        self.tokens.issue(
            user.id,
            hash_token(raw),
            now + timedelta(minutes=settings.password_reset_expire_minutes),
            now,
        )
        self.email.send_reset(user.email, raw)

    def reset(self, raw: str, new_password: str) -> None:
        digest = hash_token(raw)
        token = self.tokens.get_by_hash(digest)
        if token is None:
            raise ValueError("Invalid or expired password reset token")
        user = self.users.get_user_for_update(token.user_id)
        token = self.tokens.get_by_hash(digest, lock=True)
        now = datetime.now(timezone.utc)
        if (
            user is None
            or not user.is_active
            or token is None
            or token.consumed_at is not None
            or token.expires_at <= now
        ):
            raise ValueError("Invalid or expired password reset token")
        self.tokens.reset_password(user, hash_password(new_password), now)
        log_event(
            logger, logging.INFO, "auth.password_reset.completed", user_id=str(user.id)
        )
