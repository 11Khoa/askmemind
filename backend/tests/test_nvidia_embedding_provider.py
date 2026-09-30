from typing import Any

import httpx

from app.services.providers.nvidia_embedding_provider import NvidiaEmbeddingProvider


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


def test_embed_passages_sends_passage_input_type(monkeypatch) -> None:
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
                "data": [
                    {"embedding": [0.1, 0.2, 0.3]},
                    {"embedding": [0.4, 0.5, 0.6]},
                ]
            }
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    provider = NvidiaEmbeddingProvider(
        api_key="api-key",
        base_url="https://example.com/v1/",
        model="test-model",
        dimensions=1024,
    )

    result = provider.embed_passages(texts=["first", "second"])

    assert result == [
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6],
    ]
    assert captured_request["url"] == "https://example.com/v1/embeddings"
    assert captured_request["headers"]["Authorization"] == "Bearer api-key"
    assert captured_request["headers"]["Content-Type"] == "application/json"
    assert captured_request["json"] == {
        "model": "test-model",
        "input": ["first", "second"],
        "input_type": "passage",
        "dimensions": 1024,
    }
    assert captured_request["timeout"] == 30.0


def test_embed_passages_batches_large_requests(monkeypatch) -> None:
    captured_batches: list[list[str]] = []

    def fake_post(
        url: str,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: float,
    ) -> FakeResponse:
        captured_batches.append(list(json["input"]))
        return FakeResponse(
            payload={
                "data": [
                    {"embedding": [float(index)]}
                    for index, _ in enumerate(json["input"])
                ]
            }
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    provider = NvidiaEmbeddingProvider(
        api_key="api-key",
        base_url="https://example.com/v1/",
        model="test-model",
        dimensions=1024,
        batch_size=2,
    )

    result = provider.embed_passages(texts=["first", "second", "third"])

    assert result == [[0.0], [1.0], [0.0]]
    assert captured_batches == [["first", "second"], ["third"]]


def test_embed_query_sends_query_input_type(monkeypatch) -> None:
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
                "data": [
                    {"embedding": [0.7, 0.8, 0.9]},
                ]
            }
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    provider = NvidiaEmbeddingProvider(
        api_key="api-key",
        base_url="https://example.com/v1",
        model="test-model",
        dimensions=1024,
    )

    result = provider.embed_query(text="What is this?")

    assert result == [0.7, 0.8, 0.9]
    assert captured_request["url"] == "https://example.com/v1/embeddings"
    assert captured_request["headers"]["Authorization"] == "Bearer api-key"
    assert captured_request["json"] == {
        "model": "test-model",
        "input": ["What is this?"],
        "input_type": "query",
        "dimensions": 1024,
    }
    assert captured_request["timeout"] == 30.0


def test_embed_failure_includes_response_body(monkeypatch) -> None:
    class ErrorResponse:
        status_code = 400
        text = "bad embedding request"

        def raise_for_status(self) -> None:
            request = httpx.Request("POST", "https://example.com/v1/embeddings")
            response = httpx.Response(400, request=request, text=self.text)
            raise httpx.HTTPStatusError(
                "Bad Request",
                request=request,
                response=response,
            )

    def fake_post(*args, **kwargs) -> ErrorResponse:
        return ErrorResponse()

    monkeypatch.setattr(httpx, "post", fake_post)

    provider = NvidiaEmbeddingProvider(
        api_key="api-key",
        base_url="https://example.com/v1/",
        model="test-model",
        dimensions=1024,
    )

    try:
        provider.embed_passages(texts=["first"])
    except RuntimeError as error:
        assert "status 400" in str(error)
        assert "bad embedding request" in str(error)
    else:
        raise AssertionError("Expected RuntimeError")
