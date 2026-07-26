from unittest.mock import Mock

import pytest

from app.services.embedding_service import EmbeddingProvider, EmbeddingService


def test_embed_passages_returns_valid_embeddings() -> None:
    provider = Mock(spec=EmbeddingProvider)
    provider.embed_passages.return_value = [
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6],
    ]

    service = EmbeddingService(
        provider=provider,
        embedding_dimensions=3,
    )

    result = service.embed_passages(texts=["first", "second"])

    assert result == [
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6],
    ]

    provider.embed_passages.assert_called_once_with(
        texts=["first", "second"],
    )


def test_embed_query_returns_valid_embedding() -> None:
    provider = Mock(spec=EmbeddingProvider)
    provider.embed_query.return_value = [0.1, 0.2, 0.3]

    service = EmbeddingService(
        provider=provider,
        embedding_dimensions=3,
    )

    result = service.embed_query(text="question")

    assert result == [0.1, 0.2, 0.3]
    provider.embed_query.assert_called_once_with(text="question")


def test_embed_passages_raises_when_embedding_dimension_is_wrong() -> None:
    provider = Mock(spec=EmbeddingProvider)
    provider.embed_passages.return_value = [[0.1, 0.2]]

    service = EmbeddingService(
        provider=provider,
        embedding_dimensions=3,
    )

    with pytest.raises(ValueError, match="Expected embedding dimension 3, got 2"):
        service.embed_passages(texts=["bad"])


def test_embed_query_raises_when_embedding_dimension_is_wrong() -> None:
    provider = Mock(spec=EmbeddingProvider)
    provider.embed_query.return_value = [0.1, 0.2]

    service = EmbeddingService(
        provider=provider,
        embedding_dimensions=3,
    )

    with pytest.raises(ValueError, match="Expected embedding dimension 3, got 2"):
        service.embed_query(text="bad query")
