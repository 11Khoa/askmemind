import uuid
from unittest.mock import Mock, call

from app.agents.retrieval_agent import (
    KeywordQueryRewriteTool,
    RetrievalAgent,
    RetrievalSearchTool,
)
from app.services.guardrail_service import GuardrailService
from app.services.retrieval_service import RetrievedChunk, RetrievalService


def _chunk(distance: float) -> RetrievedChunk:
    return RetrievedChunk(chunk=Mock(), distance=distance)


def test_agent_accepts_sufficient_first_retrieval() -> None:
    user_id = uuid.uuid4()
    chunks = [_chunk(distance=0.2)]
    search_tool = Mock()
    search_tool.search.return_value = chunks
    rewrite_tool = Mock()
    agent = RetrievalAgent(
        search_tool=search_tool,
        rewrite_tool=rewrite_tool,
        guardrail_service=GuardrailService(),
        minimum_confidence=0.5,
    )

    result = agent.retrieve(
        question="What is a DON?",
        user_id=user_id,
        document_id=None,
        top_k=5,
    )

    assert result.chunks == chunks
    assert result.state.retry_count == 0
    assert result.state.decisions == ["accept"]
    rewrite_tool.rewrite.assert_not_called()
    search_tool.search.assert_called_once_with(
        query="What is a DON?",
        user_id=user_id,
        document_id=None,
        top_k=5,
    )


def test_agent_rewrites_and_retries_weak_retrieval() -> None:
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    weak_chunks = [_chunk(distance=1.8)]
    strong_chunks = [_chunk(distance=0.1)]
    search_tool = Mock()
    search_tool.search.side_effect = [weak_chunks, strong_chunks]
    rewrite_tool = Mock()
    rewrite_tool.rewrite.return_value = "DON oracle network"
    agent = RetrievalAgent(
        search_tool=search_tool,
        rewrite_tool=rewrite_tool,
        guardrail_service=GuardrailService(),
        minimum_confidence=0.5,
        max_retries=1,
    )

    result = agent.retrieve(
        question="What is a DON oracle network?",
        user_id=user_id,
        document_id=document_id,
        top_k=3,
    )

    assert result.chunks == strong_chunks
    assert result.state.rewritten_query == "DON oracle network"
    assert result.state.retry_count == 1
    assert result.state.decisions == ["rewrite", "accept"]
    assert search_tool.search.call_args_list == [
        call(
            query="What is a DON oracle network?",
            user_id=user_id,
            document_id=document_id,
            top_k=3,
        ),
        call(
            query="DON oracle network",
            user_id=user_id,
            document_id=document_id,
            top_k=3,
        ),
    ]


def test_agent_stops_at_retry_limit_and_keeps_best_result() -> None:
    first_chunks = [_chunk(distance=1.0)]
    worse_chunks = [_chunk(distance=1.8)]
    search_tool = Mock()
    search_tool.search.side_effect = [first_chunks, worse_chunks]
    rewrite_tool = Mock()
    rewrite_tool.rewrite.return_value = "rewritten query"
    agent = RetrievalAgent(
        search_tool=search_tool,
        rewrite_tool=rewrite_tool,
        guardrail_service=GuardrailService(),
        minimum_confidence=0.9,
        max_retries=1,
    )

    result = agent.retrieve(
        question="original query",
        user_id=uuid.uuid4(),
        document_id=None,
        top_k=3,
    )

    assert result.chunks == first_chunks
    assert result.state.retry_count == 1
    assert result.state.decisions == [
        "rewrite",
        "rewrite",
        "max_retries_reached",
    ]
    assert search_tool.search.call_count == 2


def test_agent_stops_when_rewrite_does_not_change_query() -> None:
    search_tool = Mock()
    search_tool.search.return_value = []
    rewrite_tool = Mock()
    rewrite_tool.rewrite.return_value = "  SAME query  "
    agent = RetrievalAgent(
        search_tool=search_tool,
        rewrite_tool=rewrite_tool,
        guardrail_service=GuardrailService(),
        minimum_confidence=0.5,
        max_retries=2,
    )

    result = agent.retrieve(
        question="same query",
        user_id=uuid.uuid4(),
        document_id=None,
        top_k=3,
    )

    assert result.state.decisions == ["rewrite", "query_unchanged"]
    assert result.state.retry_count == 0
    search_tool.search.assert_called_once()


def test_retrieval_search_tool_forwards_scoped_arguments() -> None:
    retrieval_service = Mock(spec=RetrievalService)
    retrieval_service.retrieve_relevant_chunks.return_value = []
    tool = RetrievalSearchTool(retrieval_service)
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()

    assert tool.search(
        query="query",
        user_id=user_id,
        document_id=document_id,
        top_k=4,
    ) == []
    retrieval_service.retrieve_relevant_chunks.assert_called_once_with(
        query="query",
        user_id=user_id,
        document_id=document_id,
        top_k=4,
    )


def test_keyword_rewrite_removes_question_words_and_duplicates() -> None:
    tool = KeywordQueryRewriteTool()

    assert tool.rewrite(
        "What is the Oracle oracle Network?"
    ) == "oracle network"


def test_keyword_rewrite_removes_accented_vietnamese_stop_words() -> None:
    tool = KeywordQueryRewriteTool()

    assert (
        tool.rewrite("Chainlink được dùng để làm gì trong hệ thống?")
        == "chainlink hệ thống"
    )


def test_keyword_rewrite_removes_unaccented_vietnamese_stop_words() -> None:
    tool = KeywordQueryRewriteTool()

    assert (
        tool.rewrite("Chainlink duoc dung de lam gi trong he thong?")
        == "chainlink he thong"
    )


def test_keyword_rewrite_removes_english_stop_words() -> None:
    tool = KeywordQueryRewriteTool()

    assert tool.rewrite("How can Chainlink work in DeFi?") == "chainlink work defi"


def test_keyword_rewrite_handles_mixed_vietnamese_and_english() -> None:
    tool = KeywordQueryRewriteTool()

    assert (
        tool.rewrite("Chainlink và oracle network được dùng như thế nào?")
        == "chainlink oracle network"
    )


def test_agent_stops_when_keyword_rewrite_keeps_original_query() -> None:
    search_tool = Mock()
    search_tool.search.return_value = []
    user_id = uuid.uuid4()
    agent = RetrievalAgent(
        search_tool=search_tool,
        rewrite_tool=KeywordQueryRewriteTool(),
        guardrail_service=GuardrailService(),
        minimum_confidence=0.5,
        max_retries=2,
    )

    result = agent.retrieve(
        question="Chainlink",
        user_id=user_id,
        document_id=None,
        top_k=3,
    )

    assert result.state.decisions == ["rewrite", "query_unchanged"]
    assert result.state.retry_count == 0
    search_tool.search.assert_called_once_with(
        query="Chainlink",
        user_id=user_id,
        document_id=None,
        top_k=3,
    )
