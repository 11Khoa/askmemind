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
