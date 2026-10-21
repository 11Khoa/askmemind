import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.core.security import decode_access_token, hash_password, hash_token
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import TokenResponse
from app.services.auth_service import AuthService


def test_login_user_success_returns_token_response() -> None:
    user_id = uuid.uuid4()
    email = "test@gmail.com"
    password = "password1122"

    user = Mock()
    user.id = user_id
    user.token_version = 0
    user.hashed_password = hash_password(password)

    user_repository = Mock(spec=UserRepository)
    user_repository.get_user_by_email.return_value = user
    user_repository.get_user_for_update.return_value = user

    refresh_repository = Mock(spec=RefreshTokenRepository)
    service = AuthService(user_repository, refresh_repository)

    result = service.login_user(
        email=email,
        password=password,
    )

    assert isinstance(result, TokenResponse)
    assert result.token_type == "bearer"
    assert decode_access_token(result.access_token).subject == str(user_id)
    stored = refresh_repository.create_refresh_token.call_args.kwargs
    assert stored["user_id"] == user_id
    assert stored["token_hash"] == hash_token(result.refresh_token)
    assert stored["token_hash"] != result.refresh_token
    user_repository.get_user_by_email.assert_called_once_with(email=email)


def test_login_signs_before_refresh_commit_can_reload_account_version():
    user = Mock()
    user.id = uuid.uuid4()
    user.is_active = True
    user.token_version = 0
    user.hashed_password = hash_password("password123")
    users = Mock(spec=UserRepository)
    users.get_user_by_email.return_value = user
    users.get_user_for_update.return_value = user
    refresh = Mock(spec=RefreshTokenRepository)
    refresh.create_refresh_token.side_effect = lambda **kwargs: setattr(
        user, "token_version", 1
    )
    result = AuthService(users, refresh).login_user("test@example.com", "password123")
    assert decode_access_token(result.access_token).token_version == 0


def test_refresh_signs_before_rotation_commit_can_reload_account_version():
    user = Mock(id=uuid.uuid4(), is_active=True, token_version=0)
    users = Mock(spec=UserRepository)
    users.get_user_for_update.return_value = user
    token = Mock(
        user_id=user.id,
        revoked_at=None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    refresh = Mock(spec=RefreshTokenRepository)
    refresh.get_by_token_hash.return_value = token
    refresh.get_for_update.return_value = token
    refresh.rotate.side_effect = lambda *args: setattr(user, "token_version", 1)
    result = AuthService(users, refresh).refresh("x" * 43)
    assert decode_access_token(result.access_token).token_version == 0


def test_login_user_raises_when_user_not_found() -> None:
    user_repository = Mock(spec=UserRepository)
    user_repository.get_user_by_email.return_value = None

    service = AuthService(user_repository, Mock(spec=RefreshTokenRepository))

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
    user_repository.get_user_for_update.return_value = user

    service = AuthService(user_repository, Mock(spec=RefreshTokenRepository))

    with pytest.raises(ValueError, match="Invalid email or password"):
        service.login_user(
            email=email,
            password="wrong-password",
        )

    user_repository.get_user_by_email.assert_called_once_with(email=email)
