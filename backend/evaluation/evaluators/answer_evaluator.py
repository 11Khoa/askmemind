from dataclasses import dataclass


@dataclass(frozen=True)
class AnswerEvaluationResult:
    test_id: str
    question_language: str
    passed: bool
    answer: str
    expected_keywords: list[str]
    matched_keywords: list[str]
    missing_keywords: list[str]
    keyword_recall: float
    has_answer: bool
    has_citations: bool


class AnswerEvaluator:
    def evaluate(
        self,
        test_id: str,
        question_language: str,
        answer: str,
        expected_keywords: list[str],
        citation_count: int,
    ) -> AnswerEvaluationResult:
        normalized_answer = answer.lower()

        matched_keywords = [
            keyword
            for keyword in expected_keywords
            if keyword.lower() in normalized_answer
        ]

        missing_keywords = [
            keyword
            for keyword in expected_keywords
            if keyword.lower() not in normalized_answer
        ]

        keyword_recall = (
            0.0
            if not expected_keywords
            else len(matched_keywords) / len(expected_keywords)
        )

        has_answer = bool(answer.strip())
        has_citations = citation_count > 0

        passed = (
            has_answer
            and has_citations
            and keyword_recall >= 0.5
        )

        return AnswerEvaluationResult(
            test_id=test_id,
            question_language=question_language,
            passed=passed,
            answer=answer,
            expected_keywords=expected_keywords,
            matched_keywords=matched_keywords,
            missing_keywords=missing_keywords,
            keyword_recall=keyword_recall,
            has_answer=has_answer,
            has_citations=has_citations,
        )
