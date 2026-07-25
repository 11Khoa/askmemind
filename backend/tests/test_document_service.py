import uuid
from unittest.mock import Mock

import pytest

from app.core.types import DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.services.document_service import DocumentService


def test_create_uploaded_document_success() -> None:
    user_id = uuid.uuid4()
    expected_document = Mock()

    document_repository = Mock(spec=DocumentRepository)
    user_repository = Mock(spec=UserRepository)

    user_repository.get_user_by_id.return_value = Mock()
    document_repository.create_document.return_value = expected_document

    service = DocumentService(
        document_repository=document_repository,
        user_repository=user_repository,
    )

    result = service.create_uploaded_document(
        user_id=user_id,
        filename="stored.pdf",
        original_filename="original.pdf",
        file_path="/uploads/stored.pdf",
        content_type="application/pdf",
        file_size_bytes=123,
    )

    assert result is expected_document
    user_repository.get_user_by_id.assert_called_once_with(user_id=user_id)
    document_repository.create_document.assert_called_once_with(
        user_id=user_id,
        filename="stored.pdf",
        original_filename="original.pdf",
        file_path="/uploads/stored.pdf",
        content_type="application/pdf",
        file_size_bytes=123,
        status=DocumentStatus.UPLOADED,
        source_type="pdf",
        source_metadata=None,
    )


def test_create_uploaded_document_raises_when_user_not_found() -> None:
    user_id = uuid.uuid4()

    document_repository = Mock(spec=DocumentRepository)
    user_repository = Mock(spec=UserRepository)

    user_repository.get_user_by_id.return_value = None

    service = DocumentService(
        document_repository=document_repository,
        user_repository=user_repository,
    )

    with pytest.raises(ValueError, match="User not found"):
        service.create_uploaded_document(
            user_id=user_id,
            filename="stored.pdf",
            original_filename="original.pdf",
            file_path="/uploads/stored.pdf",
            content_type="application/pdf",
            file_size_bytes=123,
        )

    user_repository.get_user_by_id.assert_called_once_with(user_id=user_id)
    document_repository.create_document.assert_not_called()


def test_create_uploaded_document_rejects_non_pdf_content_type() -> None:
    user_id = uuid.uuid4()

    document_repository = Mock(spec=DocumentRepository)
    user_repository = Mock(spec=UserRepository)

    user_repository.get_user_by_id.return_value = Mock()

    service = DocumentService(
        document_repository=document_repository,
        user_repository=user_repository,
    )

    with pytest.raises(ValueError, match="Only PDF uploads are supported"):
        service.create_uploaded_document(
            user_id=user_id,
            filename="stored.txt",
            original_filename="original.txt",
            file_path="/uploads/stored.txt",
            content_type="text/plain",
            file_size_bytes=123,
        )

    user_repository.get_user_by_id.assert_called_once_with(user_id=user_id)
    document_repository.create_document.assert_not_called()


def test_create_uploaded_document_rejects_empty_file() -> None:
    user_id = uuid.uuid4()

    document_repository = Mock(spec=DocumentRepository)
    user_repository = Mock(spec=UserRepository)

    user_repository.get_user_by_id.return_value = Mock()

    service = DocumentService(
        document_repository=document_repository,
        user_repository=user_repository,
    )

    with pytest.raises(ValueError, match="File size must be greater than 0"):
        service.create_uploaded_document(
            user_id=user_id,
            filename="stored.pdf",
            original_filename="original.pdf",
            file_path="/uploads/stored.pdf",
            content_type="application/pdf",
            file_size_bytes=0,
        )

    user_repository.get_user_by_id.assert_called_once_with(user_id=user_id)
    document_repository.create_document.assert_not_called()


def test_get_user_document_returns_document_for_owner() -> None:
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()

    document = Mock()
    document.user_id = user_id

    document_repository = Mock(spec=DocumentRepository)
    user_repository = Mock(spec=UserRepository)

    document_repository.get_document_by_id.return_value = document

    service = DocumentService(
        document_repository=document_repository,
        user_repository=user_repository,
    )

    result = service.get_user_document(
        user_id=user_id,
        document_id=document_id,
    )

    assert result is document
    document_repository.get_document_by_id.assert_called_once_with(
        document_id=document_id,
    )


def test_get_user_document_raises_when_document_not_found() -> None:
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()

    document_repository = Mock(spec=DocumentRepository)
    user_repository = Mock(spec=UserRepository)

    document_repository.get_document_by_id.return_value = None

    service = DocumentService(
        document_repository=document_repository,
        user_repository=user_repository,
    )

    with pytest.raises(ValueError, match="Document not found"):
        service.get_user_document(
            user_id=user_id,
            document_id=document_id,
        )
    document_repository.get_document_by_id.assert_called_once_with(
        document_id=document_id,
    )


def test_get_user_document_raises_when_user_is_not_owner() -> None:
    user_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    document_id = uuid.uuid4()

    document = Mock()
    document.user_id = owner_id

    document_repository = Mock(spec=DocumentRepository)
    user_repository = Mock(spec=UserRepository)

    document_repository.get_document_by_id.return_value = document

    service = DocumentService(
        document_repository=document_repository,
        user_repository=user_repository,
    )

    with pytest.raises(
        PermissionError,
        match="You don't have access to this document",
    ):
        service.get_user_document(
            user_id=user_id,
            document_id=document_id,
        )

    document_repository.get_document_by_id.assert_called_once_with(
        document_id=document_id,
    )


def test_list_user_documents_when_user_exists() -> None:
    user_id = uuid.uuid4()
    expected_documents = [Mock(), Mock()]

    document_repository = Mock(spec=DocumentRepository)
    user_repository = Mock(spec=UserRepository)

    user_repository.get_user_by_id.return_value = Mock()
    document_repository.list_documents_by_user.return_value = expected_documents

    service = DocumentService(
        document_repository=document_repository,
        user_repository=user_repository,
    )

    result = service.list_user_documents(user_id=user_id)

    assert result is expected_documents
    user_repository.get_user_by_id.assert_called_once_with(user_id=user_id)
    document_repository.list_documents_by_user.assert_called_once_with(
        user_id=user_id,
    )


def test_list_user_documents_raises_when_user_not_found() -> None:
    user_id = uuid.uuid4()

    document_repository = Mock(spec=DocumentRepository)
    user_repository = Mock(spec=UserRepository)

    user_repository.get_user_by_id.return_value = None

    service = DocumentService(
        document_repository=document_repository,
        user_repository=user_repository,
    )

    with pytest.raises(ValueError, match="User not found"):
        service.list_user_documents(user_id=user_id)

    user_repository.get_user_by_id.assert_called_once_with(user_id=user_id)
    document_repository.list_documents_by_user.assert_not_called()
