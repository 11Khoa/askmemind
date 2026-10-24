import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_user, get_db
from app.main import app
from app.models.user import User
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.chat_message import ChatMessage
from app.repositories.chat_repository import ChatRepository
from app.repositories.document_repository import DocumentRepository
from app.services.chat_service import ChatService
from app.repositories.user_repository import UserRepository
from app.services.rag_service import RagAnswer


@pytest.fixture
def workspace(db_session, tmp_path):
    owner = User(email="features@example.com", hashed_password="hashed", role="admin")
    db_session.add(owner)
    db_session.commit()
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-1.7\nsource bytes")
    document = Document(
        user_id=owner.id, filename="source.pdf", original_filename="source.pdf",
        file_path=str(pdf), content_type="application/pdf", file_size_bytes=pdf.stat().st_size,
        status="ready", page_count=3, chunk_count=1,
    )
    db_session.add(document)
    db_session.flush()
    chunk = Chunk(document_id=document.id, chunk_index=0, content="A sourced passage.", page_number=3)
    db_session.add(chunk)
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_db] = lambda: db_session
    yield SimpleNamespace(client=TestClient(app), owner=owner, document=document, chunk=chunk, pdf=pdf)
    app.dependency_overrides.clear()


def test_source_endpoints_return_passage_and_private_pdf(workspace):
    w = workspace
    response = w.client.get(f"/documents/{w.document.id}/chunks/{w.chunk.id}")
    assert response.status_code == 200
    assert response.json()["content"] == "A sourced passage."
    assert response.json()["page_number"] == 3
    response = w.client.get(f"/documents/{w.document.id}/file")
    assert response.status_code == 200
    assert response.content == w.pdf.read_bytes()
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Content-Type"] == "application/pdf"
    assert response.headers["Content-Disposition"].startswith("inline")
    assert w.client.get(f"/documents/{w.document.id}/chunks/{uuid.uuid4()}").status_code == 404


def test_delete_document_cascades_chunks_scrubs_cached_sources_and_releases_quota(workspace, db_session):
    w = workspace
    repository = ChatRepository(db_session)
    chat = repository.create_chat(w.owner.id, "Saved sources")
    message = repository.create_message(chat.id, 1, "assistant", "Historical answer", {
        "context": "A sourced passage.",
        "citations": [{"document_id": str(w.document.id), "chunk_id": str(w.chunk.id)}],
    })
    document_id, chunk_id = w.document.id, w.chunk.id
    assert w.client.delete(f"/documents/{document_id}").status_code == 204
    assert not w.pdf.exists()
    db_session.expire_all()
    assert db_session.get(Document, document_id) is None
    assert db_session.get(Chunk, chunk_id) is None
    persisted = db_session.get(ChatMessage, message.id)
    assert persisted.content == "Historical answer"
    assert persisted.message_metadata["context"] == ""
    assert persisted.message_metadata["citations"] == []
    assert persisted.message_metadata["sources_deleted"] is True
    assert w.client.get(f"/documents/{document_id}/file").status_code == 404


def test_delete_chat_cascades_messages_but_keeps_documents(workspace, db_session):
    w = workspace
    repository = ChatRepository(db_session)
    chat = repository.create_chat(w.owner.id, "Delete me")
    message = repository.create_message(chat.id, 0, "user", "Question")
    message_id = message.id
    assert w.client.delete(f"/chats/{chat.id}").status_code == 204
    assert db_session.query(ChatMessage).filter_by(id=message_id).first() is None
    assert w.pdf.exists()
    assert db_session.get(Document, w.document.id) is not None


def test_other_users_cannot_delete_or_read_sources(workspace, db_session):
    w = workspace
    chat = ChatRepository(db_session).create_chat(w.owner.id, "Private")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    for method, path in [
        ("delete", f"/documents/{w.document.id}"), ("delete", f"/chats/{chat.id}"),
        ("get", f"/documents/{w.document.id}/file"),
        ("get", f"/documents/{w.document.id}/chunks/{w.chunk.id}"),
    ]:
        assert getattr(w.client, method)(path).status_code == 403
    assert w.pdf.exists()


def test_active_worker_prevents_deletion(workspace, db_session):
    w = workspace
    with DocumentRepository(db_session).processing_lock(w.document.id) as acquired:
        assert acquired
        assert w.client.delete(f"/documents/{w.document.id}").status_code == 409
    assert w.pdf.exists()


def test_failed_file_cleanup_is_retryable(workspace, db_session, monkeypatch):
    w = workspace
    original = Path.unlink
    def fail(path, **kwargs):
        if path == w.pdf:
            raise PermissionError("Filesystem unavailable")
        return original(path, **kwargs)
    monkeypatch.setattr(Path, "unlink", fail)
    path = f"/documents/{w.document.id}"
    assert w.client.delete(path).status_code == 503
    assert w.client.get(path).json()["status"] == "deleting"
    assert w.client.get(path + "/file").status_code == 409
    monkeypatch.setattr(Path, "unlink", original)
    assert w.client.delete(path).status_code == 204


def test_generation_cannot_restore_deleted_source(workspace, db_session):
    w = workspace
    repository = ChatRepository(db_session)
    chat = repository.create_chat(w.owner.id, "In-flight answer")
    document_id = w.document.id
    assert w.client.delete(f"/documents/{document_id}").status_code == 204
    message = repository.create_message(chat.id, 1, "assistant", "Stale answer", {
        "context": "Deleted text", "citations": [{"document_id": str(document_id)}],
    })
    assert message.message_metadata["sources_deleted"]
    assert message.message_metadata["context"] == ""
    assert message.content != "Stale answer"


def test_history_only_uses_completed_prior_turns_in_same_scope(workspace, db_session):
    w = workspace
    repository = ChatRepository(db_session)
    chat = repository.create_chat(w.owner.id, "Follow ups")
    for index, scope in [(0, str(w.document.id)), (2, str(uuid.uuid4())), (4, None)]:
        repository.create_message(chat.id, index, "user", f"Q{index}", {"document_id": scope})
        repository.create_message(chat.id, index + 1, "assistant", f"A{index}")
    repository.create_message(chat.id, 6, "user", "Incomplete", {"document_id": str(w.document.id)})
    history = repository.conversation_history(chat.id, 7, w.document.id, 6, 12000)
    assert [m["content"] for m in history] == ["Q0", "A0"]
    assert repository.conversation_history(chat.id, 7, w.document.id, 6, 1) == []
    rag = Mock()
    rag.answer_question.return_value = RagAnswer("Answer", "", [])
    service = ChatService(repository, UserRepository(db_session), rag)
    service.create_rag_message(w.owner.id, chat.id, "Explain that", w.document.id)
    assert rag.answer_question.call_args.kwargs["history"] == history
