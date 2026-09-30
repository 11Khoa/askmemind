from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    backend_cors_origins: str = ""
    database_url: str
    secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    enable_registration: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    embedding_provider: str = "nvidia"
    embedding_model: str = "nvidia/nemotron-3-embed-1b"
    embedding_base_url: str = "https://integrate.api.nvidia.com/v1"
    embedding_dimensions: int = 2048
    embedding_batch_size: int = Field(default=32, ge=1, le=128)
    nvidia_api_key: str = ""
    embedding_v2_enabled: bool = False

    groq_api_key: str = ""
    llm_provider: str = "groq"
    llm_model: str = "openai/gpt-oss-120b"
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_max_tokens: int = 500

    hybrid_search_enabled: bool = False
    reranker_enabled: bool = False
    reranker_candidate_k: int = Field(default=20, ge=1, le=100)
    agentic_retrieval_enabled: bool = False
    agentic_retrieval_max_retries: int = Field(default=1, ge=0, le=3)
    agentic_retrieval_min_confidence: float = Field(default=0.35, ge=0.0, le=1.0)
    retrieval_min_confidence: float = Field(default=0.05, ge=0.0, le=1.0)
    citation_validation_enabled: bool = True

    max_upload_size_mb: int = Field(default=25, ge=1, le=100)
    upload_dir: str = "storage/uploads"
    temp_dir: str = "storage/temp"

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_upload_dir(self) -> Path:
        upload_path = Path(self.upload_dir)

        if upload_path.is_absolute():
            return upload_path
        return BASE_DIR / upload_path

    @property
    def resolved_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def resolved_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


settings = Settings()
