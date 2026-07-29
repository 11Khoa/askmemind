from typing import Any

import httpx

from app.services.providers.groq_llm_provider import GroqLLMProvider


class FakeResponse:
    def __init__(
        self,
        payload: dict[str, Any],
    ) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


def test_generate_answer_sends_chat_completion_request(monkeypatch) -> None:
    captured_request: dict[str, Any] = {}

    def fake_post(
        url: str,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: float,
    ) -> FakeResponse:
        captured_request["url"] = url
        captured_request["headers"] = headers
        captured_request["json"] = json
        captured_request["timeout"] = timeout

        return FakeResponse(
            payload={
                "choices": [
                    {
                        "message": {
                            "content": "Refunds are available within 30 days.",
                        },
                    },
                ],
            }
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    provider = GroqLLMProvider(
        api_key="groq-api-key",
        base_url="https://api.groq.com/openai/v1/",
        model="openai/gpt-oss-120b",
        max_tokens=500,
    )

    result = provider.generate_answer(
        question="What is the refund policy?",
        context="[Source 1]\nContent:\nRefunds are available within 30 days.",
    )

    assert result == "Refunds are available within 30 days."
    assert captured_request["url"] == (
        "https://api.groq.com/openai/v1/chat/completions"
    )
    assert captured_request["headers"]["Authorization"] == "Bearer groq-api-key"
    assert captured_request["json"]["model"] == "openai/gpt-oss-120b"
    assert captured_request["json"]["max_tokens"] == 500
    assert captured_request["timeout"] == 30.0
    assert "messages" in captured_request["json"]
    assert "message" not in captured_request["json"]
    assert captured_request["json"]["messages"][0]["role"] == "system"
    assert captured_request["json"]["messages"][0]["content"]
    assert captured_request["json"]["messages"][1] == {
        "role": "user",
        "content": (
            "Context:\n"
            "[Source 1]\nContent:\nRefunds are available within 30 days.\n\n"
            "Question:\n"
            "What is the refund policy?"
        ),
    }