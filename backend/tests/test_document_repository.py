from sqlalchemy.orm import Session

from app.core.types import DocumentStatus
from app.models.document import Document
from app.models.user import User
from app.repositories.document_repository import DocumentRepository


def test_mark_processing_started(db_session: Session) -> None:
    user = User(
        email="document-processing-started@gmail.com",
        hashed_password="hashed",
    )

    document = Document(
        filename="started.pdf",
        original_filename="started.pdf",
        file_path="/tmp/started.pdf",
        content_type="application/pdf",
        file_size_bytes=123,
        status=DocumentStatus.UPLOADED.value,
        error_message="Old error",
    )

    user.documents.append(document)
    db_session.add(user)
    db_session.flush()

    repository = DocumentRepository(db=db_session)

    uploaded_document = repository.mark_processing_started(document=document)

    assert uploaded_document is document
    assert document.status == DocumentStatus.PROCESSING.value
    assert document.error_message is None


def test_mark_processing_completed(db_session: Session) -> None:
    user = User(
        email="document-processing-completed@gmail.com",
        hashed_password="hashed",
    )

    document = Document(
        filename="completed.pdf",
        original_filename="completed.pdf",
        file_path="/tmp/completed.pdf",
        content_type="application/pdf",
        file_size_bytes=123,
        status=DocumentStatus.PROCESSING.value,
        error_message="Old error",
    )

    user.documents.append(document)
    db_session.add(user)
    db_session.flush()

    repository = DocumentRepository(db=db_session)

    updated_document = repository.mark_processing_completed(
        document=document,
        page_count=5,
    )

    assert updated_document is document
    assert document.status == DocumentStatus.COMPLETED.value
    assert document.page_count == 5
    assert document.error_message is None


def test_mark_processing_failed(db_session: Session) -> None:
    user = User(
        email="document-processing-failed@gmail.com",
        hashed_password="hashed",
    )

    document = Document(
        filename="failed.pdf",
        original_filename="failed.pdf",
        file_path="/tmp/failed.pdf",
        content_type="application/pdf",
        file_size_bytes=123,
        status=DocumentStatus.PROCESSING.value,
    )

    user.documents.append(document)
    db_session.add(user)
    db_session.flush()

    repository = DocumentRepository(db=db_session)

    updated_document = repository.mark_processing_failed(
        document=document,
        error_message="PDF has no extractable text",
    )

    assert updated_document is document
    assert document.status == DocumentStatus.FAILED.value
    assert document.error_message == "PDF has no extractable text"
