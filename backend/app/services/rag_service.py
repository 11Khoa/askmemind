import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from time import perf_counter

from app.agents.retrieval_agent import RetrievalAgent
from app.core.logging import log_event
from app.services.context_builder_service import (
    BuiltContext,
    ContextBuilderService,
    ContextCitation,
)
from app.services.guardrail_service import GuardrailService
from app.services.llm_service import LLMService
from app.services.retrieval_service import RetrievedChunk, RetrievalService
from app.services.reranking_service import RerankingService

logger = logging.getLogger(__name__)


NO_ANSWER_MESSAGE = "I do not know based on the uploaded documents."


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    context: str
    citations: list[ContextCitation]


@dataclass(frozen=True)
class RagStreamEvent:
    event: str
    token: str | None = None
    answer: RagAnswer | None = None


@dataclass(frozen=True)
class PreparedRagContext:
    total_started_at: float
    retrieved_chunks: list[RetrievedChunk]
    candidate_count: int
    built_context: BuiltContext
    best_confidence: float | None


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
        retrieval_agent: RetrievalAgent | None = None,
        agentic_retrieval_enabled: bool = False,
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

        self.retrieval_agent = retrieval_agent
        self.agentic_retrieval_enabled = agentic_retrieval_enabled

    def answer_question(
        self,
        question: str,
        user_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
        top_k: int = 3,
    ) -> RagAnswer:
        prepared = self._prepare_context(
            question=question,
            user_id=user_id,
            document_id=document_id,
            top_k=top_k,
        )
        if isinstance(prepared, RagAnswer):
            return prepared

        llm_started_at = perf_counter()
        answer = self.llm_service.generate_answer(
            question=question,
            context=prepared.built_context.context,
        )
        llm_latency_ms = (perf_counter() - llm_started_at) * 1000
        log_event(
            logger,
            logging.INFO,
            "rag.llm.completed",
            llm_latency_ms=round(llm_latency_ms, 2),
            answer_characters=len(answer),
        )

        return self._finish_answer(
            answer=answer,
            prepared=prepared,
        )

    def stream_answer_question(
        self,
        question: str,
        user_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
        top_k: int = 3,
    ) -> Iterator[RagStreamEvent]:
        prepared = self._prepare_context(
            question=question,
            user_id=user_id,
            document_id=document_id,
            top_k=top_k,
        )
        if isinstance(prepared, RagAnswer):
            yield RagStreamEvent(event="replace", token=prepared.answer)
            yield RagStreamEvent(event="final", answer=prepared)
            return

        answer_chunks: list[str] = []
        llm_started_at = perf_counter()
        for token in self.llm_service.stream_answer(
            question=question,
            context=prepared.built_context.context,
        ):
            answer_chunks.append(token)
            yield RagStreamEvent(event="token", token=token)

        answer = "".join(answer_chunks)
        llm_latency_ms = (perf_counter() - llm_started_at) * 1000
        log_event(
            logger,
            logging.INFO,
            "rag.llm.stream.completed",
            llm_latency_ms=round(llm_latency_ms, 2),
            answer_characters=len(answer),
        )

        final_answer = self._finish_answer(
            answer=answer,
            prepared=prepared,
            validate_citations=False,
        )
        yield RagStreamEvent(event="final", answer=final_answer)

    def _prepare_context(
        self,
        question: str,
        user_id: uuid.UUID,
        document_id: uuid.UUID | None,
        top_k: int,
    ) -> PreparedRagContext | RagAnswer:
        total_started_at = perf_counter()
        retrieval_limit = (
            max(top_k, self.reranker_candidate_k)
            if self.reranker_enabled
            else top_k
        )
        retrieval_started_at = perf_counter()
        if self.agentic_retrieval_enabled:
            if self.retrieval_agent is None:
                raise RuntimeError(
                    "RetrievalAgent is required when agentic retrieval is enabled"
                )
            agent_result = self.retrieval_agent.retrieve(
                question=question,
                user_id=user_id,
                document_id=document_id,
                top_k=retrieval_limit,
            )
            retrieved_chunks = agent_result.chunks
            log_event(
                logger,
                logging.INFO,
                "rag.agent.completed",
                retry_count=agent_result.state.retry_count,
                rewritten_query=agent_result.state.rewritten_query,
                retrieval_score=round(
                    agent_result.state.retrieval_score,
                    4,
                ),
                decisions=agent_result.state.decisions,
            )
        else:
            retrieved_chunks = self.retrieval_service.retrieve_relevant_chunks(
                query=question,
                user_id=user_id,
                document_id=document_id,
                top_k=retrieval_limit,
            )
        retrieval_latency_ms = (perf_counter() - retrieval_started_at) * 1000
        candidate_count = len(retrieved_chunks)
        log_event(
            logger,
            logging.INFO,
            "rag.retrieval.completed",
            retrieval_method=self.retrieval_service.active_method,
            retrieval_latency_ms=round(retrieval_latency_ms, 2),
            retrieved_chunks=candidate_count,
            candidate_limit=retrieval_limit,
        )
        if not retrieved_chunks:
            return self._fallback(
                reason="no_context",
                total_started_at=total_started_at,
                retrieved_chunks=0,
            )
        if self.reranker_enabled:
            if self.reranking_service is None:
                raise RuntimeError(
                    "RerankingService is required when reranking is enabled"
                )
            reranking_started_at = perf_counter()
            retrieved_chunks = self.reranking_service.rerank(
                query=question,
                retrieved_chunks=retrieved_chunks,
                top_k=top_k,
            )
            reranking_latency_ms = (
                perf_counter() - reranking_started_at
            ) * 1000
            log_event(
                logger,
                logging.INFO,
                "rag.reranking.completed",
                reranking_latency_ms=round(reranking_latency_ms, 2),
                reranked_chunks=len(retrieved_chunks),
            )

        best_confidence: float | None = None
        if self.guardrail_service is not None:
            best_confidence = max(
                self.guardrail_service.calculate_confidence(result)
                for result in retrieved_chunks
            )

        if self.retrieval_min_confidence > 0:
            guardrail_service = self._require_guardrail_service()
            if not guardrail_service.has_sufficient_evidence(
                retrieved_chunks=retrieved_chunks,
                minimum_confidence=self.retrieval_min_confidence,
            ):
                return self._fallback(
                    reason="low_confidence",
                    total_started_at=total_started_at,
                    retrieved_chunks=len(retrieved_chunks),
                    best_confidence=best_confidence,
                )

        built_context = self.context_builder_service.build_context(
            retrieved_chunks=retrieved_chunks,
        )

        return PreparedRagContext(
            total_started_at=total_started_at,
            retrieved_chunks=retrieved_chunks,
            candidate_count=candidate_count,
            built_context=built_context,
            best_confidence=best_confidence,
        )

    def _finish_answer(
        self,
        answer: str,
        prepared: PreparedRagContext,
        validate_citations: bool = True,
    ) -> RagAnswer:
        citations = prepared.built_context.citations
        if self.citation_validation_enabled and validate_citations:
            guardrail_service = self._require_guardrail_service()
            validation = guardrail_service.validate_answer_citations(
                answer=answer,
                citations=citations,
            )
            if not validation.valid:
                return self._fallback(
                    reason="invalid_citations",
                    total_started_at=prepared.total_started_at,
                    retrieved_chunks=len(prepared.retrieved_chunks),
                    best_confidence=prepared.best_confidence,
                    citation_errors=list(validation.errors),
                )
            citations = guardrail_service.select_cited_context(
                citations=citations,
                cited_source_numbers=validation.cited_source_numbers,
            )

        total_latency_ms = (perf_counter() - prepared.total_started_at) * 1000
        log_event(
            logger,
            logging.INFO,
            "rag.completed",
            retrieval_method=self.retrieval_service.active_method,
            total_latency_ms=round(total_latency_ms, 2),
            retrieved_chunks=prepared.candidate_count,
            final_chunks=len(prepared.retrieved_chunks),
            best_confidence=prepared.best_confidence,
            fallback=False,
        )

        return RagAnswer(
            answer=answer,
            context=prepared.built_context.context,
            citations=citations,
        )

    def _fallback(
        self,
        reason: str,
        total_started_at: float,
        retrieved_chunks: int,
        best_confidence: float | None = None,
        citation_errors: list[str] | None = None,
    ) -> RagAnswer:
        total_latency_ms = (perf_counter() - total_started_at) * 1000
        log_event(
            logger,
            logging.WARNING,
            "rag.fallback",
            retrieval_method=self.retrieval_service.active_method,
            total_latency_ms=round(total_latency_ms, 2),
            retrieved_chunks=retrieved_chunks,
            best_confidence=best_confidence,
            fallback=True,
            fallback_reason=reason,
            citation_errors=citation_errors or [],
        )
        return self._no_answer()

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
