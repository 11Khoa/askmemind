from collections.abc import Iterator
from typing import Protocol


class LLMProvider(Protocol):
    def generate_answer(
        self,
        question: str,
        context: str,
    ) -> str:
        ...

    def stream_answer(
        self,
        question: str,
        context: str,
    ) -> Iterator[str]:
        ...


class LLMService:
    def __init__(
        self,
        provider: LLMProvider,
    ) -> None:
        self.provider = provider

    def generate_answer(
        self,
        question: str,
        context: str,
    ) -> str:
        return self.provider.generate_answer(
            question=question,
            context=context,
        )

    def stream_answer(
        self,
        question: str,
        context: str,
    ) -> Iterator[str]:
        yield from self.provider.stream_answer(
            question=question,
            context=context,
        )
