from typing import Any

import httpx


class NvidiaEmbeddingProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        dimensions: int,
        batch_size: int = 32,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size

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
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            embeddings.extend(
                self._embed_batch(
                    texts=batch,
                    input_type=input_type,
                )
            )

        return embeddings

    def _embed_batch(
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
                "dimensions": self.dimensions,
            },
            timeout=30.0,
        )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            detail = response.text[:500]
            raise RuntimeError(
                "NVIDIA embedding request failed "
                f"with status {response.status_code}: {detail}"
            ) from error

        payload: dict[str, Any] = response.json()

        return [
            item["embedding"]
            for item in payload["data"]
        ]
