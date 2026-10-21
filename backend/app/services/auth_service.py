from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.security import (
    create_access_token, create_opaque_token, hash_token, hash_password, verify_password,
)
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.models.user import User
from app.schemas.user import TokenResponse
from app.repositories.user_repository import UserRepository


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
