from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from unittest.mock import Mock

import pytest

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.types import DocumentStatus
from app.database import engine
from app.models.user import User
from app.repositories.chat_repository import ChatRepository
from app.repositories.document_repository import DocumentQuotaExceeded, DocumentRepository
from app.repositories.user_repository import UserRepository
from app.services.chat_service import ChatService
from app.services.rag_service import RagAnswer


def create_owner():
    owner = uuid4()
    with Session(engine) as db:
        db.add(User(id=owner, email=f"{owner}@example.com", hashed_password="hashed"))
        db.commit()
    return owner


def delete_owner(owner):
    with Session(engine) as db:
        db.execute(delete(User).where(User.id == owner))
        db.commit()


def test_concurrent_questions_reserve_adjacent_question_answer_pairs():
    owner = create_owner()
    with Session(engine) as db:
        chat_id = ChatRepository(db).create_chat(owner, "Concurrent chat").id
    barrier = Barrier(2)

    def ask(question):
        with Session(engine) as db:
            rag = Mock()

            def answer(**kwargs):
                # Both user messages have been committed before either answer.
                barrier.wait(timeout=10)
                return RagAnswer(f"Answer: {kwargs['question']}", "", [])

            rag.answer_question.side_effect = answer
            service = ChatService(ChatRepository(db), UserRepository(db), rag)
            return service.create_rag_message(owner, chat_id, question).content

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert set(pool.map(ask, ["A", "B"])) == {"Answer: A", "Answer: B"}
        with Session(engine) as db:
            messages = ChatRepository(db).list_messages_by_chat(chat_id)
            assert [m.message_index for m in messages] == [0, 1, 2, 3]
            assert [m.role for m in messages] == ["user", "assistant", "user", "assistant"]
            assert messages[1].content == f"Answer: {messages[0].content}"
            assert messages[3].content == f"Answer: {messages[2].content}"
    finally:
        delete_owner(owner)


@pytest.mark.parametrize("quota,value,file_size", [
    ("max_documents_per_user", 1, 100),
    ("max_storage_per_user_mb", 1, 600_000),
])
def test_concurrent_uploads_cannot_exceed_document_quota(monkeypatch, quota, value, file_size):
    monkeypatch.setattr(settings, quota, value)
    owner = create_owner()
    barrier = Barrier(2)

    def upload(_):
        with Session(engine) as db:
            barrier.wait(timeout=10)
            try:
                DocumentRepository(db).create_document(
                    owner, "stored.pdf", "original.pdf", "/tmp/stored.pdf",
                    "application/pdf", file_size, DocumentStatus.PROCESSING, "pdf",
                )
                return True
            except DocumentQuotaExceeded:
                return False

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(upload, range(2))).count(True) == 1
        with Session(engine) as db:
            assert len(DocumentRepository(db).list_documents_by_user(owner)) == 1
    finally:
        delete_owner(owner)
