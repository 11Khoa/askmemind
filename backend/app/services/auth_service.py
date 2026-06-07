from app.core.security import hash_password
from app.models.user import User
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
