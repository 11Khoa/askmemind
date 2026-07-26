from typing import Any

import httpx


class NvidiaEmbeddingProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def embed_passages(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        return self._embed(
            texts=texts,
            input_type="passage",
        )

    def embed_query(
        self,
        text: str,
    ) -> list[float]:
        embeddings = self._embed(
            texts=[text],
            input_type="query",
        )

        return embeddings[0]

    def _embed(
        self,
        texts: list[str],
        input_type: str,
    ) -> list[list[float]]:
        response = httpx.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": texts,
                "input_type": input_type,
            },
            timeout=30.0,
        )
        response.raise_for_status()

        payload: dict[str, Any] = response.json()

        return [
            item["embedding"]
            for item in payload["data"]
        ]
