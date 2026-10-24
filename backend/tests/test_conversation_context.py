from unittest.mock import Mock
from uuid import uuid4

from app.services.context_builder_service import BuiltContext
from app.services.rag_service import RagService
from app.services.providers.groq_llm_provider import GroqLLMProvider


def test_followup_retrieves_new_evidence_and_passes_history_to_generation():
    retrieval, builder, llm = Mock(), Mock(), Mock()
    retrieval.retrieve_relevant_chunks.return_value = [Mock()]
    builder.build_context.return_value = BuiltContext("Current evidence", [])
    llm.generate_answer.return_value = "Answer"
    llm.stream_answer.return_value = iter(["Answer"])
    service = RagService(retrieval, builder, llm)
    history = [{"role": "user", "content": "What is RRF?"},
               {"role": "assistant", "content": "Reciprocal rank fusion."}]
    service.answer_question("Explain it", uuid4(), history=history)
    query = retrieval.retrieve_relevant_chunks.call_args.kwargs["query"]
    assert "RRF" in query and "Explain it" in query
    assert llm.generate_answer.call_args.kwargs == {
        "question": "Explain it", "context": "Current evidence", "history": history,
    }
    list(service.stream_answer_question("Explain it", uuid4(), history=history))
    assert llm.stream_answer.call_args.kwargs["history"] == history


def test_provider_history_is_dialogue_not_document_evidence():
    provider = GroqLLMProvider("fake", "https://example.com", "fake", 500)
    history = [{"role": "user", "content": "Prior question"},
               {"role": "assistant", "content": "Prior answer [Source 1]"}]
    messages = provider._payload("Follow-up", "New source", history=history)["messages"]
    assert messages[1:3] == history
    assert messages[-1]["content"].endswith("Question:\nFollow-up")
    assert "never evidence" in messages[0]["content"]


def test_empty_combined_lexical_query_falls_back_to_prior_question():
    retrieval, builder, llm = Mock(), Mock(), Mock()
    retrieval.retrieve_relevant_chunks.side_effect = [[], [], [Mock()]]
    builder.build_context.return_value = BuiltContext("Fresh evidence", [])
    llm.generate_answer.return_value = "Answer"
    service = RagService(retrieval, builder, llm)
    service.answer_question("Explain it", uuid4(), history=[
        {"role": "user", "content": "RRF"}, {"role": "assistant", "content": "Rank fusion"},
    ])
    assert [call.kwargs["query"] for call in retrieval.retrieve_relevant_chunks.call_args_list][1:] == ["Explain it", "RRF"]
    assert llm.generate_answer.call_args.kwargs["context"] == "Fresh evidence"
