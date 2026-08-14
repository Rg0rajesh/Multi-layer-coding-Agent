from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379"

    ollama_url: str = "http://localhost:11434"
    chroma_url: str = "http://localhost:8001"
    piston_url: str = "http://piston:2000"

    ollama_model: str = "qwen2.5-coder:3b"
    llama_guard_model: str = "llama-guard3:1b"

    ollama_timeout_seconds: float = 180.0
    ollama_max_concurrent_requests: int = 1

    opa_url: str = "http://localhost:8181"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    cookie_secure: bool = True

    github_client_id: str | None = None
    github_client_secret: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None

    sendgrid_api_key: str | None = None
    slack_webhook_url: str | None = None

    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_comma_separated(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                import json
                return json.loads(value)
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
