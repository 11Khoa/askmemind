import uuid
from pathlib import Path

from app.core.types import DocumentStatus
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository


class DocumentRetryConflict(Exception):
    pass


class DocumentService:
    def __init__(
        self,
        document_repository: DocumentRepository,
        user_repository: UserRepository,
    ):
        self.document_repository = document_repository
        self.user_repository = user_repository

    def list_user_documents(
        self,
        user_id: uuid.UUID,
    ) -> list[Document]:
        user = self.user_repository.get_user_by_id(user_id=user_id)

        if user is None:
            raise ValueError("User not found")

        return self.document_repository.list_documents_by_user(user_id=user_id)

    def get_user_document(
        self,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> Document:
        document = self.document_repository.get_document_by_id(
            document_id=document_id,
        )

        if document is None:
            raise ValueError("Document not found")

        if document.user_id != user_id:
            raise PermissionError("You don't have access to this document")

        return document

    def create_uploaded_document(
        self,
        user_id: uuid.UUID,
        filename: str,
        original_filename: str,
        file_path: str,
        content_type: str,
        file_size_bytes: int,
    ) -> Document:
        user = self.user_repository.get_user_by_id(user_id=user_id)

        if user is None:
            raise ValueError("User not found")

        if content_type != "application/pdf":
            raise ValueError("Only PDF uploads are supported")

        if file_size_bytes <= 0:
            raise ValueError("File size must be greater than 0")

        return self.document_repository.create_document(
            user_id=user_id,
            filename=filename,
            original_filename=original_filename,
            file_path=file_path,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            status=DocumentStatus.PROCESSING,
            source_type="pdf",
            source_metadata=None,
        )

    def retry_document(self, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        document = self.get_user_document(user_id, document_id)
        if document.status not in {DocumentStatus.PROCESSING_FAILED.value, "failed"}:
            raise DocumentRetryConflict("Only failed documents can be retried")
        if document.chunk_count is None and not Path(document.file_path).is_file():
            raise DocumentRetryConflict("Original PDF is unavailable. Upload it again.")
        with self.document_repository.processing_lock(document_id) as acquired:
            if not acquired:
                raise DocumentRetryConflict(
                    "Previous processing attempt is finishing. Please retry shortly."
                )
            claimed = self.document_repository.claim_retry(document_id, user_id)
        if claimed is None:
            raise DocumentRetryConflict("Document is already being processed")
        return claimed

    def fail_enqueue(self, document: Document) -> None:
        self.document_repository.fail_attempt(
            document.id,
            document.processing_attempt_id,
            "Could not queue document processing. Please retry.",
        )
