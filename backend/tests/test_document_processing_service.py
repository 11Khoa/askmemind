import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.core.unit_of_work import UnitOfWork
from app.services.chunk_persistence_service import ChunkPersistenceService
from app.services.chunk_service import ChunkingService
from app.services.document_processing_service import DocumentProcessingService
from app.services.extraction.base import SourceExtractionService


def test_process_document_persists_chunks_and_commits() -> None:
    document_id = uuid.uuid4()
    file_path = Path("/tmp/test.pdf")

    extracted_source = Mock()
    text_chunks = [Mock(), Mock()]
    persisted_chunks = [Mock(), Mock()]

    extraction_service = Mock(spec=SourceExtractionService)
    chunking_service = Mock(spec=ChunkingService)
    chunk_persistence_service = Mock(spec=ChunkPersistenceService)
    unit_of_work = Mock(spec=UnitOfWork)

    extraction_service.extract.return_value = extracted_source
    chunking_service.chunk_source.return_value = text_chunks
    chunk_persistence_service.persist_chunks.return_value = persisted_chunks

    service = DocumentProcessingService(
        extraction_service=extraction_service,
        chunking_service=chunking_service,
        chunk_persistence_service=chunk_persistence_service,
        unit_of_work=unit_of_work,
    )

    result = service.process_document(
        document_id=document_id,
        file_path=file_path,
    )

    assert result is persisted_chunks

    extraction_service.extract.assert_called_once_with(file_path=file_path)
    chunking_service.chunk_source.assert_called_once_with(
        source=extracted_source,
    )
    chunk_persistence_service.persist_chunks.assert_called_once_with(
        document_id=document_id,
        text_chunks=text_chunks,
    )
    unit_of_work.commit.assert_called_once_with()
    unit_of_work.rollback.assert_not_called()


def test_process_document_rolls_back_when_persistence_fails() -> None:
    document_id = uuid.uuid4()
    file_path = Path("/tmp/failing.pdf")

    extracted_source = Mock()
    text_chunks = [Mock(), Mock()]

    extraction_service = Mock(spec=SourceExtractionService)
    chunking_service = Mock(spec=ChunkingService)
    chunk_persistence_service = Mock(spec=ChunkPersistenceService)
    unit_of_work = Mock(spec=UnitOfWork)

    extraction_service.extract.return_value = extracted_source
    chunking_service.chunk_source.return_value = text_chunks
    chunk_persistence_service.persist_chunks.side_effect = RuntimeError(
        "Could not persist chunks"
    )

    service = DocumentProcessingService(
        extraction_service=extraction_service,
        chunking_service=chunking_service,
        chunk_persistence_service=chunk_persistence_service,
        unit_of_work=unit_of_work,
    )

    with pytest.raises(
        RuntimeError,
        match="Could not persist chunks",
    ):
        service.process_document(
            document_id=document_id,
            file_path=file_path,
        )

    unit_of_work.rollback.assert_called_once_with()
    unit_of_work.commit.assert_not_called()
