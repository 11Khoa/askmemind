import re
from dataclasses import dataclass

from app.services.context_builder_service import ContextCitation
from app.services.retrieval_service import RetrievedChunk


_SOURCE_PATTERN = re.compile(r"\[Source\s+(\d+)\]", re.IGNORECASE)


@dataclass(frozen=True)
class CitationValidationResult:
    valid: bool
    cited_source_numbers: tuple[int, ...]
    errors: tuple[str, ...]


class GuardrailService:
    def calculate_confidence(self, result: RetrievedChunk) -> float:
        if result.rerank_score is not None:
            return self._clamp(result.rerank_score)

        if result.distance is not None:
            return self._clamp(1.0 - (result.distance / 2.0))

        if result.score is not None:
            if result.score < 0:
                return 0.0
            return result.score / (1.0 + result.score)

        return 0.0

    def has_sufficient_evidence(
        self,
        retrieved_chunks: list[RetrievedChunk],
        minimum_confidence: float,
    ) -> bool:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")
        if not retrieved_chunks:
            return False

        return max(
            self.calculate_confidence(result)
            for result in retrieved_chunks
        ) >= minimum_confidence

    def validate_answer_citations(
        self,
        answer: str,
        citations: list[ContextCitation],
    ) -> CitationValidationResult:
        source_numbers = tuple(
            dict.fromkeys(
                int(match)
                for match in _SOURCE_PATTERN.findall(answer)
            )
        )
        available_source_numbers = {
            citation.source_number for citation in citations
        }
        errors: list[str] = []

        if not source_numbers:
            errors.append("Answer does not cite any context source")

        unknown_source_numbers = sorted(
            set(source_numbers) - available_source_numbers
        )
        if unknown_source_numbers:
            errors.append(
                "Answer cites unknown sources: "
                + ", ".join(str(number) for number in unknown_source_numbers)
            )

        return CitationValidationResult(
            valid=not errors,
            cited_source_numbers=source_numbers,
            errors=tuple(errors),
        )

    def select_cited_context(
        self,
        citations: list[ContextCitation],
        cited_source_numbers: tuple[int, ...],
    ) -> list[ContextCitation]:
        cited_set = set(cited_source_numbers)
        return [
            citation
            for citation in citations
            if citation.source_number in cited_set
        ]

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(value, 1.0))
