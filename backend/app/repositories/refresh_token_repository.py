import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_refresh_token(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        refresh_token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        self.db.add(refresh_token)
        self.db.commit()
        self.db.refresh(refresh_token)

        return refresh_token

    def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        return (
            self.db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .first()
        )

    def get_for_update(self, token_hash: str) -> RefreshToken | None:
        return (
            self.db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .populate_existing().with_for_update().first()
        )

    def rotate(self, token: RefreshToken, token_hash: str, now: datetime) -> RefreshToken:
        # The caller holds the user lock, serializing rotation and revocation.
        try:
            replacement = RefreshToken(
                user_id=token.user_id,
                token_hash=token_hash,
                expires_at=token.expires_at,
            )
            self.db.add(replacement)
            self.db.flush()
            token.revoked_at = now
            token.replaced_by_token_id = replacement.id
            self.db.commit()
            return replacement
        except Exception:
            self.db.rollback()
            raise

    def revoke_all_for_user(self, user_id: uuid.UUID, now: datetime) -> None:
        self.db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        ).update({RefreshToken.revoked_at: now}, synchronize_session="fetch")
        self.db.commit()

    def revoke_refresh_token(
        self,
        refresh_token: RefreshToken,
        revoked_at: datetime,
        replaced_at_by_token_id: uuid.UUID | None = None,
    ) -> RefreshToken:
        refresh_token.revoked_at = revoked_at
        refresh_token.replaced_by_token_id = replaced_at_by_token_id
        self.db.commit()
        self.db.refresh(refresh_token)
        return refresh_token
