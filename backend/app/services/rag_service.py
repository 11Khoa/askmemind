import uuid
from dataclasses import dataclass

from app.services.context_builder_service import (
    ContextBuilderService,
    ContextCitation,
)
from app.services.guardrail_service import GuardrailService
from app.services.llm_service import LLMService
from app.services.retrieval_service import RetrievalService
from app.services.reranking_service import RerankingService


NO_ANSWER_MESSAGE = "I do not know based on the uploaded documents."


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    context: str
    citations: list[ContextCitation]


class RagService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        context_builder_service: ContextBuilderService,
        llm_service: LLMService,
        reranking_service: RerankingService | None = None,
        reranker_enabled: bool = False,
        reranker_candidate_k: int = 20,
        guardrail_service: GuardrailService | None = None,
        retrieval_min_confidence: float = 0.0,
        citation_validation_enabled: bool = False,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.context_builder_service = context_builder_service
        self.llm_service = llm_service
        self.reranking_service = reranking_service
        self.reranker_enabled = reranker_enabled
        self.reranker_candidate_k = reranker_candidate_k
        self.guardrail_service = guardrail_service
        self.retrieval_min_confidence = retrieval_min_confidence
        self.citation_validation_enabled = citation_validation_enabled

    def answer_question(
        self,
        question: str,
        user_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
        top_k: int = 3,
    ) -> RagAnswer:
        retrieval_limit = (
            max(top_k, self.reranker_candidate_k)
            if self.reranker_enabled
            else top_k
        )
        retrieved_chunks = self.retrieval_service.retrieve_relevant_chunks(
            query=question,
            user_id=user_id,
            document_id=document_id,
            top_k=retrieval_limit,
        )
        if not retrieved_chunks:
            return self._no_answer()

        if self.reranker_enabled:
            if self.reranking_service is None:
                raise RuntimeError(
                    "RerankingService is required when reranking is enabled"
                )
            retrieved_chunks = self.reranking_service.rerank(
                query=question,
                retrieved_chunks=retrieved_chunks,
                top_k=top_k,
            )

        if self.retrieval_min_confidence > 0:
            guardrail_service = self._require_guardrail_service()
            if not guardrail_service.has_sufficient_evidence(
                retrieved_chunks=retrieved_chunks,
                minimum_confidence=self.retrieval_min_confidence,
            ):
                return self._no_answer()

        built_context = self.context_builder_service.build_context(
            retrieved_chunks=retrieved_chunks,
        )

        answer = self.llm_service.generate_answer(
            question=question,
            context=built_context.context,
        )

        citations = built_context.citations
        if self.citation_validation_enabled:
            guardrail_service = self._require_guardrail_service()
            validation = guardrail_service.validate_answer_citations(
                answer=answer,
                citations=citations,
            )
            if not validation.valid:
                return self._no_answer()
            citations = guardrail_service.select_cited_context(
                citations=citations,
                cited_source_numbers=validation.cited_source_numbers,
            )

        return RagAnswer(
            answer=answer,
            context=built_context.context,
            citations=citations,
        )

    def _require_guardrail_service(self) -> GuardrailService:
        if self.guardrail_service is None:
            raise RuntimeError(
                "GuardrailService is required when guardrails are enabled"
            )
        return self.guardrail_service

    @staticmethod
    def _no_answer() -> RagAnswer:
        return RagAnswer(
            answer=NO_ANSWER_MESSAGE,
            context="",
            citations=[],
        )
