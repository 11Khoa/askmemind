import uuid
from dataclasses import dataclass

from app.models.chunk import Chunk
from app.repositories.chunk_repository import ChunkRepository
from app.services.embedding_service import EmbeddingService


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    distance: float


class RetrievalService:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        chunk_repository: ChunkRepository,
    ) -> None:
        self.embedding_service = embedding_service
        self.chunk_repository = chunk_repository

    def retrieve_relevant_chunks(
        self,
        query: str,
        user_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        query_embedding = self.embedding_service.embed_query(text=query)

        search_results = self.chunk_repository.search_similar_chunks(
            embedding=query_embedding,
            user_id=user_id,
            document_id=document_id,
            top_k=top_k,
        )

        return [
            RetrievedChunk(
                chunk=chunk,
                distance=distance,
            )
            for chunk, distance in search_results
        ]
