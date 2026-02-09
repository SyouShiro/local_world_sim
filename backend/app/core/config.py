from __future__ import annotations

from functools import lru_cache
from typing import Any, List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_env: str = Field(default="dev", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    # NOTE: Keep as string to avoid pydantic-settings JSON-decoding complex types from .env.
    cors_origins: str = Field(
        default="http://127.0.0.1:5500,http://localhost:5500",
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
    event_dice_enabled: bool = Field(default=True, alias="EVENT_DICE_ENABLED")
    event_good_event_prob: float = Field(default=0.25, alias="EVENT_GOOD_EVENT_PROB")
    event_bad_event_prob: float = Field(default=0.15, alias="EVENT_BAD_EVENT_PROB")
    event_rebel_prob: float = Field(default=0.10, alias="EVENT_REBEL_PROB")
    event_min_events: int = Field(default=1, alias="EVENT_MIN_EVENTS")
    event_max_events: int = Field(default=5, alias="EVENT_MAX_EVENTS")
    event_default_hemisphere: str = Field(default="north", alias="EVENT_DEFAULT_HEMISPHERE")

    model_config = SettingsConfigDict(env_file=(".env", "backend/.env"), extra="ignore")

    def parsed_cors_origins(self) -> List[str]:
        """Return CORS origins parsed from env var.

        Supports comma-delimited strings (recommended) and JSON list strings.
        """

        raw = (self.cors_origins or "").strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                import json

                value: Any = json.loads(raw)
                if isinstance(value, list):
                    items = [str(item).strip() for item in value]
                    return [item for item in items if item]
            except Exception:  # noqa: BLE001
                pass
        return [item.strip() for item in raw.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
