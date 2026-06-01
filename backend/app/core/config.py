from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR=Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    openai_api_key: str

    upload_dir: str = "storage/uploads"
    temp_dir: str = "storage/temp"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
