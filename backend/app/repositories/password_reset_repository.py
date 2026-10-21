import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User


class PasswordResetRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_hash(
        self, token_hash: str, *, lock: bool = False
    ) -> PasswordResetToken | None:
        query = self.db.query(PasswordResetToken).filter_by(token_hash=token_hash)
        if lock:
            query = query.populate_existing().with_for_update()
        return query.first()

    def issue(
        self, user_id: uuid.UUID, token_hash: str, expires_at: datetime, now: datetime
    ) -> None:
        try:
            self._consume_all(user_id, now)
            self.db.add(
                PasswordResetToken(
                    user_id=user_id, token_hash=token_hash, expires_at=expires_at
                )
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _consume_all(self, user_id: uuid.UUID, now: datetime) -> None:
        self.db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.consumed_at.is_(None),
        ).update({PasswordResetToken.consumed_at: now}, synchronize_session="fetch")

    def reset_password(self, user: User, hashed_password: str, now: datetime) -> None:
        # Caller holds the user and reset-token locks; all changes commit together.
        try:
            user.hashed_password = hashed_password
            user.token_version += 1
            self._consume_all(user.id, now)
            self.db.query(RefreshToken).filter(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
            ).update({RefreshToken.revoked_at: now}, synchronize_session="fetch")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
