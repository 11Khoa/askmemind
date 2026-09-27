from unittest.mock import Mock

import pytest

from app.services.retrieval_service import RetrievedChunk
from evaluation.evaluators.retrieval_evaluator import RetrievalEvaluator


def make_retrieved_chunk(page_number: int | None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Mock(page_number=page_number),
        distance=0.1,
    )


def test_evaluate_calculates_recall_precision_latency_and_chunk_count() -> None:
    evaluator = RetrievalEvaluator()
    retrieved_chunks = [
        make_retrieved_chunk(page_number=1),
        make_retrieved_chunk(page_number=1),
        make_retrieved_chunk(page_number=3),
        make_retrieved_chunk(page_number=None),
    ]

    result = evaluator.evaluate(
        test_id="case_001",
        question_language="en",
        expected_pages=[1, 2],
        retrieved_chunks=retrieved_chunks,
        latency_ms=12.5,
    )

    assert result.hit is True
    assert result.best_rank == 1
    assert result.mrr == 1.0
    assert result.recall_at_k == pytest.approx(0.5)
    assert result.precision_at_k == pytest.approx(0.5)
    assert result.latency_ms == 12.5
    assert result.retrieved_chunk_count == 4


def test_evaluate_handles_empty_expected_and_retrieved_pages() -> None:
    result = RetrievalEvaluator().evaluate(
        test_id="case_002",
        question_language="en",
        expected_pages=[],
        retrieved_chunks=[],
    )

    assert result.recall_at_k == 0.0
    assert result.precision_at_k == 0.0
