import uuid
from dataclasses import dataclass

from app.services.context_builder_service import (
    ContextBuilderService,
    ContextCitation,
)
from app.services.llm_service import LLMService
from app.services.retrieval_service import RetrievalService


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
    ) -> None:
        self.retrieval_service = retrieval_service
        self.context_builder_service = context_builder_service
        self.llm_service = llm_service

    def answer_question(
        self,
        question: str,
        user_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
        top_k: int = 3,
    ) -> RagAnswer:
        retrieved_chunks = self.retrieval_service.retrieve_relevant_chunks(
            query=question,
            user_id=user_id,
            document_id=document_id,
            top_k=top_k,
        )
        if not retrieved_chunks:
            return RagAnswer(
                answer="I do not know based on the uploaded documents.",
                context="",
                citations=[],
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
