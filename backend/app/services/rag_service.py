import uuid
from dataclasses import dataclass

from app.services.context_builder_service import (
    ContextBuilderService,
    ContextCitation,
)
from app.services.llm_service import LLMService
from app.services.retrieval_service import RetrievalService
from app.services.reranking_service import RerankingService


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
    ) -> None:
        self.retrieval_service = retrieval_service
        self.context_builder_service = context_builder_service
        self.llm_service = llm_service
        self.reranking_service = reranking_service
        self.reranker_enabled = reranker_enabled
        self.reranker_candidate_k = reranker_candidate_k

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
            return RagAnswer(
                answer="I do not know based on the uploaded documents.",
                context="",
                citations=[],
            )

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

        built_context = self.context_builder_service.build_context(
            retrieved_chunks=retrieved_chunks,
        )

        answer = self.llm_service.generate_answer(
            question=question,
            context=built_context.context,
        )

        return RagAnswer(
            answer=answer,
            context=built_context.context,
            citations=built_context.citations,
        )
