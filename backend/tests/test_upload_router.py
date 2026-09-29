import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.dependencies import (
    get_current_user,
    get_document_service,
    get_file_storage_service,
)
from app.core.types import DocumentStatus
from app.main import app
from app.routers import upload as upload_router


PDF_BYTES = b'%PDF-1.7\nvalid pdf bytes'


def _document(user_id: uuid.UUID) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        filename='stored.pdf',
        original_filename='original.pdf',
        file_path='/tmp/stored.pdf',
        content_type='application/pdf',
        file_size_bytes=len(PDF_BYTES),
        status=DocumentStatus.PROCESSING.value,
        page_count=None,
        source_type='pdf',
        source_metadata=None,
        error_message=None,
        created_at=now,
        updated_at=now,
    )


class FakeDocumentService:
    def __init__(self, document: SimpleNamespace) -> None:
        self.document = document

    def create_uploaded_document(self, **kwargs):
        self.document.filename = kwargs['filename']
        self.document.original_filename = kwargs['original_filename']
        self.document.file_path = kwargs['file_path']
        self.document.content_type = kwargs['content_type']
        self.document.file_size_bytes = kwargs['file_size_bytes']
        return self.document


class FakeFileStorageService:
    def save_upload(self, file_bytes: bytes, filename: str) -> str:
        assert file_bytes == PDF_BYTES
        return '/tmp/' + filename

    def delete_file(self, file_path: str) -> None:
        raise AssertionError('delete_file should not be called')


def _install_upload_overrides(document: SimpleNamespace, user_id: uuid.UUID) -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    app.dependency_overrides[get_document_service] = lambda: FakeDocumentService(document)
    app.dependency_overrides[get_file_storage_service] = lambda: FakeFileStorageService()


def test_upload_returns_202_processing_and_background_success(monkeypatch) -> None:
    user_id = uuid.uuid4()
    document = _document(user_id=user_id)
    calls: list[tuple[str, str, str | None, str]] = []

    monkeypatch.setattr(
        upload_router.process_document_task,
        'delay',
        lambda *args: calls.append(args),
    )
    _install_upload_overrides(document=document, user_id=user_id)

    try:
        client = TestClient(app)
        response = client.post(
            '/documents/upload',
            files={'file': ('original.pdf', PDF_BYTES, 'application/pdf')},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    payload = response.json()
    assert payload['status'] == DocumentStatus.PROCESSING.value
    assert calls == [
        (
            str(document.id),
            document.file_path,
            response.headers['X-Request-ID'],
            str(user_id),
        )
    ]


def test_upload_returns_202_processing_without_waiting_for_task(monkeypatch) -> None:
    user_id = uuid.uuid4()
    document = _document(user_id=user_id)

    monkeypatch.setattr(
        upload_router.process_document_task,
        'delay',
        lambda *args: None,
    )
    _install_upload_overrides(document=document, user_id=user_id)

    try:
        client = TestClient(app)
        response = client.post(
            '/documents/upload',
            files={'file': ('original.pdf', PDF_BYTES, 'application/pdf')},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()['status'] == DocumentStatus.PROCESSING.value
    assert document.status == DocumentStatus.PROCESSING.value
    assert document.error_message is None
