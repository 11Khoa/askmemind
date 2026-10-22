from pathlib import Path
from unittest.mock import Mock
import uuid
import pytest

import fitz
from sqlalchemy.orm import Session

from app.core.types import DocumentStatus
from app.models.document import Document
from app.models.user import User
from app.models.chunk import Chunk
from app.repositories.document_repository import DocumentRepository
from app.repositories.chunk_repository import ChunkRepository
from app.services.chunk_persistence_service import ChunkPersistenceService
from app.services.chunk_service import ChunkingService
from app.services.document_processing_service import DocumentProcessingService
from app.services.embedding_service import EmbeddingService
from app.services.extraction.pdf_extraction_service import PdfExtractionService


def test_document_processing_pipeline_persists_pdf_chunks(
    db_session: Session,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "processing-pipeline.pdf"

    pdf_document = fitz.open()

    first_page = pdf_document.new_page()
    first_page.insert_text((72, 72), "Content from page one")

    second_page = pdf_document.new_page()
    second_page.insert_text((100, 100), "Content from page two")

    pdf_document.save(pdf_path)
    pdf_document.close()

    user = User(
        email="processing-integration@gmail.com",
        hashed_password="hashed",
    )

    source_document = Document(
        filename="processing-pipeline.pdf",
        original_filename="processing-pipeline.pdf",
        file_path=str(pdf_path),
        content_type="application/pdf",
        file_size_bytes=pdf_path.stat().st_size,
    )

    user.documents.append(source_document)
    db_session.add(user)
    db_session.flush()

    chunk_repository = ChunkRepository(db=db_session)
    document_repository = DocumentRepository(db=db_session)

    chunk_persistence_service = ChunkPersistenceService(
        chunk_repository=chunk_repository,
    )

    embedding_service = Mock(spec=EmbeddingService)
    embedding_service.embedding_provider = "test-provider"
    embedding_service.embedding_model = "test-model"
    embedding_service.embedding_dimensions = 2048
    embedding_service.embed_passages.return_value = [
        [0.1] * 2048,
        [0.2] * 2048,
    ]

    processing_service = DocumentProcessingService(
        extraction_service=PdfExtractionService(),
        chunking_service=ChunkingService(),
        embedding_service=embedding_service,
        chunk_persistence_service=chunk_persistence_service,
        document_repository=document_repository,
        unit_of_work=db_session,
    )

    result = processing_service.process_document(
        document_id=source_document.id,
        file_path=pdf_path,
    )
    db_session.expire_all()

    persisted_chunks = (
        db_session.query(Chunk)
        .filter(Chunk.document_id == source_document.id)
        .order_by(Chunk.chunk_index.asc())
        .all()
    )

    assert len(result) == 2
    assert len(persisted_chunks) == 2

    assert [chunk.chunk_index for chunk in persisted_chunks] == [0, 1]
    assert [chunk.page_number for chunk in persisted_chunks] == [1, 2]
    assert [chunk.content for chunk in persisted_chunks] == [
        "Content from page one",
        "Content from page two",
    ]
    assert [chunk.document_id for chunk in persisted_chunks] == [
        source_document.id,
        source_document.id,
    ]
    assert [chunk.start_char for chunk in persisted_chunks] == [0, 0]
    assert [chunk.end_char for chunk in persisted_chunks] == [21, 21]
    assert [chunk.embedding_v2_provider for chunk in persisted_chunks] == [
        "test-provider",
        "test-provider",
    ]
    assert [chunk.embedding_v2_model for chunk in persisted_chunks] == [
        "test-model",
        "test-model",
    ]
    assert [chunk.embedding_v2_dimensions for chunk in persisted_chunks] == [2048, 2048]
    assert list(persisted_chunks[0].embedding_v2) == [0.1] * 2048
    assert list(persisted_chunks[1].embedding_v2) == [0.2] * 2048
    assert all(chunk.embedding is None for chunk in persisted_chunks)

    persisted_document = db_session.get(Document, source_document.id)

    assert persisted_document is not None
    assert persisted_document.status == DocumentStatus.COMPLETED.value
    assert persisted_document.page_count == 2
    assert persisted_document.error_message is None


def test_failed_batch_resumes_missing_vectors_and_preserves_chunk_ids(
    db_session, tmp_path
):
    pdf_path = tmp_path / "resume.pdf"
    with fitz.open() as pdf:
        for text in ["First content", "Second content", "Third content"]:
            pdf.new_page().insert_text((72, 72), text)
        pdf.save(pdf_path)
    user = User(email=f"resume-{uuid.uuid4()}@example.com", hashed_password="hashed")
    document = Document(
        user=user,
        filename="resume.pdf",
        original_filename="resume.pdf",
        file_path=str(pdf_path),
        content_type="application/pdf",
        file_size_bytes=pdf_path.stat().st_size,
        status="processing",
    )
    db_session.add(document)
    db_session.flush()
    chunks = ChunkRepository(db_session)
    embedding = Mock(spec=EmbeddingService)
    embedding.embedding_provider = "test"
    embedding.embedding_model = "model"
    embedding.embedding_dimensions = 2048
    embedding.embed_passages.side_effect = [
        [[0.1] * 2048],
        RuntimeError("rate limited"),
    ]
    extraction = Mock(wraps=PdfExtractionService())
    service = DocumentProcessingService(
        extraction,
        ChunkingService(),
        embedding,
        ChunkPersistenceService(chunks),
        DocumentRepository(db_session),
        db_session,
        embedding_batch_size=1,
    )

    with pytest.raises(RuntimeError, match="rate limited"):
        service.process_document(document.id, pdf_path)
    saved = chunks.list_chunks_by_document(document.id)
    ids = [chunk.id for chunk in saved]
    assert document.status == "processing_failed"
    assert document.chunk_count == 3
    assert saved[0].embedding_v2 is not None
    assert saved[1].embedding_v2 is None
    # Partial checkpoints must not leak into either retrieval path.
    assert chunks.search_keyword_chunks("content", user.id) == []
    assert chunks.search_similar_chunks([0.1] * 2048, user.id, use_v2=True) == []

    # The checkpoint is sufficient even if the PDF is no longer on disk.
    pdf_path.unlink()
    embedding.embed_passages.side_effect = lambda texts: [[0.2] * 2048 for _ in texts]
    embedding.embed_passages.reset_mock()
    service.process_document(document.id, pdf_path)
    resumed = chunks.list_chunks_by_document(document.id)
    assert [chunk.id for chunk in resumed] == ids
    assert extraction.extract.call_count == 1
    assert embedding.embed_passages.call_count == 2
    assert [
        call.kwargs["texts"] for call in embedding.embed_passages.call_args_list
    ] == [["Second content"], ["Third content"]]
    assert list(resumed[0].embedding_v2) == pytest.approx([0.1] * 2048)
    assert all(chunk.embedding_v2 is not None for chunk in resumed)
    assert document.status == "ready"
    assert len(chunks.search_keyword_chunks("content", user.id)) == 3


def test_legacy_partial_chunks_are_reconciled_not_duplicated(db_session, tmp_path):
    pdf_path = tmp_path / "legacy.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Legacy content")
        pdf.new_page().insert_text((72, 72), "Missing content")
        pdf.save(pdf_path)
    user = User(email=f"legacy-{uuid.uuid4()}@example.com", hashed_password="hashed")
    document = Document(
        user=user,
        filename="legacy.pdf",
        original_filename="legacy.pdf",
        file_path=str(pdf_path),
        content_type="application/pdf",
        file_size_bytes=pdf_path.stat().st_size,
        status="processing_failed",
    )
    db_session.add(document)
    db_session.flush()
    repository = ChunkRepository(db_session)
    old = repository.create_chunks(
        document.id,
        [
            {
                "chunk_index": 0,
                "content": "Legacy content",
                "page_number": 1,
                "start_char": 0,
                "end_char": 14,
                "embedding_v2": [0.1] * 2048,
                "embedding_v2_provider": "test",
                "embedding_v2_model": "model",
                "embedding_v2_dimensions": 2048,
            }
        ],
    )[0]
    old_id = old.id
    embedding = Mock(spec=EmbeddingService)
    embedding.embedding_provider = "test"
    embedding.embedding_model = "model"
    embedding.embedding_dimensions = 2048
    embedding.embed_passages.return_value = [[0.2] * 2048]
    service = DocumentProcessingService(
        PdfExtractionService(),
        ChunkingService(),
        embedding,
        ChunkPersistenceService(repository),
        DocumentRepository(db_session),
        db_session,
    )
    service.process_document(document.id, pdf_path)
    chunks = repository.list_chunks_by_document(document.id)
    assert len(chunks) == 2
    assert chunks[0].id == old_id
    assert list(chunks[0].embedding_v2) == pytest.approx([0.1] * 2048)
    embedding.embed_passages.assert_called_once_with(texts=["Missing content"])
