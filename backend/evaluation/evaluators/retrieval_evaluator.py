from dataclasses import dataclass

from evaluation.evaluators.metrics import calculate_mrr, find_best_rank
from app.services.retrieval_service import RetrievedChunk


@dataclass(frozen=True)
class RetrievalEvaluationResult:
    test_id: str
    question_language: str
    hit: bool
    expected_pages: list[int]
    retrieved_pages: list[int | None]
    matched_pages: list[int]
    best_rank: int | None
    mrr: float


class RetrievalEvaluator:
    def evaluate(
        self,
        test_id: str,
        question_language: str,
        expected_pages: list[int],
        retrieved_chunks: list[RetrievedChunk],
    ) -> RetrievalEvaluationResult:
        retrieved_pages = [
            retrieved_chunk.chunk.page_number
            for retrieved_chunk in retrieved_chunks
        ]

        matched_pages = [
            page
            for page in retrieved_pages
            if page in expected_pages
        ]

        best_rank = find_best_rank(
            expected_pages=expected_pages,
            actual_pages=retrieved_pages,
        )
        mrr = calculate_mrr(best_rank=best_rank)

        return RetrievalEvaluationResult(
            test_id=test_id,
            question_language=question_language,
            hit=best_rank is not None,
            expected_pages=expected_pages,
            retrieved_pages=retrieved_pages,
            matched_pages=matched_pages,
            best_rank=best_rank,
            mrr=mrr,
        )
