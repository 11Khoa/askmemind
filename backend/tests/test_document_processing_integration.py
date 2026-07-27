from pathlib import Path
from unittest.mock import Mock

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
    embedding_service.embedding_dimensions = 1024
    embedding_service.embed_passages.return_value = [
        [0.1] * 1024,
        [0.2] * 1024,
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
    assert [chunk.embedding_provider for chunk in persisted_chunks] == [
        "test-provider",
        "test-provider",
    ]
    assert [chunk.embedding_model for chunk in persisted_chunks] == [
        "test-model",
        "test-model",
    ]
    assert [chunk.embedding_dimensions for chunk in persisted_chunks] == [1024, 1024]
    assert list(persisted_chunks[0].embedding) == [0.1] * 1024
    assert list(persisted_chunks[1].embedding) == [0.2] * 1024

    persisted_document = db_session.get(Document, source_document.id)

    assert persisted_document is not None
    assert persisted_document.status == DocumentStatus.COMPLETED.value
    assert persisted_document.page_count == 2
    assert persisted_document.error_message is None
