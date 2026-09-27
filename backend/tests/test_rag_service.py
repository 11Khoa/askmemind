import uuid
from unittest.mock import Mock

import pytest

from app.services.context_builder_service import (
    BuiltContext,
    ContextBuilderService,
    ContextCitation,
)
from app.services.llm_service import LLMService
from app.services.rag_service import RagAnswer, RagService
from app.services.retrieval_service import RetrievalService
from app.services.reranking_service import RerankingService


def test_answer_question_retrieves_context_and_generates_answer() -> None:
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    chunk_id = uuid.uuid4()

    retrieved_chunks = [Mock()]
    citations = [
        ContextCitation(
            source_number=1,
            document_id=document_id,
            chunk_id=chunk_id,
            chunk_index=0,
            page_number=3,
            start_time_seconds=None,
            end_time_seconds=None,
            distance=0.12,
        )
    ]
    built_context = BuiltContext(
        context="[Source 1]\nContent:\nRefund policy content.",
        citations=citations,
    )

    retrieval_service = Mock(spec=RetrievalService)
    retrieval_service.retrieve_relevant_chunks.return_value = retrieved_chunks

    context_builder_service = Mock(spec=ContextBuilderService)
    context_builder_service.build_context.return_value = built_context

    llm_service = Mock(spec=LLMService)
    llm_service.generate_answer.return_value = "Refunds are available within 30 days."

    service = RagService(
        retrieval_service=retrieval_service,
        context_builder_service=context_builder_service,
        llm_service=llm_service,
    )

    result = service.answer_question(
        question="What is the refund policy?",
        user_id=user_id,
        document_id=document_id,
        top_k=3,
    )

    retrieval_service.retrieve_relevant_chunks.assert_called_once_with(
        query="What is the refund policy?",
        user_id=user_id,
        document_id=document_id,
        top_k=3,
    )
    context_builder_service.build_context.assert_called_once_with(
        retrieved_chunks=retrieved_chunks,
    )
    llm_service.generate_answer.assert_called_once_with(
        question="What is the refund policy?",
        context="[Source 1]\nContent:\nRefund policy content.",
    )

    assert result == RagAnswer(
        answer="Refunds are available within 30 days.",
        context="[Source 1]\nContent:\nRefund policy content.",
        citations=citations,
    )


def test_answer_question_does_not_call_llm_when_no_chunks_are_retrieved() -> None:
    user_id = uuid.uuid4()

    retrieved_chunks = []

    retrieval_service = Mock(spec=RetrievalService)
    retrieval_service.retrieve_relevant_chunks.return_value = retrieved_chunks

    context_builder_service = Mock(spec=ContextBuilderService)

    llm_service = Mock(spec=LLMService)
    llm_service.generate_answer.assert_not_called()

    service = RagService(
        retrieval_service=retrieval_service,
        context_builder_service=context_builder_service,
        llm_service=llm_service,
    )

    result = service.answer_question(
        question="What does my knowledge base say?",
        user_id=user_id,
    )

    retrieval_service.retrieve_relevant_chunks.assert_called_once_with(
        query="What does my knowledge base say?",
        user_id=user_id,
        document_id=None,
        top_k=3,
    )

    context_builder_service.build_context.assert_not_called()
    llm_service.generate_answer.assert_not_called()
    assert result == RagAnswer(
        answer="I do not know based on the uploaded documents.",
        context="",
        citations=[],
    )

def test_answer_question_reranks_a_larger_candidate_pool() -> None:
    user_id = uuid.uuid4()
    candidates = [Mock() for _ in range(8)]
    reranked_chunks = candidates[:3]
    built_context = BuiltContext(
        context="[Source 1]\nContent:\nRelevant content.",
        citations=[],
    )

    retrieval_service = Mock(spec=RetrievalService)
    retrieval_service.retrieve_relevant_chunks.return_value = candidates
    reranking_service = Mock(spec=RerankingService)
    reranking_service.rerank.return_value = reranked_chunks
    context_builder_service = Mock(spec=ContextBuilderService)
    context_builder_service.build_context.return_value = built_context
    llm_service = Mock(spec=LLMService)
    llm_service.generate_answer.return_value = "Grounded answer."

    service = RagService(
        retrieval_service=retrieval_service,
        context_builder_service=context_builder_service,
        llm_service=llm_service,
        reranking_service=reranking_service,
        reranker_enabled=True,
        reranker_candidate_k=8,
    )

    service.answer_question(
        question="What is relevant?",
        user_id=user_id,
        top_k=3,
    )

    retrieval_service.retrieve_relevant_chunks.assert_called_once_with(
        query="What is relevant?",
        user_id=user_id,
        document_id=None,
        top_k=8,
    )
    reranking_service.rerank.assert_called_once_with(
        query="What is relevant?",
        retrieved_chunks=candidates,
        top_k=3,
    )
    context_builder_service.build_context.assert_called_once_with(
        retrieved_chunks=reranked_chunks,
    )


def test_answer_question_requires_reranking_service_when_enabled() -> None:
    retrieval_service = Mock(spec=RetrievalService)
    retrieval_service.retrieve_relevant_chunks.return_value = [Mock()]

    service = RagService(
        retrieval_service=retrieval_service,
        context_builder_service=Mock(spec=ContextBuilderService),
        llm_service=Mock(spec=LLMService),
        reranker_enabled=True,
    )

    with pytest.raises(
        RuntimeError,
        match="RerankingService is required",
    ):
        service.answer_question(
            question="Question",
            user_id=uuid.uuid4(),
        )
