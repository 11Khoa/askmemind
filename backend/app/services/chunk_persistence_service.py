import uuid
from collections.abc import Sequence

from app.models.chunk import Chunk
from app.repositories.chunk_repository import ChunkRepository
from app.services.chunk_service import TextChunk


class ChunkPersistenceService:
    def __init__(self, chunk_repository: ChunkRepository) -> None:
        self.chunk_repository = chunk_repository

    def list_chunks(self, document_id: uuid.UUID) -> list[Chunk]:
        return self.chunk_repository.list_chunks_by_document(document_id)

    def prepare_chunks(
        self, document_id: uuid.UUID, text_chunks: Sequence[TextChunk]
    ) -> list[Chunk]:
        existing = {chunk.chunk_index: chunk for chunk in self.list_chunks(document_id)}
        prepared = []
        missing = []
        for text_chunk in text_chunks:
            chunk = existing.pop(text_chunk.chunk_index, None)
            fields = {
                "content": text_chunk.content,
                "page_number": text_chunk.page_number,
                "start_char": text_chunk.start_char,
                "end_char": text_chunk.end_char,
                "start_time_seconds": text_chunk.start_time_seconds,
                "end_time_seconds": text_chunk.end_time_seconds,
            }
            if chunk is None:
                missing.append(
                    {
                        "chunk_index": text_chunk.chunk_index,
                        **fields,
                        "chunk_metadata": dict(text_chunk.metadata),
                    }
                )
            else:
                if any(getattr(chunk, key) != value for key, value in fields.items()):
                    # Never reuse a vector after its source text/position changes.
                    for column in (
                        "embedding",
                        "embedding_provider",
                        "embedding_model",
                        "embedding_dimensions",
                        "embedding_v2",
                        "embedding_v2_provider",
                        "embedding_v2_model",
                        "embedding_v2_dimensions",
                    ):
                        setattr(chunk, column, None)
                for key, value in fields.items():
                    setattr(chunk, key, value)
                chunk.chunk_metadata = dict(text_chunk.metadata)
                prepared.append(chunk)
        self.chunk_repository.delete_chunks(list(existing.values()))
        if missing:
            prepared.extend(self.chunk_repository.create_chunks(document_id, missing))
        return sorted(prepared, key=lambda chunk: chunk.chunk_index)

    def save_embeddings(
        self,
        chunks: Sequence[Chunk],
        embeddings: Sequence[list[float]],
        provider: str,
        model: str,
        dimensions: int,
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Text chunks and embeddings must have the same length")
        if any(len(vector) != dimensions for vector in embeddings):
            raise ValueError("Unexpected embedding dimensions")
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding_v2 = embedding
            chunk.embedding_v2_provider = provider
            chunk.embedding_v2_model = model
            chunk.embedding_v2_dimensions = dimensions

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
                "embedding_v2": embedding,
                "embedding_v2_provider": embedding_provider,
                "embedding_v2_model": embedding_model,
                "embedding_v2_dimensions": embedding_dimensions,
                "chunk_metadata": dict(text_chunk.metadata),
            }
            for text_chunk, embedding in zip(text_chunks, embeddings)
        ]
        return self.chunk_repository.create_chunks(
            document_id=document_id,
            chunks_data=chunks_data,
        )
