from pathlib import Path
from unittest.mock import Mock
import uuid

import fitz
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.document import Document
from app.models.document_page_checkpoint import DocumentPageCheckpoint
from app.models.user import User
from app.repositories.document_repository import DocumentRepository
from app.services.document_progress import DocumentProgress, processing_error_code
from app.services.extraction import pdf_extraction_service as extraction
from app.repositories.chunk_repository import ChunkRepository
from app.services.chunk_persistence_service import ChunkPersistenceService
from app.services.chunk_service import ChunkingService
from app.services.document_processing_service import DocumentProcessingService


@pytest.fixture
def checkpoint_document(db_session, tmp_path, monkeypatch):
    path = tmp_path / "resumable.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Native first page")
        for _ in range(2):
            page = pdf.new_page()
            pixels = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 100), False)
            pixels.clear_with(255)
            page.insert_image(page.rect, pixmap=pixels)
        pdf.new_page()
        pdf.save(path)
    user = User(email=f"checkpoint-{uuid.uuid4()}@example.com", hashed_password="hash")
    document = Document(user=user, filename="stored.pdf", original_filename="scan.pdf",
                        file_path=str(path), content_type="application/pdf", file_size_bytes=path.stat().st_size,
                        status="processing", processing_attempt_id=uuid.uuid4())
    db_session.add(document)
    db_session.flush()
    session = Mock()
    session.recognize.return_value = {"text": "Tài liệu tiếng Việt", "confidence": 0.95}
    monkeypatch.setattr(extraction, "OCRSession", Mock(return_value=session))
    publish = Mock()
    monkeypatch.setattr("app.services.document_progress.document_event_broker.publish", publish)
    monkeypatch.setattr(settings, "pdf_ocr_enabled", True)
    return document, DocumentRepository(db_session), session, publish


def rows(db, document):
    return db.scalars(select(DocumentPageCheckpoint).where(
        DocumentPageCheckpoint.document_id == document.id,
    ).order_by(DocumentPageCheckpoint.page_number)).all()


def test_failed_page_retry_reuses_committed_pages_and_caches_blank_pages(checkpoint_document, db_session):
    document, repository, session, publish = checkpoint_document
    session.recognize.side_effect = [{"text": "First OCR page", "confidence": 0.95},
                                     ValueError("PDF OCR exceeded the configured page or document timeout")]
    with pytest.raises(ValueError, match="timeout"):
        extraction.PdfExtractionService().extract(Path(document.file_path), checkpoint=DocumentProgress(repository, document))
    assert [row.page_number for row in rows(db_session, document)] == [1, 2]
    assert document.processing_progress["completed_pages"] == 2
    assert document.processing_progress["current_page"] == 3
    repository.mark_processing_failed(document, "PDF OCR exceeded the configured page or document timeout")
    db_session.commit()
    assert document.processing_progress["error_code"] == "ocr_timeout"
    previous_attempt = document.processing_attempt_id
    document = repository.claim_retry(document.id, document.user_id)
    assert document.processing_attempt_id != previous_attempt
    session.recognize.reset_mock()
    session.recognize.side_effect = None
    source = extraction.PdfExtractionService().extract(Path(document.file_path), checkpoint=DocumentProgress(repository, document))
    session.recognize.assert_called_once()
    assert session.recognize.call_args.args[0] == 2
    assert [unit.page_number for unit in source.units] == [1, 2, 3]
    assert source.metadata["reused_pages"] == 2
    assert [row.page_number for row in rows(db_session, document)] == [1, 2, 3, 4]
    assert rows(db_session, document)[3].content == ""
    assert document.processing_progress["completed_pages"] == 4
    assert document.processing_progress["total_pages"] == 4
    assert publish.call_args.args[1]["processing_attempt_id"] == str(document.processing_attempt_id)
    session.recognize.reset_mock()
    restored = extraction.PdfExtractionService().extract(Path(document.file_path), checkpoint=DocumentProgress(repository, document))
    session.recognize.assert_not_called()
    assert restored.units == source.units


def test_changed_configuration_invalidates_checkpoint(checkpoint_document, monkeypatch, db_session):
    document, repository, session, _ = checkpoint_document
    service = extraction.PdfExtractionService()
    service.extract(Path(document.file_path), checkpoint=DocumentProgress(repository, document))
    old = rows(db_session, document)[0].fingerprint
    monkeypatch.setattr(settings, "pdf_ocr_min_confidence", 0.75)
    session.recognize.reset_mock()
    source = service.extract(Path(document.file_path), checkpoint=DocumentProgress(repository, document))
    assert session.recognize.call_count == 2
    assert source.metadata["reused_pages"] == 0
    assert rows(db_session, document)[0].fingerprint != old


def test_changed_file_invalidates_checkpoint(checkpoint_document, db_session):
    document, repository, session, _ = checkpoint_document
    service = extraction.PdfExtractionService()
    service.extract(Path(document.file_path), checkpoint=DocumentProgress(repository, document))
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Replacement document")
        pdf.save(document.file_path)
    source = service.extract(Path(document.file_path), checkpoint=DocumentProgress(repository, document))
    assert source.metadata["reused_pages"] == 0
    assert len(rows(db_session, document)) == 1
    assert source.units[0].text == "Replacement document"


def test_cached_text_and_ocr_pages_still_obey_limits(checkpoint_document, monkeypatch):
    document, repository, session, _ = checkpoint_document
    extraction.PdfExtractionService().extract(Path(document.file_path), checkpoint=DocumentProgress(repository, document))
    session.recognize.reset_mock()
    with pytest.raises(ValueError, match="extracted text limit"):
        extraction.PdfExtractionService(max_text_characters=3).extract(
            Path(document.file_path), checkpoint=DocumentProgress(repository, document))
    monkeypatch.setattr(settings, "pdf_ocr_max_pages", 1)
    with pytest.raises(ValueError, match="OCR page limit"):
        extraction.PdfExtractionService().extract(Path(document.file_path), checkpoint=DocumentProgress(repository, document))
    session.recognize.assert_not_called()


def test_old_attempt_cannot_write_progress_or_checkpoint(checkpoint_document, db_session):
    document, repository, _, _ = checkpoint_document
    old = DocumentProgress(repository, document)
    document.processing_attempt_id = uuid.uuid4()
    db_session.commit()
    with pytest.raises(ValueError, match="no longer active"):
        old.begin("0" * 64, 4)
    with pytest.raises(ValueError, match="no longer active"):
        old.report(stage="ocr", current_page=1)
    assert rows(db_session, document) == []


def test_redis_outage_keeps_database_progress_and_does_not_retry_each_page(checkpoint_document):
    document, repository, _, publish = checkpoint_document
    publish.side_effect = RuntimeError("Redis unavailable")
    source = extraction.PdfExtractionService().extract(Path(document.file_path), checkpoint=DocumentProgress(repository, document))
    assert len(source.units) == 3
    assert document.processing_progress["completed_pages"] == 4
    assert publish.call_count == 1


def test_document_delete_cascades_page_text(checkpoint_document, db_session):
    document, repository, _, _ = checkpoint_document
    extraction.PdfExtractionService().extract(Path(document.file_path), checkpoint=DocumentProgress(repository, document))
    identity = document.id
    db_session.delete(document)
    db_session.commit()
    assert db_session.scalars(select(DocumentPageCheckpoint).where(
        DocumentPageCheckpoint.document_id == identity)).all() == []


def test_processing_pipeline_reports_failure_then_resumes_to_ready(checkpoint_document, db_session):
    document, repository, session, _ = checkpoint_document
    embeddings = Mock(embedding_provider="test", embedding_model="test", embedding_dimensions=2048)
    embeddings.embed_passages.side_effect = lambda texts: [[0.1] * 2048 for _ in texts]
    service = DocumentProcessingService(
        extraction_service=extraction.PdfExtractionService(), chunking_service=ChunkingService(),
        embedding_service=embeddings,
        chunk_persistence_service=ChunkPersistenceService(ChunkRepository(db_session)),
        document_repository=repository, unit_of_work=db_session, embedding_batch_size=1,
        checkpoint_factory=lambda row: DocumentProgress(repository, row),
    )
    session.recognize.side_effect = [{"text": "Page two", "confidence": 0.9}, ValueError("OCR timeout")]
    with pytest.raises(ValueError, match="timeout"):
        service.process_document(document.id, Path(document.file_path))
    assert document.status == "processing_failed"
    assert document.processing_progress["error_code"] == "ocr_timeout"
    assert document.processing_progress["completed_pages"] == 2
    embeddings.embed_passages.assert_not_called()
    document = repository.claim_retry(document.id, document.user_id)
    session.recognize.side_effect = None
    session.recognize.reset_mock()
    chunks = service.process_document(document.id, Path(document.file_path))
    assert document.status == "ready"
    assert document.processing_progress["stage"] == "ready"
    assert document.processing_progress["reused_pages"] == 2
    assert document.processing_progress["completed_chunks"] == len(chunks)
    assert document.processing_progress["total_chunks"] == len(chunks)
    assert session.recognize.call_count == 1


def test_progress_is_available_on_document_get_and_list(checkpoint_document, db_session):
    from fastapi.testclient import TestClient
    from app.core.dependencies import get_current_user, get_document_service
    from app.main import app
    from app.repositories.user_repository import UserRepository
    from app.services.document_service import DocumentService

    document, repository, _, _ = checkpoint_document
    progress = DocumentProgress(repository, document)
    progress.report(stage="ocr", current_page=3, completed_pages=2, total_pages=4)
    app.dependency_overrides[get_current_user] = lambda: document.user
    app.dependency_overrides[get_document_service] = lambda: DocumentService(repository, UserRepository(db_session))
    try:
        with TestClient(app) as client:
            detail = client.get(f"/documents/{document.id}")
            assert detail.status_code == 200
            assert detail.json()["processing_progress"]["current_page"] == 3
            listing = client.get("/documents")
            assert listing.status_code == 200
            assert next(row for row in listing.json() if row["id"] == str(document.id))["processing_progress"]["completed_pages"] == 2
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_document_service, None)


@pytest.mark.parametrize("message,stage,expected", [
    ("PDF OCR exceeded timeout", "ocr", "ocr_timeout"),
    ("PDF exceeds the configured OCR page limit", "ocr", "ocr_page_limit"),
    ("OCR models unavailable", "ocr", "ocr_models"),
    ("PDF does not contain extractable text", "extracting", "no_text"),
    ("secret provider credentials and internal URL", "embedding", "embedding_failed"),
])
def test_user_error_codes_do_not_expose_exception_contents(message, stage, expected):
    assert processing_error_code(message, stage) == expected
