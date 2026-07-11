
# backend/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # database / cache
    database_url: str
    redis_url: str = "redis://localhost:6379"

    # local LLM + vector store
    ollama_url: str = "http://localhost:11434"
    chroma_url: str = "http://localhost:8001"

    # auth
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # oauth
    github_client_id: str | None = None
    github_client_secret: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None

    # notifications (optional in dev)
    sendgrid_api_key: str | None = None
    slack_webhook_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    # cached so we don't re-parse the .env on every request
    return Settings()


settings = get_settings()