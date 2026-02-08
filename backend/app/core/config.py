from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_env: str = Field(default="dev", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    cors_origins: List[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:5500", "http://localhost:5500"],
        alias="CORS_ORIGINS",
    )
    db_url: str = Field(default="sqlite+aiosqlite:///./worldline.db", alias="DB_URL")
    default_post_gen_delay_sec: int = Field(default=5, alias="DEFAULT_POST_GEN_DELAY_SEC")
    default_tick_label: str = Field(default="1个月", alias="DEFAULT_TICK_LABEL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    app_secret_key: str = Field(default="", alias="APP_SECRET_KEY")
    openai_base_url: str = Field(default="https://api.openai.com", alias="OPENAI_BASE_URL")
    ollama_base_url: str = Field(
        default="http://localhost:11434", alias="OLLAMA_BASE_URL"
    )
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com", alias="GEMINI_BASE_URL"
    )
    memory_mode: str = Field(default="off", alias="MEMORY_MODE")
    memory_max_snippets: int = Field(default=8, alias="MEMORY_MAX_SNIPPETS")
    memory_max_chars: int = Field(default=4000, alias="MEMORY_MAX_CHARS")
    embed_provider: str = Field(default="deterministic", alias="EMBED_PROVIDER")
    embed_model: str = Field(default="deterministic-v1", alias="EMBED_MODEL")
    embed_dim: int = Field(default=64, alias="EMBED_DIM")
    embed_openai_api_key: str = Field(default="", alias="EMBED_OPENAI_API_KEY")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | List[str]) -> List[str]:
        """Split comma-delimited CORS origins when provided as a string."""

        if isinstance(value, list):
            return value
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
