import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.repositories.document_repository import DocumentRepository
from app.services.chunk_persistence_service import ChunkPersistenceService
from app.services.document_processing_service import DocumentProcessingService


def make_service(chunk_count=2, batch_size=1):
    document = SimpleNamespace(chunk_count=chunk_count, page_count=3)
    repository = Mock(spec=DocumentRepository)
    repository.get_document_by_id.return_value = document
    persistence = Mock(spec=ChunkPersistenceService)
    chunks = [
        SimpleNamespace(chunk_index=index, content=f"Chunk {index}", embedding_v2=None)
        for index in range(2)
    ]
    persistence.list_chunks.return_value = chunks
    embedding = Mock(
        embedding_provider="test", embedding_model="model", embedding_dimensions=3
    )
    embedding.embed_passages.side_effect = lambda texts: [
        [0.1, 0.2, 0.3] for _ in texts
    ]
    service = DocumentProcessingService(
        extraction_service=Mock(),
        chunking_service=Mock(),
        embedding_service=embedding,
        chunk_persistence_service=persistence,
        document_repository=repository,
        unit_of_work=Mock(),
        embedding_batch_size=batch_size,
    )
    return service, document, chunks


def test_complete_chunks_resume_without_reading_pdf():
    service, document, chunks = make_service()
    result = service.process_document(uuid.uuid4(), Path("/missing.pdf"))
    assert result is chunks
    service.extraction_service.extract.assert_not_called()
    assert service.embedding_service.embed_passages.call_count == 2
    assert service.chunk_persistence_service.save_embeddings.call_count == 2
    assert service.unit_of_work.commit.call_count == 4
    service.document_repository.mark_processing_completed.assert_called_once_with(
        document=document, page_count=3
    )


def test_complete_vectors_are_not_embedded_again():
    service, _, chunks = make_service()
    for chunk in chunks:
        chunk.embedding_v2 = [0.1] * 3
        chunk.embedding_v2_provider = "test"
        chunk.embedding_v2_model = "model"
        chunk.embedding_v2_dimensions = 3
    service.process_document(uuid.uuid4(), Path("/missing.pdf"))
    service.embedding_service.embed_passages.assert_not_called()


def test_wrong_model_vector_is_replaced():
    service, _, chunks = make_service()
    for chunk in chunks:
        chunk.embedding_v2 = [0.1] * 3
        chunk.embedding_v2_provider = "test"
        chunk.embedding_v2_model = "old-model"
        chunk.embedding_v2_dimensions = 3
    service.process_document(uuid.uuid4(), Path("/missing.pdf"))
    assert service.embedding_service.embed_passages.call_count == 2


def test_batch_failure_keeps_earlier_commits_and_marks_failed():
    service, document, _ = make_service()
    service.embedding_service.embed_passages.side_effect = [
        [[0.1] * 3],
        RuntimeError("provider unavailable"),
    ]
    with pytest.raises(RuntimeError, match="provider unavailable"):
        service.process_document(uuid.uuid4(), Path("/missing.pdf"))
    service.unit_of_work.rollback.assert_called_once()
    assert service.chunk_persistence_service.save_embeddings.call_count == 1
    service.document_repository.mark_processing_failed.assert_called_once_with(
        document=document, error_message="provider unavailable"
    )
    service.document_repository.mark_processing_completed.assert_not_called()


@pytest.mark.parametrize("checkpoint", [None, 1, 3, 0])
def test_incomplete_chunks_require_original_file(checkpoint):
    service, _, _ = make_service(chunk_count=checkpoint)
    with pytest.raises(ValueError, match="Original PDF is unavailable"):
        service.process_document(uuid.uuid4(), Path("/missing.pdf"))
    service.embedding_service.embed_passages.assert_not_called()


def test_process_document_raises_when_document_not_found():
    service, _, _ = make_service()
    service.document_repository.get_document_by_id.return_value = None
    with pytest.raises(ValueError, match="Document not found"):
        service.process_document(uuid.uuid4(), Path("/missing.pdf"))
    service.unit_of_work.commit.assert_not_called()
