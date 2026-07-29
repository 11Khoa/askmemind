from unittest.mock import Mock

from app.services.llm_service import LLMProvider, LLMService


def test_generate_answer_calls_provider() -> None:
    provider = Mock(spec=LLMProvider)
    provider.generate_answer.return_value = "Answer from context."

    service = LLMService(provider=provider)

    result = service.generate_answer(
        question="What is the refund policy?",
        context="[Source 1]\nContent:\nRefunds are available within 30 days.",
    )

    assert result == "Answer from context."
    provider.generate_answer.assert_called_once_with(
        question="What is the refund policy?",
        context="[Source 1]\nContent:\nRefunds are available within 30 days.",
    )