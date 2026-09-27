import re
from dataclasses import replace

from app.services.retrieval_service import RetrievedChunk


class RerankingService:
    def __init__(
        self,
        keyword_weight: float = 0.7,
        rank_weight: float = 0.2,
        phrase_weight: float = 0.1,
    ) -> None:
        weights = (keyword_weight, rank_weight, phrase_weight)
        if any(weight < 0 for weight in weights):
            raise ValueError("Reranking weights must be non-negative")
        if not 0.999 <= sum(weights) <= 1.001:
            raise ValueError("Reranking weights must sum to 1")

        self.keyword_weight = keyword_weight
        self.rank_weight = rank_weight
        self.phrase_weight = phrase_weight

    def rerank(
        self,
        query: str,
        retrieved_chunks: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if not retrieved_chunks:
            return []

        query_tokens = self._tokenize(query)
        normalized_query = self._normalize(query)
        scored_chunks = [
            replace(
                result,
                rerank_score=self._score(
                    query_tokens=query_tokens,
                    normalized_query=normalized_query,
                    content=result.chunk.content,
                    rank=rank,
                ),
            )
            for rank, result in enumerate(retrieved_chunks, start=1)
        ]

        return sorted(
            scored_chunks,
            key=lambda result: result.rerank_score or 0.0,
            reverse=True,
        )[:top_k]

    def _score(
        self,
        query_tokens: set[str],
        normalized_query: str,
        content: str,
        rank: int,
    ) -> float:
        content_tokens = self._tokenize(content)
        keyword_score = (
            len(query_tokens & content_tokens) / len(query_tokens)
            if query_tokens
            else 0.0
        )
        rank_score = 1.0 / rank
        phrase_score = float(
            bool(normalized_query)
            and normalized_query in self._normalize(content)
        )

        return (
            self.keyword_weight * keyword_score
            + self.rank_weight * rank_score
            + self.phrase_weight * phrase_score
        )

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return set(re.findall(r"[^\W_]+", text.casefold()))

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.casefold().split())
