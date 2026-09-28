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
    embedding_model: str = "nvidia/llama-nemotron-embed-1b-v2"
    embedding_base_url: str = "https://integrate.api.nvidia.com/v1"
    embedding_dimensions: int = 1024
    nvidia_api_key: str = ""

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

    upload_dir: str = "storage/uploads"
    temp_dir: str = "storage/temp"

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

settings = Settings()
