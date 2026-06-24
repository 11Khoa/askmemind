import uuid

from sqlalchemy.orm import Session

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
        status: str,
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
            status=status,
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
