from typing import Any

import httpx


class GroqLLMProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        max_tokens: int,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens

    def generate_answer(
        self,
        question: str,
        context: str,
    ) -> str:
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You answer questions using only the provided context. "
                            "If the context does not contain the answer, say you do not know."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Context:\n{context}\n\n"
                            f"Question:\n{question}"
                        ),
                    },
                ],
                "max_tokens": self.max_tokens,
            },
            timeout=30.0,
        )
        response.raise_for_status()

        payload: dict[str, Any] = response.json()

        return payload["choices"][0]["message"]["content"]
