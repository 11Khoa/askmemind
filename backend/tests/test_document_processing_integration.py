from pathlib import Path

import fitz
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User
from app.models.chunk import Chunk
from app.repositories.chunk_repository import ChunkRepository
from app.services.chunk_persistence_service import ChunkPersistenceService
from app.services.chunk_service import ChunkingService
from app.services.document_processing_service import DocumentProcessingService
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

    chunk_persistence_service = ChunkPersistenceService(
        chunk_repository=chunk_repository,
    )

    processing_service = DocumentProcessingService(
        extraction_service=PdfExtractionService(),
        chunking_service=ChunkingService(),
        chunk_persistence_service=chunk_persistence_service,
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
