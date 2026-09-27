import uuid
from unittest.mock import Mock

import pytest

from app.services.reranking_service import RerankingService
from app.services.retrieval_service import RetrievedChunk


def make_result(content: str, distance: float) -> RetrievedChunk:
    chunk = Mock(
        id=uuid.uuid4(),
        content=content,
    )
    return RetrievedChunk(
        chunk=chunk,
        distance=distance,
    )


def test_rerank_promotes_the_stronger_keyword_match() -> None:
    service = RerankingService()
    weak_match = make_result(
        content="An unrelated introduction mentions oracle.",
        distance=0.1,
    )
    strong_match = make_result(
        content=(
            "Hybrid smart contracts combine on-chain code with "
            "off-chain computation."
        ),
        distance=0.2,
    )

    results = service.rerank(
        query="hybrid smart contracts off-chain computation",
        retrieved_chunks=[weak_match, strong_match],
        top_k=2,
    )

    assert [result.chunk for result in results] == [
        strong_match.chunk,
        weak_match.chunk,
    ]
    assert all(result.rerank_score is not None for result in results)


def test_rerank_limits_results_to_top_k() -> None:
    service = RerankingService()
    candidates = [
        make_result(content="oracle networks", distance=0.1),
        make_result(content="smart contracts", distance=0.2),
        make_result(content="off-chain computation", distance=0.3),
    ]

    results = service.rerank(
        query="oracle networks",
        retrieved_chunks=candidates,
        top_k=1,
    )

    assert len(results) == 1
    assert results[0].chunk is candidates[0].chunk


@pytest.mark.parametrize(
    ("weights", "message"),
    [
        ((-0.1, 0.6, 0.5), "must be non-negative"),
        ((0.5, 0.2, 0.1), "must sum to 1"),
    ],
)
def test_reranking_service_rejects_invalid_weights(
    weights: tuple[float, float, float],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        RerankingService(
            keyword_weight=weights[0],
            rank_weight=weights[1],
            phrase_weight=weights[2],
        )


def test_rerank_rejects_non_positive_top_k() -> None:
    service = RerankingService()

    with pytest.raises(ValueError, match="top_k must be at least 1"):
        service.rerank(query="query", retrieved_chunks=[], top_k=0)
