from dataclasses import dataclass

from evaluation.evaluators.metrics import calculate_mrr, find_best_rank
from app.services.context_builder_service import ContextCitation
from app.services.retrieval_service import RetrievedChunk


@dataclass(frozen=True)
class CitationEvaluationResult:
    test_id: str
    question_language: str
    hit: bool
    expected_pages: list[int]
    cited_pages: list[int | None]
    matched_pages: list[int]
    best_rank: int | None
    mrr: float


@dataclass(frozen=True)
class CitationIntegrityEvaluationResult:
    test_id: str
    question_language: str
    passed: bool
    citation_count: int
    retrieved_chunk_count: int
    errors: list[str]


class CitationEvaluator:
    def evaluate(
        self,
        test_id: str,
        question_language: str,
        expected_pages: list[int],
        citations: list[ContextCitation],
    ) -> CitationEvaluationResult:
        cited_pages = [
            citation.page_number
            for citation in citations
        ]

        matched_pages = [
            page
            for page in cited_pages
            if page in expected_pages
        ]

        best_rank = find_best_rank(
            expected_pages=expected_pages,
            actual_pages=cited_pages,
        )

        return CitationEvaluationResult(
            test_id=test_id,
            question_language=question_language,
            hit=best_rank is not None,
            expected_pages=expected_pages,
            cited_pages=cited_pages,
            matched_pages=matched_pages,
            best_rank=best_rank,
            mrr=calculate_mrr(best_rank=best_rank),
        )

    def evaluate_integrity(
        self,
        test_id: str,
        question_language: str,
        retrieved_chunks: list[RetrievedChunk],
        citations: list[ContextCitation],
    ) -> CitationIntegrityEvaluationResult:
        errors: list[str] = []

        if len(citations) != len(retrieved_chunks):
            errors.append(
                f"Expected {len(retrieved_chunks)} citations, got {len(citations)}"
            )

        for index, (retrieved_chunk, citation) in enumerate(
            zip(retrieved_chunks, citations),
            start=1,
        ):
            chunk = retrieved_chunk.chunk

            if citation.source_number != index:
                errors.append(
                    f"Source {index}: expected source_number={index},"
                    f"got {citation.source_number}"
                )

            if citation.document_id != chunk.document_id:
                errors.append(
                    f"Source {index}: document_id mismatch"
                )

            if citation.chunk_id != chunk.id:
                errors.append(
                    f"Source {index}: chunk_id mismatch"
                )

            if citation.page_number != chunk.page_number:
                errors.append(
                    f"Source {index}: page_number mismatch"
                )

            if citation.distance != retrieved_chunk.distance:
                errors.append(
                    f"Source {index}: distance mismatch"
                )

        return CitationIntegrityEvaluationResult(
            test_id=test_id,
            question_language=question_language,
            passed=not errors,
            citation_count=len(citations),
            retrieved_chunk_count=len(retrieved_chunks),
            errors=errors,
        )
