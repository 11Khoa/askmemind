import uuid
from dataclasses import dataclass

from app.models.chunk import Chunk
from app.repositories.chunk_repository import ChunkRepository
from app.services.embedding_service import EmbeddingService


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    distance: float | None
    score: float | None = None


class RetrievalService:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        chunk_repository: ChunkRepository,
        hybrid_search_enabled: bool = False,
    ) -> None:
        self.embedding_service = embedding_service
        self.chunk_repository = chunk_repository
        self.hybrid_search_enabled = hybrid_search_enabled

    def vector_search(
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

    def fts_search(
        self,
        query: str,
        user_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        search_results = self.chunk_repository.search_keyword_chunks(
            query=query,
            user_id=user_id,
            document_id=document_id,
            top_k=top_k,
        )

        return [
            RetrievedChunk(
                chunk=chunk,
                distance=None,
                score=score,
            )
            for chunk, score in search_results
        ]

    def hybrid_search(
        self,
        query: str,
        user_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
        top_k: int = 10,
        vector_weight: float = 0.6,
        lexical_weight: float = 0.4,
        candidate_k: int | None = None,
    ) -> list[RetrievedChunk]:
        candidate_limit = candidate_k if candidate_k is not None else top_k * 2
        candidate_limit = max(candidate_limit, top_k)
        vector_results = self.vector_search(
            query=query,
            user_id=user_id,
            document_id=document_id,
            top_k=candidate_limit,
        )
        lexical_results = self.fts_search(
            query=query,
            user_id=user_id,
            document_id=document_id,
            top_k=candidate_limit,
        )

        fused_results: dict[uuid.UUID, RetrievedChunk] = {}
        fused_scores: dict[uuid.UUID, float] = {}

        self._add_rrf_scores(
            results=vector_results,
            weight=vector_weight,
            fused_results=fused_results,
            fused_scores=fused_scores,
        )
        self._add_rrf_scores(
            results=lexical_results,
            weight=lexical_weight,
            fused_results=fused_results,
            fused_scores=fused_scores,
        )

        ranked_chunk_ids = sorted(
            fused_scores,
            key=lambda chunk_id: fused_scores[chunk_id],
            reverse=True,
        )

        return [
            RetrievedChunk(
                chunk=fused_results[chunk_id].chunk,
                distance=fused_results[chunk_id].distance,
                score=fused_scores[chunk_id],
            )
            for chunk_id in ranked_chunk_ids[:top_k]
        ]

    def retrieve_relevant_chunks(
        self,
        query: str,
        user_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        if self.hybrid_search_enabled:
            return self.hybrid_search(
                query=query,
                user_id=user_id,
                document_id=document_id,
                top_k=top_k,
            )

        return self.vector_search(
            query=query,
            user_id=user_id,
            document_id=document_id,
            top_k=top_k,
        )

    def _add_rrf_scores(
        self,
        results: list[RetrievedChunk],
        weight: float,
        fused_results: dict[uuid.UUID, RetrievedChunk],
        fused_scores: dict[uuid.UUID, float],
        rrf_k: int = 60,
    ) -> None:
        for rank, result in enumerate(results, start=1):
            chunk_id = result.chunk.id

            if chunk_id not in fused_results:
                fused_results[chunk_id] = result

            fused_scores[chunk_id] = (
                fused_scores.get(chunk_id, 0.0) + weight / (rrf_k + rank)
            )
