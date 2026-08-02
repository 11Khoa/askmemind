import uuid

from sqlalchemy.orm import Session

from app.core.types import DocumentStatus
from app.models.document import Document


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
        )

        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)

        return document

    def get_document_by_id(self, document_id: uuid.UUID) -> Document | None:
        return self.db.get(Document, document_id)

    def list_documents_by_user(self, user_id: uuid.UUID) -> list[Document]:
        return (
            self.db.query(Document)
            .filter(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .all()
        )

    def mark_processing_started(
        self,
        document: Document,
    ) -> Document:
        document.status = DocumentStatus.PROCESSING.value
        document.error_message = None

        self.db.flush()

        return document

    def mark_processing_completed(
        self,
        document: Document,
        page_count: int | None,
    ) -> Document:
        document.status = DocumentStatus.COMPLETED.value
        document.page_count = page_count
        document.error_message = None

        self.db.flush()

        return document

    def mark_processing_failed(
        self,
        document: Document,
        error_message: str,
    ) -> Document:
        document.status = DocumentStatus.FAILED.value
        document.error_message = error_message

        self.db.flush()

        return document

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
