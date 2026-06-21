from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import TokenResponse
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

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

        if user is None:
            raise ValueError("Invalid email or password")

        password_is_valid = verify_password(password, user.hashed_password)

        if password_is_valid is False:
            raise ValueError("Invalid email or password")

        token = create_access_token(subject=str(user.id))
        return TokenResponse(access_token=token)
