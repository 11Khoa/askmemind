import pytest
import uuid
from unittest.mock import Mock

from app.repositories.chat_repository import ChatRepository
from app.repositories.user_repository import UserRepository
from app.services.chat_service import ChatService


def test_create_chat_when_user_exists() -> None:
    user_id = uuid.uuid4()
    expected_chat = Mock()

    chat_repository = Mock(spec=ChatRepository)
    user_repository = Mock(spec=UserRepository)

    user_repository.get_user_by_id.return_value = Mock()
    chat_repository.create_chat.return_value = expected_chat

    service = ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
    )

    result = service.create_chat(
        user_id=user_id,
        title="Test chat",
    )

    assert result is expected_chat
    user_repository.get_user_by_id.assert_called_once_with(user_id)
    chat_repository.create_chat.assert_called_once_with(
        user_id=user_id,
        title="Test chat",
    )


def test_create_chat_when_user_not_found() -> None:
    user_id = uuid.uuid4()

    chat_repository = Mock(spec=ChatRepository)
    user_repository = Mock(spec=UserRepository)

    user_repository.get_user_by_id.return_value = None

    service = ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
    )

    with pytest.raises(ValueError, match="User not found"):
        service.create_chat(
            user_id=user_id,
            title="Test chat",
        )

    user_repository.get_user_by_id.assert_called_once_with(user_id)
    chat_repository.create_chat.assert_not_called()


def test_get_user_chat_returns_chat_for_owner() -> None:
    user_id = uuid.uuid4()
    chat_id = uuid.uuid4()

    chat = Mock()
    chat_repository = Mock(spec=ChatRepository)
    user_repository = Mock(spec=UserRepository)

    chat.id = chat_id
    chat.user_id = user_id
    chat_repository.get_chat_by_id.return_value = chat

    service = ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
    )

    result = service.get_user_chat(
        user_id=user_id,
        chat_id=chat_id,
    )

    assert result is chat
    chat_repository.get_chat_by_id.assert_called_once_with(chat_id=chat_id)


def test_get_user_chat_raises_when_chat_not_found() -> None:
    user_id = uuid.uuid4()
    chat_id = uuid.uuid4()

    chat_repository = Mock(spec=ChatRepository)
    user_repository = Mock(spec=UserRepository)

    chat_repository.get_chat_by_id.return_value = None

    service = ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
    )

    with pytest.raises(ValueError, match="Chat not found"):
        service.get_user_chat(
            user_id=user_id,
            chat_id=chat_id,
        )

    chat_repository.get_chat_by_id.assert_called_once_with(chat_id=chat_id)


def test_get_user_chat_raises_when_user_is_not_owner() -> None:
    user_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    chat_id = uuid.uuid4()

    chat = Mock()
    chat.id = chat_id
    chat.user_id = owner_id

    chat_repository = Mock(spec=ChatRepository)
    user_repository = Mock(spec=UserRepository)
    chat_repository.get_chat_by_id.return_value = chat

    service = ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
    )

    with pytest.raises(
        PermissionError,
        match="You don't have access to this chat",
    ):
        service.get_user_chat(
            user_id=user_id,
            chat_id=chat_id,
        )

    chat_repository.get_chat_by_id.assert_called_once_with(chat_id=chat_id)
