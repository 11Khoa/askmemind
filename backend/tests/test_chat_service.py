import uuid
from unittest.mock import Mock

import pytest

from app.repositories.chat_repository import ChatRepository
from app.repositories.user_repository import UserRepository
from app.services.chat_service import ChatService
from app.services.rag_service import RagAnswer
from app.services.context_builder_service import ContextCitation
from app.routers.chat import router as chat_router
from app.schemas.chat import ChatMessageRead


def test_create_chat_when_user_exists() -> None:
    user_id = uuid.uuid4()
    expected_chat = Mock()

    chat_repository = Mock(spec=ChatRepository)
    user_repository = Mock(spec=UserRepository)
    rag_service = Mock()

    user_repository.get_user_by_id.return_value = Mock()
    chat_repository.create_chat.return_value = expected_chat

    service = ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
        rag_service=rag_service,
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
    rag_service = Mock()

    user_repository.get_user_by_id.return_value = None

    service = ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
        rag_service=rag_service,
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
    rag_service = Mock()

    chat.id = chat_id
    chat.user_id = user_id
    chat_repository.get_chat_by_id.return_value = chat

    service = ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
        rag_service=rag_service,
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
    rag_service = Mock()

    chat_repository.get_chat_by_id.return_value = None

    service = ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
        rag_service=rag_service,
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

    rag_service = Mock()

    service = ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
        rag_service=rag_service,
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


def test_list_user_chats_when_user_exists() -> None:
    user_id = uuid.uuid4()
    expected_chats = [Mock(), Mock()]

    chat_repository = Mock(spec=ChatRepository)
    user_repository = Mock(spec=UserRepository)
    rag_service = Mock()

    user_repository.get_user_by_id.return_value = Mock()
    chat_repository.list_chats_by_user.return_value = expected_chats

    service = ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
        rag_service=rag_service,
    )

    result = service.list_user_chats(
        user_id=user_id,
    )

    assert result is expected_chats
    user_repository.get_user_by_id.assert_called_once_with(user_id)
    chat_repository.list_chats_by_user.assert_called_once_with(
        user_id=user_id,
    )


def test_list_user_chats_when_user_not_found() -> None:
    user_id = uuid.uuid4()

    chat_repository = Mock(spec=ChatRepository)
    user_repository = Mock(spec=UserRepository)

    user_repository.get_user_by_id.return_value = None
    rag_service = Mock()

    service = ChatService(
        user_repository=user_repository,
        chat_repository=chat_repository,
        rag_service=rag_service,
    )

    with pytest.raises(ValueError, match="User not found"):
        service.list_user_chats(
            user_id=user_id,
        )

    user_repository.get_user_by_id.assert_called_once_with(user_id)
    chat_repository.list_chats_by_user.assert_not_called()


def test_create_user_message_success() -> None:
    user_id = uuid.uuid4()
    chat_id = uuid.uuid4()
    expected_message = Mock()

    chat_repository = Mock(spec=ChatRepository)
    user_repository = Mock(spec=UserRepository)

    chat = Mock()
    chat.user_id = user_id

    chat_repository.get_chat_by_id.return_value = chat
    chat_repository.get_next_message_index.return_value = 3
    chat_repository.create_message.return_value = expected_message
    rag_service = Mock()

    service = ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
        rag_service=rag_service,
    )

    result = service.create_user_message(
        user_id=user_id,
        chat_id=chat_id,
        content="Hello success",
    )

    assert result is expected_message
    chat_repository.get_chat_by_id.assert_called_once_with(
        chat_id=chat_id,
    )
    chat_repository.get_next_message_index.assert_called_once_with(
        chat_id=chat_id,
    )
    chat_repository.create_message.assert_called_once_with(
        chat_id=chat_id,
        message_index=3,
        role="user",
        content="Hello success",
    )


def test_list_chat_messages_success() -> None:
    user_id = uuid.uuid4()
    chat_id = uuid.uuid4()
    expected_messages = [Mock(), Mock()]

    chat = Mock()
    chat.user_id = user_id

    chat_repository = Mock(spec=ChatRepository)
    user_repository = Mock(spec=UserRepository)

    chat_repository.get_chat_by_id.return_value = chat
    chat_repository.list_messages_by_chat.return_value = expected_messages
    rag_service = Mock()

    service = ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
        rag_service=rag_service,
    )

    result = service.list_chat_messages(
        user_id=user_id,
        chat_id=chat_id,
    )

    assert result is expected_messages
    chat_repository.get_chat_by_id.assert_called_once_with(
        chat_id=chat_id,
    )
    chat_repository.list_messages_by_chat.assert_called_once_with(
        chat_id=chat_id,
    )


def test_create_rag_message_persists_user_message_then_assistant_message() -> None:
    user_id = uuid.uuid4()
    chat_id = uuid.uuid4()
    document_id = uuid.uuid4()
    chunk_id = uuid.uuid4()

    chat = Mock()
    chat.user_id = user_id

    assistant_message = Mock()

    chat_repository = Mock(spec=ChatRepository)
    user_repository = Mock(spec=UserRepository)
    rag_service = Mock()

    citation = ContextCitation(
        source_number=1,
        document_id=document_id,
        chunk_id=chunk_id,
        chunk_index=0,
        page_number=2,
        start_time_seconds=None,
        end_time_seconds=None,
        distance=0.12,
    )

    chat_repository.get_chat_by_id.return_value = chat
    chat_repository.get_next_message_index.return_value = 4
    chat_repository.create_message.side_effect = [Mock(), assistant_message]

    rag_service.answer_question.return_value = RagAnswer(
        answer="The answer from the document.",
        context="[Source 1]\nContent:\nRelevant text",
        citations=[citation],
    )

    service = ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
        rag_service=rag_service,
    )

    result = service.create_rag_message(
        user_id=user_id,
        chat_id=chat_id,
        content="What does the document say?",
        document_id=document_id,
        top_k=3,
    )

    assert result is assistant_message

    rag_service.answer_question.assert_called_once_with(
        question="What does the document say?",
        user_id=user_id,
        document_id=document_id,
        top_k=3,
    )

    assert chat_repository.create_message.call_count == 2

    first_call = chat_repository.create_message.call_args_list[0]
    second_call = chat_repository.create_message.call_args_list[1]

    assert first_call.kwargs["role"] == "user"
    assert first_call.kwargs["message_index"] == 4
    assert first_call.kwargs["content"] == "What does the document say?"

    assert second_call.kwargs["role"] == "assistant"
    assert second_call.kwargs["message_index"] == 5
    assert second_call.kwargs["content"] == "The answer from the document."
    assert second_call.kwargs["message_metadata"]["citations"][0]["document_id"] == str(
        document_id)
    assert second_call.kwargs["message_metadata"]["citations"][0]["chunk_id"] == str(
        chunk_id)


def test_chat_question_route_returns_chat_message_read_schema() -> None:
    question_route = next(
        route
        for route in chat_router.routes
        if route.path == "/chats/{chat_id}/questions" and "POST" in route.methods
    )

    assert question_route.response_model is ChatMessageRead
