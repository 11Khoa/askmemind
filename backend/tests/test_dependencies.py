from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core import dependencies
from app.repositories.chunk_repository import ChunkRepository
from app.services.embedding_service import EmbeddingService
from app.services.providers.nvidia_embedding_provider import NvidiaEmbeddingProvider
from app.services.retrieval_service import RetrievalService
from app.services.llm_service import LLMService
from app.services.rag_service import RagService
from app.services.providers.groq_llm_provider import GroqLLMProvider
from app.services.context_builder_service import ContextBuilderService


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


def test_get_llm_service_builds_groq_llm_service(monkeypatch) -> None:
    fake_settings = SimpleNamespace(
        llm_provider="groq",
        groq_api_key="groq-api-key",
        llm_base_url="https://api.groq.com/openai/v1",
        llm_model="openai/gpt-oss-120b",
        llm_max_tokens=500,
    )
    monkeypatch.setattr(dependencies, "settings", fake_settings)

    service = dependencies.get_llm_service()

    assert isinstance(service, LLMService)
    assert isinstance(service.provider, GroqLLMProvider)
    assert service.provider.api_key == "groq-api-key"
    assert service.provider.base_url == "https://api.groq.com/openai/v1"
    assert service.provider.model == "openai/gpt-oss-120b"
    assert service.provider.max_tokens == 500


def test_get_llm_service_raises_when_groq_api_key_is_missing(monkeypatch) -> None:
    fake_settings = SimpleNamespace(
        llm_provider="groq",
        groq_api_key="",
        llm_base_url="https://api.groq.com/openai/v1",
        llm_model="openai/gpt-oss-120b",
        llm_max_tokens=500,
    )
    monkeypatch.setattr(dependencies, "settings", fake_settings)

    with pytest.raises(
        ValueError,
        match="GROQ_API_KEY is required for Groq LLMs",
    ):
        dependencies.get_llm_service()


def test_get_llm_service_raises_for_unsupported_provider(monkeypatch) -> None:
    fake_settings = SimpleNamespace(
        llm_provider="unknown",
        groq_api_key="groq-api-key",
        llm_base_url="https://api.groq.com/openai/v1",
        llm_model="openai/gpt-oss-120b",
        llm_max_tokens=500,
    )
    monkeypatch.setattr(dependencies, "settings", fake_settings)

    with pytest.raises(ValueError) as error:
        dependencies.get_llm_service()

    assert str(error.value) == "Unsupported LLM provider: unknown"


def test_get_rag_service_builds_rag_service(monkeypatch) -> None:
    db = Mock()
    retrieval_service = Mock(spec=RetrievalService)
    llm_service = Mock(spec=LLMService)

    monkeypatch.setattr(
        dependencies,
        "get_retrieval_service",
        lambda db: retrieval_service,
    )
    monkeypatch.setattr(
        dependencies,
        "get_llm_service",
        lambda: llm_service,
    )

    service = dependencies.get_rag_service(db=db)

    assert isinstance(service, RagService)
    assert service.retrieval_service is retrieval_service
    assert isinstance(service.context_builder_service, ContextBuilderService)
    assert service.llm_service is llm_service
