import uuid
from unittest.mock import Mock

import pytest

from app.repositories.chunk_repository import ChunkRepository
from app.services.chunk_persistence_service import ChunkPersistenceService
from app.services.chunk_service import TextChunk


def test_persist_chunks_maps_text_chunks_and_returns_repository_result() -> None:
    document_id = uuid.uuid4()
    expected_chunks = [Mock(), Mock()]

    chunk_repository = Mock(spec=ChunkRepository)
    chunk_repository.create_chunks.return_value = expected_chunks

    service = ChunkPersistenceService(
        chunk_repository=chunk_repository,
    )

    text_chunks = [
        TextChunk(
            chunk_index=0,
            content="PDF content",
            page_number=2,
            start_char=10,
            end_char=21,
            metadata={"section": "intro"},
        ),
        TextChunk(
            chunk_index=1,
            content="Transcript content",
            start_time_seconds=12.5,
            end_time_seconds=18.0,
            metadata={"speaker": "Khoa"},
        ),
    ]

    result = service.persist_chunks(
        document_id=document_id,
        text_chunks=text_chunks,
        embeddings=[
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6]
        ],
        embedding_provider="test-provider",
        embedding_model="test-model",
        embedding_dimensions=3,
    )

    assert result is expected_chunks

    chunk_repository.create_chunks.assert_called_once_with(
        document_id=document_id,
        chunks_data=[
            {
                "chunk_index": 0,
                "content": "PDF content",
                "page_number": 2,
                "start_char": 10,
                "end_char": 21,
                "start_time_seconds": None,
                "end_time_seconds": None,
                "embedding": [0.1, 0.2, 0.3],
                "embedding_provider": "test-provider",
                "embedding_model": "test-model",
                "embedding_dimensions": 3,
                "chunk_metadata": {"section": "intro"},
            },
            {
                "chunk_index": 1,
                "content": "Transcript content",
                "page_number": None,
                "start_char": None,
                "end_char": None,
                "start_time_seconds": 12.5,
                "end_time_seconds": 18.0,
                "embedding": [0.4, 0.5, 0.6],
                "embedding_provider": "test-provider",
                "embedding_model": "test-model",
                "embedding_dimensions": 3,
                "chunk_metadata": {"speaker": "Khoa"},
            },
        ],
    )

    passed_chunks_data = (
        chunk_repository.create_chunks.call_args.kwargs["chunks_data"]
    )

    assert (
        passed_chunks_data[0]["chunk_metadata"]
        is not text_chunks[0].metadata
    )


def test_persist_chunks_raises_when_embedding_count_does_not_match() -> None:
    document_id = uuid.uuid4()

    chunk_repository = Mock(spec=ChunkRepository)

    service = ChunkPersistenceService(
        chunk_repository=chunk_repository,
    )

    text_chunks = [
        TextChunk(
            chunk_index=0,
            content="PDF content",
            page_number=1,
            start_char=0,
            end_char=11,
            metadata={},
        ),
    ]

    with pytest.raises(
        ValueError,
        match="Text chunks and embeddings must have the same length",
    ):
        service.persist_chunks(
            document_id=document_id,
            text_chunks=text_chunks,
            embeddings=[],
            embedding_provider="test-provider",
            embedding_model="test-model",
            embedding_dimensions=3,
        )

    chunk_repository.create_chunks.assert_not_called()
