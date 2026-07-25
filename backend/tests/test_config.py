from app.core.config import Settings


def test_default_embedding_settings_match_current_vector_schema() -> None:
    settings = Settings(
        database_url="postgresql://test:test@localhost:5432/test",
        secret_key="test-secret",
        openai_api_key="test-openai-key",
    )
    assert settings.embedding_provider == "nvidia"
    assert settings.embedding_model == "nvidia/llama-nemotron-embed-1b-v2"
    assert settings.embedding_base_url == "https://integrate.api.nvidia.com/v1"
    assert settings.embedding_dimensions == 1024
