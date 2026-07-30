import uuid

from app.models.user import User
from app.repositories.chat_repository import ChatRepository


def create_test_user(db_session, email: str = "chat-repo@example.com") -> User:
    user = User(
        email=email,
        hashed_password="hashed",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    return user


def test_create_chat_persists_chat(db_session) -> None:
    user = create_test_user(db_session)
    repository = ChatRepository(db=db_session)

    chat = repository.create_chat(
        user_id=user.id,
        title="Repository chat",
    )

    assert chat.id is not None
    assert chat.user_id == user.id
    assert chat.title == "Repository chat"
    assert chat.created_at is not None
    assert chat.updated_at is not None
    persisted_chat = repository.get_chat_by_id(chat_id=chat.id)

    assert persisted_chat is not None
    assert persisted_chat.id == chat.id


def test_get_chat_by_id_returns_none_when_missing(db_session) -> None:
    repository = ChatRepository(db=db_session)

    result = repository.get_chat_by_id(chat_id=uuid.uuid4())

    assert result is None


def test_list_chats_by_user_returns_only_that_users_chats(db_session) -> None:
    user = create_test_user(
        db_session,
        email="owner@gmail.com",
    )
    other_user = create_test_user(
        db_session,
        email="other@gmail.com",
    )
    repository = ChatRepository(db=db_session)

    first_chat = repository.create_chat(
        user_id=user.id,
        title="First chat",
    )
    second_chat = repository.create_chat(
        user_id=user.id,
        title="Second chat",
    )
    repository.create_chat(
        user_id=other_user.id,
        title="Other user's chat",
    )

    result = repository.list_chats_by_user(
        user_id=user.id,
    )

    result_ids = {
        chat.id for chat in result
    }

    assert first_chat.id in result_ids
    assert second_chat.id in result_ids
    assert all(
        chat.user_id == user.id
        for chat in result
    )


def test_get_next_message_index_returns_zero_for_empty_chat(db_session) -> None:
    user = create_test_user(db_session)
    repository = ChatRepository(db=db_session)

    chat = repository.create_chat(
        user_id=user.id,
        title="Empty chat",
    )

    result = repository.get_next_message_index(chat_id=chat.id)

    assert result == 0


def test_create_message_persists_message_with_metadata(db_session) -> None:
    user = create_test_user(db_session)
    repository = ChatRepository(db=db_session)

    chat = repository.create_chat(
        user_id=user.id,
        title="Message chat",
    )

    message = repository.create_message(
        chat_id=chat.id,
        message_index=0,
        role="assistant",
        content="Assistant answer",
        message_metadata={
            "citations": [
                {
                    "source_number": 1,
                    "page_number": 2,
                }
            ]
        },
    )

    assert message.id is not None
    assert message.chat_id == chat.id
    assert message.message_index == 0
    assert message.role == "assistant"
    assert message.content == "Assistant answer"
    assert message.message_metadata == {
        "citations": [
            {
                "source_number": 1,
                "page_number": 2,
            }
        ]
    }


def test_get_next_message_index_returns_max_index_plus_one(db_session) -> None:
    user = create_test_user(db_session)
    repository = ChatRepository(db=db_session)

    chat = repository.create_chat(
        user_id=user.id,
        title="Indexed chat",
    )

    repository.create_message(
        chat_id=chat.id,
        message_index=0,
        role="user",
        content="First",
    )
    repository.create_message(
        chat_id=chat.id,
        message_index=1,
        role="assistant",
        content="Second",
    )

    result = repository.get_next_message_index(chat_id=chat.id)

    assert result == 2


def test_list_messages_by_chat_orders_by_message_index(db_session) -> None:
    user = create_test_user(db_session)
    repository = ChatRepository(db=db_session)

    chat = repository.create_chat(
        user_id=user.id,
        title="Ordered messages",
    )

    second_message = repository.create_message(
        chat_id=chat.id,
        message_index=1,
        role="assistant",
        content="Second",
    )
    first_message = repository.create_message(
        chat_id=chat.id,
        message_index=0,
        role="user",
        content="First",
    )

    result = repository.list_messages_by_chat(chat_id=chat.id)

    assert [message.id for message in result] == [
        first_message.id,
        second_message.id,
    ]