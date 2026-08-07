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

    # Model tags live here, not hardcoded in each agent file — swapping back
    # to 7B on a stronger machine later is a one-line .env change this way.
    ollama_model: str = "qwen2.5-coder:3b"

    # Guardrail (C9) classifier. Defaults to the 1b tag — the 8b variant needs
    # ~6-7GB RAM on its own, which doesn't leave room for the coder model and
    # the rest of the stack on a typical laptop. Same taxonomy either way;
    # bump to "llama-guard3:8b" via .env once you're on beefier hardware.
    llama_guard_model: str = "llama-guard3:1b"

    # How long we'll wait on a single Ollama /api/chat call before giving up,
    # and how many of those calls can be in flight at once. Ollama serializes
    # requests against one loaded model anyway, so this semaphore mostly
    # exists to keep a burst of Celery workers from all queuing up at once
    # and each hitting their own timeout simultaneously.
    ollama_timeout_seconds: float = 120.0
    ollama_max_concurrent_requests: int = 2

    # governance (C7) — Identity Broker's policy engine
    opa_url: str = "http://localhost:8181"

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

    # CORS — comma-separated in .env, e.g.
    # "https://app.agentx.dev,https://staging.agentx.dev"
    # pydantic-settings parses a comma-separated string straight into a list.
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    # cached so we don't re-parse the .env on every request
    return Settings()


settings = get_settings()