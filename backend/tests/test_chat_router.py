import uuid
from datetime import datetime, UTC
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.core.dependencies import get_chat_service, get_current_user
from app.main import app


def test_create_rag_question_returns_assistant_message() -> None:
    user_id = uuid.uuid4()
    chat_id = uuid.uuid4()
    document_id = uuid.uuid4()
    message_id = uuid.uuid4()

    chat_service = Mock()
    chat_service.create_rag_message.return_value = SimpleNamespace(
        id=message_id,
        chat_id=chat_id,
        message_index=1,
        role="assistant",
        content="This document is about backend engineering.",
        message_metadata={
            "citations": [],
            "context": "Relevant context",
        },
        created_at=datetime.now(UTC),
    )

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=user_id)
    app.dependency_overrides[get_chat_service] = lambda: chat_service

    try:
        client = TestClient(app=app)

        response = client.post(
            f"/chats/{chat_id}/questions",
            json={
                "content": "What is this document about?",
                "document_id": str(document_id),
                "top_k": 3,
            },
        )

        assert response.status_code == 200
        payload = response.json()

        assert payload["id"] == str(message_id)
        assert payload["chat_id"] == str(chat_id)
        assert payload["role"] == "assistant"
        assert payload["content"] == "This document is about backend engineering."
        assert payload["message_metadata"]["citations"] == []

        chat_service.create_rag_message.assert_called_once_with(
            user_id=user_id,
            chat_id=chat_id,
            content="What is this document about?",
            document_id=document_id,
            top_k=3,
        )
    finally:
        app.dependency_overrides.clear()


def test_create_rag_question_maps_value_error_to_404() -> None:
    user_id = uuid.uuid4()
    chat_id = uuid.uuid4()

    chat_service = Mock()
    chat_service.create_rag_message.side_effect = ValueError("Chat not found")

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=user_id)
    app.dependency_overrides[get_chat_service] = lambda: chat_service

    try:
        client = TestClient(app)

        response = client.post(
            f"/chats/{chat_id}/questions",
            json={
                "content": "Question?",
                "top_k": 3,
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Chat not found"
    finally:
        app.dependency_overrides.clear()


def test_create_rag_question_maps_permission_error_to_403() -> None:
    user_id = uuid.uuid4()
    chat_id = uuid.uuid4()

    chat_service = Mock()
    chat_service.create_rag_message.side_effect = PermissionError(
        "You don't have access to this chat"
    )

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=user_id)
    app.dependency_overrides[get_chat_service] = lambda: chat_service

    try:
        client = TestClient(app)

        response = client.post(
            f"/chats/{chat_id}/questions",
            json={
                "content": "Question?",
                "top_k": 3,
            },
        )

        assert response.status_code == 403
        assert response.json()[
            "detail"] == "You don't have access to this chat"
    finally:
        app.dependency_overrides.clear()
