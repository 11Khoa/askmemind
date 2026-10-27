import uuid
from contextlib import contextmanager

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.core.types import DocumentStatus
from app.core.config import settings
from app.models.document import Document
from app.models.user import User
from app.models.chunk import Chunk
from app.models.chat import Chat
from app.models.chat_message import ChatMessage
from app.services.document_progress import failed_progress


class DocumentQuotaExceeded(Exception):
    pass


class DocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_document(
        self,
        user_id: uuid.UUID,
        filename: str,
        original_filename: str,
        file_path: str,
        content_type: str,
        file_size_bytes: int,
        status: DocumentStatus,
        source_type: str,
        source_metadata: dict | None = None,
    ) -> Document:
        # Serialize quota checks with insertion across simultaneous uploads.
        self.db.query(User.id).filter(User.id == user_id).with_for_update().one()
        count, stored_bytes = self.db.query(
            func.count(Document.id), func.coalesce(func.sum(Document.file_size_bytes), 0)
        ).filter(Document.user_id == user_id).one()
        if count >= settings.max_documents_per_user:
            self.db.rollback()
            raise DocumentQuotaExceeded("Document limit reached")
        if stored_bytes + file_size_bytes > settings.max_storage_per_user_mb * 1024 * 1024:
            self.db.rollback()
            raise DocumentQuotaExceeded("Document storage limit reached")

        document = Document(
            user_id=user_id,
            filename=filename,
            original_filename=original_filename,
            file_path=file_path,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            status=status.value,
            source_type=source_type,
            source_metadata=source_metadata,
            processing_attempt_id=uuid.uuid4(),
        )

        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)

        return document

    def get_document_by_id(self, document_id: uuid.UUID) -> Document | None:
        return self.db.query(Document).populate_existing().filter(Document.id == document_id).first()

    def get_chunk(self, document_id: uuid.UUID, chunk_id: uuid.UUID) -> Chunk | None:
        return self.db.query(Chunk).filter(
            Chunk.document_id == document_id, Chunk.id == chunk_id,
        ).first()

    def begin_deletion(self, document: Document) -> None:
        # Persist intent before touching disk. A failed cleanup can be retried;
        # queued workers and retrieval both exclude this status.
        document.status = "deleting"
        document.processing_attempt_id = None
        self.db.commit()

    def delete_document(self, document: Document, actor_id=None) -> None:
        # Remove retained excerpts as well as rows/vectors. Historical answers
        # remain in chats, but are no longer eligible as conversation context.
        for message in self.db.query(ChatMessage).populate_existing().join(Chat).filter(
            Chat.user_id == document.user_id, ChatMessage.role == "assistant",
        ).order_by(ChatMessage.id).with_for_update(of=ChatMessage).yield_per(100):
            metadata = message.message_metadata or {}
            citations = metadata.get("citations", [])
            if any(c.get("document_id") == str(document.id) for c in citations):
                message.message_metadata = {
                    **metadata, "context": "", "sources_deleted": True,
                    "citations": [c for c in citations if c.get("document_id") != str(document.id)],
                }
        if actor_id is not None:
            from app.services.audit_service import record_audit
            record_audit(self.db, actor_id, "admin.document.delete", document.id, document.user_id)
        self.db.delete(document)
        self.db.commit()

    def list_documents_by_user(self, user_id: uuid.UUID) -> list[Document]:
        return (
            self.db.query(Document)
            .filter(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .all()
        )

    @contextmanager
    def processing_lock(self, document_id: uuid.UUID):
        # A separate transaction keeps the advisory lock across checkpoint commits.
        key = int.from_bytes(document_id.bytes[:8], "big", signed=True)
        with self.db.get_bind().engine.connect() as connection, connection.begin():
            acquired = connection.scalar(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
            )
            yield bool(acquired)

    def claim_retry(
        self, document_id: uuid.UUID, user_id: uuid.UUID
    ) -> Document | None:
        result = self.db.execute(
            update(Document)
            .where(
                Document.id == document_id,
                Document.user_id == user_id,
                Document.status.in_([DocumentStatus.PROCESSING_FAILED.value, "failed"]),
            )
            .values(
                status=DocumentStatus.PROCESSING.value,
                error_message=None,
                processing_attempt_id=uuid.uuid4(),
            )
            .returning(Document),
            execution_options={"populate_existing": True},
        ).scalar_one_or_none()
        if result is not None:
            result.processing_progress = {**(result.processing_progress or {}),
                                          "stage": "queued", "error_code": None, "failed_stage": None}
        self.db.commit()
        return result

    def fail_attempt(
        self, document_id: uuid.UUID, attempt_id: uuid.UUID | None, reason: str
    ) -> None:
        previous = self.db.scalar(
            select(Document.processing_progress).where(
                Document.id == document_id, Document.processing_attempt_id == attempt_id,
            )
        )
        self.db.execute(
            update(Document)
            .where(
                Document.id == document_id,
                Document.processing_attempt_id == attempt_id,
                Document.status == DocumentStatus.PROCESSING.value,
            )
            .values(status=DocumentStatus.PROCESSING_FAILED.value, error_message=reason,
                    processing_progress=failed_progress(previous, reason))
        )
        self.db.commit()

    def mark_processing_started(
        self,
        document: Document,
    ) -> Document:
        document.status = DocumentStatus.PROCESSING.value
        document.error_message = None
        document.processing_progress = {**(document.processing_progress or {}), "stage": "queued",
                                        "error_code": None, "failed_stage": None}

        self.db.flush()

        return document

    def mark_processing_completed(
        self,
        document: Document,
        page_count: int | None,
    ) -> Document:
        document.status = DocumentStatus.READY.value
        document.processing_progress = {**(document.processing_progress or {}), "stage": "ready"}
        document.page_count = page_count
        document.error_message = None

        self.db.flush()

        return document

    def mark_processing_failed(
        self,
        document: Document,
        error_message: str,
    ) -> Document:
        document.status = DocumentStatus.PROCESSING_FAILED.value
        document.error_message = error_message
        document.processing_progress = failed_progress(document.processing_progress, error_message)

        self.db.flush()

        return document

    def mark_processing_documents_failed(
        self,
        error_message: str,
    ) -> int:
        updated_count = (
            self.db.query(Document)
            .filter(Document.status == DocumentStatus.PROCESSING.value)
            .update(
                {
                    Document.status: DocumentStatus.PROCESSING_FAILED.value,
                    Document.error_message: error_message,
                },
                synchronize_session="fetch",
            )
        )
        self.db.flush()
        return updated_count

    def get_user_document_by_original_filename(
        self,
        user_id: uuid.UUID,
        original_filename: str,
    ) -> Document | None:
        return (
            self.db.query(Document)
            .filter(
                Document.user_id == user_id,
                Document.original_filename == original_filename,
            )
            .order_by(Document.created_at.desc())
            .first()
        )
