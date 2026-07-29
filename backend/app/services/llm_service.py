from typing import Protocol


class LLMProvider(Protocol):
    def generate_answer(
        self,
        question: str,
        context: str,
    ) -> str:
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
