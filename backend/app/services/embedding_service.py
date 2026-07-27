from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed_passages(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        ...

    def embed_query(
        self,
        text: str,
    ) -> list[float]:
        ...


class EmbeddingService:
    def __init__(
        self,
        provider: EmbeddingProvider,
        embedding_provider: str,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> None:
        self.provider = provider
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions

    def _validate_embedding_dimensions(
        self,
        embedding: list[float],
    ) -> None:
        if len(embedding) != self.embedding_dimensions:
            raise ValueError(
                f"Expected embedding dimension {self.embedding_dimensions}, "
                f"got {len(embedding)}"
            )

    def embed_passages(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        embeddings = self.provider.embed_passages(texts=texts)

        for embedding in embeddings:
            self._validate_embedding_dimensions(embedding=embedding)

        return embeddings

    def embed_query(
        self,
        text: str,
    ) -> list[float]:
        embedding = self.provider.embed_query(text=text)
        self._validate_embedding_dimensions(embedding=embedding)

        return embedding
