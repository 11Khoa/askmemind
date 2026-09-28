import uuid
from unittest.mock import Mock

import pytest

from app.agents.retrieval_agent import (
    AgentRetrievalResult,
    RetrievalAgent,
    RetrievalAgentState,
)
from app.services.context_builder_service import BuiltContext, ContextBuilderService
from app.services.llm_service import LLMService
from app.services.rag_service import RagService
from app.services.retrieval_service import RetrievedChunk, RetrievalService


def test_rag_uses_agentic_retrieval_when_enabled() -> None:
    user_id = uuid.uuid4()
    chunks = [RetrievedChunk(chunk=Mock(), distance=0.2)]
    state = RetrievalAgentState(
        question="Question",
        rewritten_query="rewritten question",
        documents=chunks,
        retrieval_score=0.9,
        retry_count=1,
        decisions=["rewrite", "accept"],
    )
    retrieval_agent = Mock(spec=RetrievalAgent)
    retrieval_agent.retrieve.return_value = AgentRetrievalResult(
        chunks=chunks,
        state=state,
    )
    retrieval_service = Mock(spec=RetrievalService)
    context_builder = Mock(spec=ContextBuilderService)
    context_builder.build_context.return_value = BuiltContext(
        context="Grounded context",
        citations=[],
    )
    llm_service = Mock(spec=LLMService)
    llm_service.generate_answer.return_value = "Grounded answer"

    service = RagService(
        retrieval_service=retrieval_service,
        context_builder_service=context_builder,
        llm_service=llm_service,
        retrieval_agent=retrieval_agent,
        agentic_retrieval_enabled=True,
    )

    result = service.answer_question(
        question="Question",
        user_id=user_id,
        top_k=3,
    )

    assert result.answer == "Grounded answer"
    retrieval_agent.retrieve.assert_called_once_with(
        question="Question",
        user_id=user_id,
        document_id=None,
        top_k=3,
    )
    retrieval_service.retrieve_relevant_chunks.assert_not_called()


def test_rag_requires_agent_when_agentic_retrieval_is_enabled() -> None:
    service = RagService(
        retrieval_service=Mock(spec=RetrievalService),
        context_builder_service=Mock(spec=ContextBuilderService),
        llm_service=Mock(spec=LLMService),
        agentic_retrieval_enabled=True,
    )

    with pytest.raises(RuntimeError, match="RetrievalAgent is required"):
        service.answer_question(
            question="Question",
            user_id=uuid.uuid4(),
        )
