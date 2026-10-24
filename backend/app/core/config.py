from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[3]


def parse_origins(value: str) -> tuple[str, ...]:
    origins = tuple(
        dict.fromkeys(item.strip() for item in value.split(",") if item.strip())
    )
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or "*" in origin
            or any(character.isspace() for character in origin)
            or origin != f"{parsed.scheme}://{parsed.netloc}"
        ):
            raise ValueError(
                "Origins must be explicit http(s) origins without paths or wildcards"
            )
        parsed.port  # Validate the port as well as the hostname.
    return origins


class Settings(BaseSettings):
    environment: Literal["local", "production"] = "production"
    backend_cors_origins: str = ""
    auth_csrf_trusted_origins: str = ""
    auth_refresh_cookie_name: str = "__Host-askmemind_refresh"
    auth_refresh_cookie_secure: bool = True
    auth_refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    auth_refresh_cookie_path: str = "/"
    auth_json_tokens_enabled: bool = False
    database_url: str
    secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    refresh_token_expire_days: int = Field(default=30, ge=1, le=365)
    password_reset_expire_minutes: int = Field(default=15, ge=1, le=60)
    password_reset_url: AnyHttpUrl | None = None
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = Field(default=SecretStr(""))
    smtp_from_email: str = ""
    smtp_use_ssl: bool = False
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
    max_pdf_pages: int = Field(default=500, ge=1, le=10000)
    max_pdf_text_characters: int = Field(default=2_000_000, ge=1, le=20_000_000)
    max_documents_per_user: int = Field(default=100, ge=1)
    max_storage_per_user_mb: int = Field(default=500, ge=1)
    login_requests_per_minute: int = Field(default=10, ge=1)
    register_requests_per_hour: int = Field(default=5, ge=1)
    question_requests_per_minute: int = Field(default=30, ge=1)
    conversation_history_turns: int = Field(default=6, ge=1, le=20)
    conversation_history_characters: int = Field(default=12000, ge=100, le=40000)
    upload_requests_per_hour: int = Field(default=20, ge=1)
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

    @field_validator("backend_cors_origins", "auth_csrf_trusted_origins")
    @classmethod
    def _validate_origins(cls, value: str) -> str:
        return ",".join(parse_origins(value))

    @model_validator(mode="after")
    def _validate_cookie_security(self):
        if self.environment == "production" and not self.auth_refresh_cookie_secure:
            raise ValueError("Production refresh cookies must use Secure")
        if (
            self.auth_refresh_cookie_samesite == "none"
            and not self.auth_refresh_cookie_secure
        ):
            raise ValueError("SameSite=None requires Secure")
        if not self.auth_refresh_cookie_path.startswith("/") or any(
            char in self.auth_refresh_cookie_path for char in ";\r\n"
        ):
            raise ValueError("Refresh cookie Path must be an absolute path")
        name = self.auth_refresh_cookie_name
        if not name or any(
            char
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for char in name
        ):
            raise ValueError("Invalid refresh cookie name")
        if (
            name.startswith(("__Secure-", "__Host-"))
            and not self.auth_refresh_cookie_secure
        ):
            raise ValueError("Prefixed refresh cookies require Secure")
        if name.startswith("__Host-") and self.auth_refresh_cookie_path != "/":
            raise ValueError("__Host- refresh cookies require Path=/")
        return self

    @property
    def cors_origins(self) -> tuple[str, ...]:
        return parse_origins(self.backend_cors_origins)

    @property
    def csrf_trusted_origins(self) -> tuple[str, ...]:
        return parse_origins(self.auth_csrf_trusted_origins)

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
