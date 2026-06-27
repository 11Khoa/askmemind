from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    openai_api_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

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
