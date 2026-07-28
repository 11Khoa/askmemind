from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core import dependencies
from app.repositories.chunk_repository import ChunkRepository
from app.services.embedding_service import EmbeddingService
from app.services.providers.nvidia_embedding_provider import NvidiaEmbeddingProvider
from app.services.retrieval_service import RetrievalService


def test_embedding_service_builds_nvidia_embedding_service(monkeypatch) -> None:
    fake_settings = SimpleNamespace(
        embedding_provider="nvidia",
        nvidia_api_key="nvidia-api-key",
        embedding_base_url="https://example.com/v1",
        embedding_model="test-embedding-model",
        embedding_dimensions=1024,
    )
    monkeypatch.setattr(dependencies, "settings", fake_settings)

    service = dependencies.get_embedding_service()

    assert isinstance(service, EmbeddingService)
    assert service.embedding_provider == "nvidia"
    assert service.embedding_model == "test-embedding-model"
    assert service.embedding_dimensions == 1024
    assert isinstance(service.provider, NvidiaEmbeddingProvider)
    assert service.provider.api_key == "nvidia-api-key"
    assert service.provider.base_url == "https://example.com/v1"
    assert service.provider.model == "test-embedding-model"


def test_get_embedding_service_raises_when_nvidia_api_key_is_missing(monkeypatch) -> None:
    fake_settings = SimpleNamespace(
        embedding_provider="nvidia",
        nvidia_api_key="",
        embedding_base_url="https://example.com/v1",
        embedding_model="test-embedding-model",
        embedding_dimensions=1024,
    )
    monkeypatch.setattr(dependencies, "settings", fake_settings)

    with pytest.raises(
        ValueError,
        match="NVIDIA_API_KEY is required for NVIDIA embeddings",
    ):
        dependencies.get_embedding_service()


def test_get_embedding_service_raises_for_unsupport_provider(monkeypatch) -> None:
    fake_settings = SimpleNamespace(
        embedding_provider="unknown",
        nvidia_api_key="nvidia-api-key",
        embedding_base_url="https://example.com/v1",
        embedding_model="test-embedding-model",
        embedding_dimensions=1024,
    )
    monkeypatch.setattr(dependencies, "settings", fake_settings)

    with pytest.raises(
        ValueError,
        match="^Unsupported embedding provider: unknown$",
    ):
        dependencies.get_embedding_service()


def test_get_retrieval_service_builds_retrieval_service(monkeypatch) -> None:
    db = Mock()
    embedding_service = Mock(spec=EmbeddingService)

    monkeypatch.setattr(
        dependencies,
        "get_embedding_service",
        lambda: embedding_service,
    )

    service = dependencies.get_retrieval_service(db=db)

    assert isinstance(service, RetrievalService)
    assert service.embedding_service is embedding_service
    assert isinstance(service.chunk_repository, ChunkRepository)
    assert service.chunk_repository.db is db
