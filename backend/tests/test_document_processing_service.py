import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.core.unit_of_work import UnitOfWork
from app.services.chunk_persistence_service import ChunkPersistenceService
from app.services.chunk_service import ChunkingService
from app.services.document_processing_service import DocumentProcessingService
from app.services.embedding_service import EmbeddingService
from app.services.extraction.base import SourceExtractionService
from app.repositories.document_repository import DocumentRepository


def test_process_document_persists_chunks_and_commits() -> None:
    document_id = uuid.uuid4()
    file_path = Path("/tmp/test.pdf")

    document = Mock()
    document_repository = Mock(spec=DocumentRepository)
    extracted_source = Mock()
    first_text_chunk = Mock()
    first_text_chunk.content = "First chunk"

    second_text_chunk = Mock()
    second_text_chunk.content = "Second chunk"

    text_chunks = [first_text_chunk, second_text_chunk]
    persisted_chunks = [Mock(), Mock()]

    embedding_service = Mock(spec=EmbeddingService)
    embedding_service.embedding_provider = "test-provider"
    embedding_service.embedding_model = "test-model"
    embedding_service.embedding_dimensions = 3
    embeddings = [
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6],
    ]
    embedding_service.embed_passages.return_value = embeddings

    extraction_service = Mock(spec=SourceExtractionService)
    chunking_service = Mock(spec=ChunkingService)
    chunk_persistence_service = Mock(spec=ChunkPersistenceService)
    unit_of_work = Mock(spec=UnitOfWork)

    document_repository.get_document_by_id.return_value = document
    extraction_service.extract.return_value = extracted_source
    chunking_service.chunk_source.return_value = text_chunks
    chunk_persistence_service.persist_chunks.return_value = persisted_chunks

    service = DocumentProcessingService(
        document_repository=document_repository,
        extraction_service=extraction_service,
        chunking_service=chunking_service,
        embedding_service=embedding_service,
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
    embedding_service.embed_passages.assert_called_once_with(
        texts=["First chunk", "Second chunk"],
    )
    chunk_persistence_service.persist_chunks.assert_called_once_with(
        document_id=document_id,
        text_chunks=text_chunks,
        embeddings=embeddings,
        embedding_provider="test-provider",
        embedding_model="test-model",
        embedding_dimensions=3,
    )
    document_repository.get_document_by_id.assert_called_once_with(
        document_id=document_id,
    )
    document_repository.mark_processing_started.assert_called_once_with(
        document=document,
    )
    document_repository.mark_processing_completed.assert_called_once_with(
        document=document,
        page_count=extracted_source.metadata.get("page_count"),
    )
    document_repository.mark_processing_failed.assert_not_called()
    assert unit_of_work.commit.call_count == 2
    unit_of_work.rollback.assert_not_called()


def test_process_document_rolls_back_when_persistence_fails() -> None:
    document_id = uuid.uuid4()
    file_path = Path("/tmp/failing.pdf")

    document = Mock()
    document_repository = Mock(spec=DocumentRepository)
    document_repository.get_document_by_id.return_value = document
    extracted_source = Mock()
    first_text_chunk = Mock()
    first_text_chunk.content = "First chunk"

    second_text_chunk = Mock()
    second_text_chunk.content = "Second chunk"

    text_chunks = [first_text_chunk, second_text_chunk]

    embedding_service = Mock(spec=EmbeddingService)
    embedding_service.embedding_provider = "test-provider"
    embedding_service.embedding_model = "test-model"
    embedding_service.embedding_dimensions = 3
    embeddings = [
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6],
    ]
    embedding_service.embed_passages.return_value = embeddings

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
        document_repository=document_repository,
        extraction_service=extraction_service,
        chunking_service=chunking_service,
        embedding_service=embedding_service,
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

    document_repository.get_document_by_id.assert_called_once_with(
        document_id=document_id,
    )
    document_repository.mark_processing_started.assert_called_once_with(
        document=document,
    )
    embedding_service.embed_passages.assert_called_once_with(
        texts=["First chunk", "Second chunk"],
    )
    chunk_persistence_service.persist_chunks.assert_called_once_with(
        document_id=document_id,
        text_chunks=text_chunks,
        embeddings=embeddings,
        embedding_provider="test-provider",
        embedding_model="test-model",
        embedding_dimensions=3,
    )
    document_repository.mark_processing_failed.assert_called_once_with(
        document=document,
        error_message="Could not persist chunks",
    )
    document_repository.mark_processing_completed.assert_not_called()
    assert unit_of_work.commit.call_count == 2
    unit_of_work.rollback.assert_called_once_with()


def test_process_document_raises_when_document_not_found() -> None:
    document_id = uuid.uuid4()
    file_path = Path("/tmp/missing.pdf")

    document_repository = Mock(spec=DocumentRepository)
    extraction_service = Mock(spec=SourceExtractionService)
    chunking_service = Mock(spec=ChunkingService)
    chunk_persistence_service = Mock(spec=ChunkPersistenceService)
    unit_of_work = Mock(spec=UnitOfWork)

    embedding_service = Mock(spec=EmbeddingService)
    embedding_service.embedding_provider = "test-provider"
    embedding_service.embedding_model = "test-model"
    embedding_service.embedding_dimensions = 3

    document_repository.get_document_by_id.return_value = None

    service = DocumentProcessingService(
        document_repository=document_repository,
        extraction_service=extraction_service,
        chunking_service=chunking_service,
        embedding_service=embedding_service,
        chunk_persistence_service=chunk_persistence_service,
        unit_of_work=unit_of_work,
    )

    with pytest.raises(ValueError, match="Document not found"):
        service.process_document(
            document_id=document_id,
            file_path=file_path,
        )

    extraction_service.extract.assert_not_called()
    chunking_service.chunk_source.assert_not_called()
    embedding_service.embed_passages.assert_not_called()
    chunk_persistence_service.persist_chunks.assert_not_called()
    unit_of_work.commit.assert_not_called()
    unit_of_work.rollback.assert_not_called()
