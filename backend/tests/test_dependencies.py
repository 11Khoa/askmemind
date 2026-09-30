from pathlib import Path
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core import dependencies
from app.repositories.chunk_repository import ChunkRepository
from app.services.chat_service import ChatService
from app.services.embedding_service import EmbeddingService
from app.services.providers.nvidia_embedding_provider import NvidiaEmbeddingProvider
from app.services.retrieval_service import RetrievalService
from app.services.reranking_service import RerankingService
from app.services.guardrail_service import GuardrailService
from app.services.llm_service import LLMService
from app.services.rag_service import RagService
from app.services.providers.groq_llm_provider import GroqLLMProvider
from app.services.context_builder_service import ContextBuilderService


def test_get_chat_service_builds_chat_service_with_rag_service(monkeypatch) -> None:
    db = Mock()
    rag_service = Mock(spec=RagService)

    monkeypatch.setattr(
        dependencies,
        "get_rag_service",
        lambda db: rag_service,
    )

    service = dependencies.get_chat_service(db=db)

    assert isinstance(service, ChatService)
    assert service.chat_repository.db is db
    assert service.user_repository.db is db
    assert service.rag_service is rag_service


def test_embedding_service_builds_nvidia_embedding_service(monkeypatch) -> None:
    fake_settings = SimpleNamespace(
        embedding_provider="nvidia",
        nvidia_api_key="nvidia-api-key",
        embedding_base_url="https://example.com/v1",
        embedding_model="test-embedding-model",
        embedding_dimensions=1024,
        embedding_batch_size=16,
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
    assert service.provider.batch_size == 16


def test_get_embedding_service_raises_when_nvidia_api_key_is_missing(monkeypatch) -> None:
    fake_settings = SimpleNamespace(
        embedding_provider="nvidia",
        nvidia_api_key="",
        embedding_base_url="https://example.com/v1",
        embedding_model="test-embedding-model",
        embedding_dimensions=1024,
        embedding_batch_size=16,
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
        embedding_batch_size=16,
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
    reranking_service = Mock(spec=RerankingService)
    guardrail_service = Mock(spec=GuardrailService)

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
    monkeypatch.setattr(
        dependencies,
        "get_reranking_service",
        lambda: reranking_service,
    )
    monkeypatch.setattr(
        dependencies,
        "get_guardrail_service",
        lambda: guardrail_service,
    )

    service = dependencies.get_rag_service(db=db)

    assert isinstance(service, RagService)
    assert service.retrieval_service is retrieval_service
    assert isinstance(service.context_builder_service, ContextBuilderService)
    assert service.llm_service is llm_service
    assert service.reranking_service is reranking_service
    assert service.reranker_enabled is dependencies.settings.reranker_enabled
    assert service.reranker_candidate_k == dependencies.settings.reranker_candidate_k
    assert service.guardrail_service is guardrail_service
    assert (
        service.retrieval_min_confidence
        == dependencies.settings.retrieval_min_confidence
    )
    assert (
        service.citation_validation_enabled
        is dependencies.settings.citation_validation_enabled
    )


def test_process_document_in_background_marks_failed_and_closes_session(monkeypatch) -> None:
    from app.core.types import DocumentStatus
    from app.models.document import Document

    document_id = uuid.uuid4()
    user_id = uuid.uuid4()
    document = Document(
        id=document_id,
        user_id=user_id,
        filename='failing.pdf',
        original_filename='failing.pdf',
        file_path='/tmp/failing.pdf',
        content_type='application/pdf',
        file_size_bytes=123,
        status=DocumentStatus.PROCESSING.value,
        source_type='pdf',
    )

    class FakeSession:
        def __init__(self) -> None:
            self.closed = False
            self.commits = 0
            self.rollbacks = 0

        def close(self) -> None:
            self.closed = True

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            self.rollbacks += 1

    class FakeRepository:
        def __init__(self, db) -> None:
            self.db = db

        def get_document_by_id(self, document_id):
            return document

        def mark_processing_failed(self, document, error_message):
            document.status = DocumentStatus.PROCESSING_FAILED.value
            document.error_message = error_message
            return document

    class FailingProcessingService:
        def process_document(self, document_id, file_path):
            raise RuntimeError('boom')

    published_events = []
    fake_session = FakeSession()
    monkeypatch.setattr(dependencies, 'SessionLocal', lambda: fake_session)
    monkeypatch.setattr(dependencies, 'DocumentRepository', FakeRepository)
    monkeypatch.setattr(
        dependencies,
        'build_document_processing_service',
        lambda db: FailingProcessingService(),
    )
    monkeypatch.setattr(
        dependencies.document_event_broker,
        'publish',
        lambda user_id, payload: published_events.append((user_id, payload)),
    )

    dependencies.process_document_in_background(
        document_id=document_id,
        file_path=Path('/tmp/failing.pdf'),
        request_id='request-1',
        user_id=user_id,
    )

    assert document.status == DocumentStatus.PROCESSING_FAILED.value
    assert document.error_message == 'boom'
    assert fake_session.rollbacks == 1
    assert fake_session.commits == 1
    assert fake_session.closed is True
    assert published_events == [
        (
            user_id,
            {
                'document_id': str(document_id),
                'status': DocumentStatus.PROCESSING_FAILED.value,
                'page_count': None,
                'error_message': 'boom',
            },
        )
    ]
