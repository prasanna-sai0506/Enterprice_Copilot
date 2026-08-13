from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    DATABASE_URL: str = "sqlite+aiosqlite:///./enterprise.db"
    JWT_SECRET: str = "dev-secret"
    JWT_EXPIRY_HOURS: int = 8
    GROQ_API_KEY: str = ""
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 50
    SUPER_ADMIN_EMAIL: str = "admin@ent-ai.local"
    SUPER_ADMIN_PASSWORD: str = "Admin@12345"
    SUPER_ADMIN_API_KEY: str = "super-admin-dev-key"
    SEED_DEMO: bool = True
    ALLOWED_ORIGINS: str = "http://localhost:8000"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""


settings = Settings()
