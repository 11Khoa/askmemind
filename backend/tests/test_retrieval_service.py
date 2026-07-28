import uuid
from unittest.mock import Mock

from app.repositories.chunk_repository import ChunkRepository
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService, RetrievedChunk


def test_retrieve_relevant_chunks_embeds_query_and_searches_chunks() -> None:
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    query_embedding = [0.1, 0.2, 0.3]

    first_chunk = Mock()
    second_chunk = Mock()

    embedding_service = Mock(spec=EmbeddingService)
    embedding_service.embed_query.return_value = query_embedding

    chunk_repository = Mock(spec=ChunkRepository)
    chunk_repository.search_similar_chunks.return_value = [
        (first_chunk, 0.12),
        (second_chunk, 0.34),
    ]

    service = RetrievalService(
        embedding_service=embedding_service,
        chunk_repository=chunk_repository,
    )

    result = service.retrieve_relevant_chunks(
        query="What is the refund policy?",
        user_id=user_id,
        document_id=document_id,
        top_k=2,
    )

    embedding_service.embed_query.assert_called_once_with(
        text="What is the refund policy?",
    )

    chunk_repository.search_similar_chunks.assert_called_once_with(
        embedding=query_embedding,
        user_id=user_id,
        document_id=document_id,
        top_k=2,
    )

    assert result == [
        RetrievedChunk(chunk=first_chunk, distance=0.12),
        RetrievedChunk(chunk=second_chunk, distance=0.34),
    ]


def test_retrieve_relevant_chunks_can_search_all_user_documents() -> None:
    user_id = uuid.uuid4()
    query_embedding = [0.1, 0.2, 0.3]
    chunk = Mock()

    embedding_service = Mock(spec=EmbeddingService)
    embedding_service.embed_query.return_value = query_embedding

    chunk_repository = Mock(spec=ChunkRepository)
    chunk_repository.search_similar_chunks.return_value = [
        (chunk, 0.2),
    ]

    service = RetrievalService(
        embedding_service=embedding_service,
        chunk_repository=chunk_repository,
    )

    results = service.retrieve_relevant_chunks(
        query="What does my knowledge base say?",
        user_id=user_id,
        document_id=None,
        top_k=5,
    )

    assert results == [
        RetrievedChunk(chunk=chunk, distance=0.2),
    ]
