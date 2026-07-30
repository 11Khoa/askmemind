from sqlalchemy.orm import Session

from app.models.chat import Chat
from app.models.chat_message import ChatMessage
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User


def test_user_document_chunk_relationship_objects() -> None:
    user = User(
        email="test@gmail.com",
        hashed_password="hashed",
    )

    document = Document(
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
        content_type="application/pdf",
        file_size_bytes=123,
    )

    chunk = Chunk(
        chunk_index=0,
        content="Hello chunk",
        page_number=1,
    )

    user.documents.append(document)
    document.chunks.append(chunk)

    assert document.user is user
    assert user.documents == [document]

    assert chunk.document is document
    assert document.chunks == [chunk]


def test_remove_chunk_from_document_deletes_orphan(db_session: Session) -> None:
    user = User(
        email="testdb@gmail.com",
        hashed_password="hashed",
    )

    document = Document(
        filename="testdb.pdf",
        original_filename="testdb.pdf",
        file_path="/tmp/testdb.pdf",
        content_type="application/pdf",
        file_size_bytes=123,
    )

    chunk = Chunk(
        chunk_index=0,
        content="Hello chunk testdb",
        page_number=1,
    )

    user.documents.append(document)
    document.chunks.append(chunk)

    db_session.add(user)
    db_session.commit()

    chunk_id = chunk.id

    document.chunks.remove(chunk)
    db_session.commit()

    assert db_session.get(Chunk, chunk_id) is None


def test_delete_document_deletes_chunks(db_session: Session) -> None:
    user = User(
        email="delete_document@gmail.com",
        hashed_password="hashed",
    )

    document = Document(
        filename="delete-document.pdf",
        original_filename="delete-document.pdf",
        file_path="/tmp/delete-document.pdf",
        content_type="application/pdf",
        file_size_bytes=123,
    )

    chunk = Chunk(
        chunk_index=0,
        content="Hello chunk delete document",
        page_number=1,
    )

    user.documents.append(document)
    document.chunks.append(chunk)

    db_session.add(user)
    db_session.commit()

    user_id = user.id
    document_id = document.id
    chunk_id = chunk.id

    db_session.delete(document)
    db_session.commit()

    assert db_session.get(User, user_id) is not None
    assert db_session.get(Document, document_id) is None
    assert db_session.get(Chunk, chunk_id) is None


def test_delete_user_deletes_documents_and_chunks(db_session: Session) -> None:
    user = User(
        email="delete_user@gmail.com",
        hashed_password="hashed",
    )

    document = Document(
        filename="delete-user.pdf",
        original_filename="delete-user.pdf",
        file_path="/tmp/delete-user.pdf",
        content_type="application/pdf",
        file_size_bytes=123,
    )

    chunk = Chunk(
        chunk_index=0,
        content="Hello chunk delete user",
        page_number=1,
    )

    user.documents.append(document)
    document.chunks.append(chunk)

    db_session.add(user)
    db_session.commit()

    user_id = user.id
    document_id = document.id
    chunk_id = chunk.id

    db_session.delete(user)
    db_session.commit()

    assert db_session.get(User, user_id) is None
    assert db_session.get(Document, document_id) is None
    assert db_session.get(Chunk, chunk_id) is None


def test_user_chat_message_relationship_objects() -> None:
    user = User(
        email="chat-object@gmail.com",
        hashed_password="hashed",
    )

    chat = Chat(
        title="Object relationship chat",
    )

    message = ChatMessage(
        message_index=0,
        role="user",
        content="Hello chat",
    )

    user.chats.append(chat)
    chat.messages.append(message)

    assert chat.user is user
    assert user.chats == [chat]

    assert message.chat is chat
    assert chat.messages == [message]


def test_remove_message_from_chat_deletes_orphan(db_session: Session) -> None:
    user = User(
        email="remove-message@gmail.com",
        hashed_password="hashed",
    )

    chat = Chat(
        title="Remove message chat",
    )

    message = ChatMessage(
        message_index=0,
        role="user",
        content="Message to remove",
    )

    user.chats.append(chat)
    chat.messages.append(message)

    db_session.add(user)
    db_session.commit()

    message_id = message.id

    chat.messages.remove(message)
    db_session.commit()

    assert db_session.get(ChatMessage, message_id) is None


def test_delete_chat_deletes_messages(db_session: Session) -> None:
    user = User(
        email="delete-chat@gmail.com",
        hashed_password="hashed",
    )

    chat = Chat(
        title="Delete chat",
    )

    message = ChatMessage(
        message_index=0,
        role="assistant",
        content="Message deleted with chat",
    )

    user.chats.append(chat)
    chat.messages.append(message)

    db_session.add(user)
    db_session.commit()

    user_id = user.id
    chat_id = chat.id
    message_id = message.id

    db_session.delete(chat)
    db_session.commit()

    assert db_session.get(User, user_id) is not None
    assert db_session.get(Chat, chat_id) is None
    assert db_session.get(ChatMessage, message_id) is None


def test_delete_user_deletes_chats_and_messages(db_session: Session) -> None:
    user = User(
        email="delete-user-chat@gmail.com",
        hashed_password="hashed",
    )

    chat = Chat(
        title="Delete user chat",
    )

    message = ChatMessage(
        message_index=0,
        role="user",
        content="Message deleted with user",
    )

    user.chats.append(chat)
    chat.messages.append(message)

    db_session.add(user)
    db_session.commit()

    user_id = user.id
    chat_id = chat.id
    message_id = message.id

    db_session.delete(user)
    db_session.commit()

    assert db_session.get(User, user_id) is None
    assert db_session.get(Chat, chat_id) is None
    assert db_session.get(ChatMessage, message_id) is None
