from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Enterprise Intelligence Copilot"
    environment: str = "development"
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 720
    database_url: str = "sqlite:///./app.db"
    groq_api_key: str = ""
    cors_origins: str = "http://localhost:5173"
    upload_dir: str = "./data/uploads"
    chroma_dir: str = "./data/chroma"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)

    @property
    def chroma_path(self) -> Path:
        return Path(self.chroma_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()
