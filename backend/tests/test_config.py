from app.core.config import Settings


def test_default_embedding_settings_match_current_vector_schema() -> None:
    settings = Settings(
        database_url="postgresql://test:test@localhost:5432/test",
        secret_key="test-secret",
    )
    assert settings.embedding_provider == "nvidia"
    assert settings.embedding_model == "nvidia/llama-nemotron-embed-1b-v2"
    assert settings.embedding_base_url == "https://integrate.api.nvidia.com/v1"
    assert settings.embedding_dimensions == 1024
    assert settings.reranker_enabled is False
    assert settings.reranker_candidate_k == 20
    assert settings.retrieval_min_confidence == 0.05
    assert settings.citation_validation_enabled is True
    assert settings.log_level == "INFO"
    assert settings.agentic_retrieval_enabled is False
    assert settings.agentic_retrieval_max_retries == 1
    assert settings.agentic_retrieval_min_confidence == 0.35
    assert settings.max_upload_size_mb == 25
