import uuid
from collections.abc import Sequence

from app.models.chunk import Chunk
from app.repositories.chunk_repository import ChunkRepository
from app.services.chunk_service import TextChunk


class ChunkPersistenceService:
    def __init__(self, chunk_repository: ChunkRepository) -> None:
        self.chunk_repository = chunk_repository

    def persist_chunks(
        self,
        document_id: uuid.UUID,
        text_chunks: Sequence[TextChunk],
        embeddings: Sequence[list[float]],
        embedding_provider: str,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> list[Chunk]:
        if len(text_chunks) != len(embeddings):
            raise ValueError("Text chunks and embeddings must have the same length")
        chunks_data = [
            {
                "chunk_index": text_chunk.chunk_index,
                "content": text_chunk.content,
                "page_number": text_chunk.page_number,
                "start_char": text_chunk.start_char,
                "end_char": text_chunk.end_char,
                "start_time_seconds": text_chunk.start_time_seconds,
                "end_time_seconds": text_chunk.end_time_seconds,
                "embedding": embedding,
                "embedding_provider": embedding_provider,
                "embedding_model": embedding_model,
                "embedding_dimensions": embedding_dimensions,
                "chunk_metadata": dict(text_chunk.metadata),
            }
            for text_chunk, embedding in zip(text_chunks, embeddings)
        ]
        return self.chunk_repository.create_chunks(
            document_id=document_id,
            chunks_data=chunks_data,
        )
