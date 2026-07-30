import uuid

from app.repositories.user_repository import UserRepository


def test_create_user_persists_user(db_session) -> None:
    repository = UserRepository(db=db_session)

    user = repository.create_user(
        email="repo-user@example.com",
        hashed_password="hashed-password",
    )

    assert user.id is not None
    assert user.email == "repo-user@example.com"
    assert user.hashed_password == "hashed-password"
    assert user.is_active is True
    assert user.created_at is not None
    assert user.updated_at is not None


def test_get_user_by_email_returns_user(db_session) -> None:
    repository = UserRepository(db=db_session)

    created_user = repository.create_user(
        email="find-email@example.com",
        hashed_password="hashed-password",
    )

    result = repository.get_user_by_email(
        email="find-email@example.com",
    )

    assert result is not None
    assert result.id == created_user.id
    assert result.email == "find-email@example.com"


def test_get_user_by_email_returns_none_when_missing(db_session) -> None:
    repository = UserRepository(db=db_session)

    result = repository.get_user_by_email(
        email="missing@example.com",
    )

    assert result is None


def test_get_user_by_id_returns_user(db_session) -> None:
    repository = UserRepository(db=db_session)

    created_user = repository.create_user(
        email="find-id@example.com",
        hashed_password="hashed-password",
    )

    result = repository.get_user_by_id(user_id=created_user.id)

    assert result is not None
    assert result.id == created_user.id
    assert result.email == "find-id@example.com"


def test_get_user_by_id_returns_none_when_missing(db_session) -> None:
    repository = UserRepository(db=db_session)

    result = repository.get_user_by_id(user_id=uuid.uuid4())

    assert result is None
