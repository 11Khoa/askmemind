import uuid
from unittest.mock import Mock

import pytest

from app.core.security import decode_access_token, hash_password
from app.repositories.user_repository import UserRepository
from app.schemas.user import TokenResponse
from app.services.auth_service import AuthService


def test_login_user_success_returns_token_response() -> None:
    user_id = uuid.uuid4()
    email = "test@gmail.com"
    password = "password1122"

    user = Mock()
    user.id = user_id
    user.hashed_password = hash_password(password)

    user_repository = Mock(spec=UserRepository)
    user_repository.get_user_by_email.return_value = user

    service = AuthService(user_repository=user_repository)

    result = service.login_user(
        email=email,
        password=password,
    )

    assert isinstance(result, TokenResponse)
    assert result.token_type == "bearer"
    assert decode_access_token(result.access_token) == str(user_id)
    user_repository.get_user_by_email.assert_called_once_with(email=email)


def test_login_user_raises_when_user_not_found() -> None:
    user_repository = Mock(spec=UserRepository)
    user_repository.get_user_by_email.return_value = None

    service = AuthService(user_repository=user_repository)

    with pytest.raises(ValueError, match="Invalid email or password"):
        service.login_user(
            email="missing@gmail.com",
            password="password123",
        )

    user_repository.get_user_by_email.assert_called_once_with(
        email="missing@gmail.com",
    )


def test_login_user_raises_when_password_is_invalid() -> None:
    email = "test@gmail.com"

    user = Mock()
    user.id = uuid.uuid4()
    user.hashed_password = hash_password("correct-password")

    user_repository = Mock(spec=UserRepository)
    user_repository.get_user_by_email.return_value = user

    service = AuthService(user_repository=user_repository)

    with pytest.raises(ValueError, match="Invalid email or password"):
        service.login_user(
            email=email,
            password="wrong-password",
        )

    user_repository.get_user_by_email.assert_called_once_with(email=email)
