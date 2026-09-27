import uuid
from unittest.mock import Mock

import pytest

from app.services.context_builder_service import ContextCitation
from app.services.guardrail_service import GuardrailService
from app.services.retrieval_service import RetrievedChunk


def make_result(
    distance: float | None = None,
    score: float | None = None,
    rerank_score: float | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Mock(),
        distance=distance,
        score=score,
        rerank_score=rerank_score,
    )


def make_citation(source_number: int) -> ContextCitation:
    return ContextCitation(
        source_number=source_number,
        document_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        chunk_index=source_number - 1,
        page_number=source_number,
        start_time_seconds=None,
        end_time_seconds=None,
        distance=0.1,
    )


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (make_result(rerank_score=0.8, distance=0.9), 0.8),
        (make_result(distance=0.4), 0.8),
        (make_result(score=0.25), 0.2),
        (make_result(), 0.0),
    ],
)
def test_calculate_confidence_normalizes_available_scores(
    result: RetrievedChunk,
    expected: float,
) -> None:
    confidence = GuardrailService().calculate_confidence(result)

    assert confidence == pytest.approx(expected)


def test_has_sufficient_evidence_uses_the_best_candidate() -> None:
    service = GuardrailService()

    assert service.has_sufficient_evidence(
        retrieved_chunks=[
            make_result(distance=1.9),
            make_result(distance=0.4),
        ],
        minimum_confidence=0.5,
    ) is True


def test_validate_answer_citations_rejects_missing_and_unknown_sources() -> None:
    service = GuardrailService()
    citations = [make_citation(source_number=1)]

    missing = service.validate_answer_citations(
        answer="An uncited answer.",
        citations=citations,
    )
    unknown = service.validate_answer_citations(
        answer="An answer [Source 2].",
        citations=citations,
    )

    assert missing.valid is False
    assert missing.errors == ("Answer does not cite any context source",)
    assert unknown.valid is False
    assert unknown.errors == ("Answer cites unknown sources: 2",)


def test_validate_and_select_cited_context() -> None:
    service = GuardrailService()
    first = make_citation(source_number=1)
    second = make_citation(source_number=2)

    validation = service.validate_answer_citations(
        answer="Supported by [Source 2] and again [Source 2].",
        citations=[first, second],
    )
    selected = service.select_cited_context(
        citations=[first, second],
        cited_source_numbers=validation.cited_source_numbers,
    )

    assert validation.valid is True
    assert validation.cited_source_numbers == (2,)
    assert selected == [second]
