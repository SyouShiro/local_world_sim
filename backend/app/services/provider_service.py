from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.db.models import ProviderConfig
from app.providers.base import LLMAdapter, ProviderError, ProviderRuntimeConfig
from app.providers.deepseek_adapter import DeepSeekAdapter
from app.providers.gemini_adapter import GeminiAdapter
from app.providers.ollama_adapter import OllamaAdapter
from app.providers.openai_adapter import OpenAIAdapter
from app.repos.provider_repo import ProviderRepo
from app.utils.crypto import SecretCipher
from app.api.websocket import WebSocketManager

SUPPORTED_PROVIDERS = ("openai", "ollama", "deepseek", "gemini")


class ProviderService:
    """Manage provider configuration and adapter access."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        ws_manager: WebSocketManager,
        settings: Optional[Settings] = None,
        adapters: Optional[dict[str, LLMAdapter]] = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._ws_manager = ws_manager
        self._settings = settings or get_settings()
        self._adapters = adapters or {
            "openai": OpenAIAdapter(),
            "ollama": OllamaAdapter(),
            "deepseek": DeepSeekAdapter(),
            "gemini": GeminiAdapter(),
        }

    def set_adapters(self, adapters: dict[str, LLMAdapter]) -> None:
        """Override adapter registry (useful for tests)."""

        self._adapters = adapters

    async def ensure_ready(self, session_id: str) -> None:
        """Ensure provider configuration exists with a selected model."""

        async with self._sessionmaker() as db:
            repo = ProviderRepo(db)
            config = await repo.get_by_session(session_id)
            if not config or not config.model_name:
                raise ProviderError(
                    "PROVIDER_NOT_READY", "Provider and model must be configured."
                )

    async def set_provider(
        self,
        session_id: str,
        provider: str,
        api_key: Optional[str],
        base_url: Optional[str],
        model_name: Optional[str],
    ) -> ProviderConfig:
        """Store provider configuration after validation."""

        provider = self._normalize_provider(provider)
        adapter = self._get_adapter(provider)
        async with self._sessionmaker() as db:
            repo = ProviderRepo(db)
            existing = await repo.get_by_session(session_id)
            base_url = base_url or self._default_base_url(provider)
            encrypted_key = self._resolve_api_key(provider, api_key, existing)
            runtime_cfg = ProviderRuntimeConfig(
                provider=provider,
                model_name=model_name or "",
                base_url=base_url,
                api_key=self._decrypt_key(encrypted_key),
            )
            models = self._normalize_models(await adapter.list_models(runtime_cfg))
            if model_name and model_name not in models:
                raise ProviderError(
                    "PROVIDER_MODEL_INVALID", "Selected model is not available."
                )

            config = await repo.upsert_config(
                config_id=existing.id if existing else uuid.uuid4().hex,
                session_id=session_id,
                provider=provider,
                base_url=base_url,
                api_key_encrypted=encrypted_key,
                model_name=model_name,
            )
            await db.commit()
            return config

    async def list_models(self, session_id: str, provider: str) -> list[str]:
        """Fetch available models from the configured provider."""

        provider = self._normalize_provider(provider)
        adapter = self._get_adapter(provider)
        async with self._sessionmaker() as db:
            repo = ProviderRepo(db)
            config = await repo.get_by_session(session_id)
            if not config or config.provider != provider:
                raise ProviderError("PROVIDER_CONFIG_MISSING", "Provider config not found.")
            runtime_cfg = ProviderRuntimeConfig(
                provider=config.provider,
                model_name=config.model_name or "",
                base_url=config.base_url or self._default_base_url(config.provider),
                api_key=self._decrypt_key(config.api_key_encrypted),
            )

        models = self._normalize_models(await adapter.list_models(runtime_cfg))
        await self._ws_manager.broadcast(
            session_id, {"event": "models_loaded", "provider": provider, "models": models}
        )
        return models

    async def select_model(self, session_id: str, model_name: str) -> ProviderConfig:
        """Update the selected model for the provider configuration."""

        model_name = model_name.strip()
        if not model_name:
            raise ProviderError("PROVIDER_MODEL_INVALID", "Model name must not be empty.")

        async with self._sessionmaker() as db:
            repo = ProviderRepo(db)
            config = await repo.get_by_session(session_id)
            if not config:
                raise ProviderError("PROVIDER_CONFIG_MISSING", "Provider config not found.")
            adapter = self._get_adapter(config.provider)
            runtime_cfg = ProviderRuntimeConfig(
                provider=config.provider,
                model_name=model_name,
                base_url=config.base_url or self._default_base_url(config.provider),
                api_key=self._decrypt_key(config.api_key_encrypted),
            )

        models = self._normalize_models(await adapter.list_models(runtime_cfg))
        if model_name not in models:
            raise ProviderError(
                "PROVIDER_MODEL_INVALID", "Selected model is not available."
            )

        async with self._sessionmaker() as db:
            repo = ProviderRepo(db)
            async with db.begin():
                config = await repo.update_model(session_id, model_name)
            if not config:
                raise ProviderError("PROVIDER_CONFIG_MISSING", "Provider config not found.")
            return config

    async def get_generation_config(self, session_id: str) -> tuple[LLMAdapter, ProviderRuntimeConfig]:
        """Return the adapter and runtime configuration for generation."""

        async with self._sessionmaker() as db:
            repo = ProviderRepo(db)
            config = await repo.get_by_session(session_id)
            if not config or not config.model_name:
                raise ProviderError(
                    "PROVIDER_NOT_READY", "Provider and model must be configured."
                )
            adapter = self._get_adapter(config.provider)
            runtime_cfg = ProviderRuntimeConfig(
                provider=config.provider,
                model_name=config.model_name,
                base_url=config.base_url or self._default_base_url(config.provider),
                api_key=self._decrypt_key(config.api_key_encrypted),
            )
            return adapter, runtime_cfg

    def _get_adapter(self, provider: str) -> LLMAdapter:
        adapter = self._adapters.get(provider)
        if not adapter:
            raise ProviderError("PROVIDER_UNSUPPORTED", f"Unsupported provider: {provider}")
        return adapter

    def _default_base_url(self, provider: str) -> str:
        if provider == "openai":
            return self._settings.openai_base_url
        if provider == "ollama":
            return self._settings.ollama_base_url
        if provider == "deepseek":
            return self._settings.deepseek_base_url
        if provider == "gemini":
            return self._settings.gemini_base_url
        raise ProviderError("PROVIDER_UNSUPPORTED", f"Unsupported provider: {provider}")

    @staticmethod
    def _normalize_provider(provider: str) -> str:
        normalized = provider.strip().lower()
        if normalized not in SUPPORTED_PROVIDERS:
            raise ProviderError("PROVIDER_UNSUPPORTED", f"Unsupported provider: {provider}")
        return normalized

    @staticmethod
    def _normalize_models(models: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for model in models:
            candidate = model.strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            deduped.append(candidate)
        return deduped

    def _resolve_api_key(
        self,
        provider: str,
        api_key: Optional[str],
        existing: Optional[ProviderConfig],
    ) -> Optional[str]:
        if api_key:
            return self._encrypt_key(api_key)
        if existing and existing.provider == provider:
            return existing.api_key_encrypted
        if provider in {"openai", "deepseek", "gemini"}:
            raise ProviderError(
                "API_KEY_REQUIRED",
                f"API key is required for {provider}.",
            )
        return None

    def _encrypt_key(self, api_key: str) -> str:
        try:
            cipher = SecretCipher(self._settings.app_secret_key)
        except ValueError as exc:
            raise ProviderError(
                "APP_SECRET_MISSING", "APP_SECRET_KEY must be set to store API keys."
            ) from exc
        return cipher.encrypt(api_key)

    def _decrypt_key(self, encrypted: Optional[str]) -> Optional[str]:
        if not encrypted:
            return None
        try:
            cipher = SecretCipher(self._settings.app_secret_key)
        except ValueError as exc:
            raise ProviderError(
                "APP_SECRET_MISSING", "APP_SECRET_KEY must be set to read API keys."
            ) from exc
        return cipher.decrypt(encrypted)


def get_provider_service(request: Request) -> ProviderService:
    """Dependency to access the provider service from app state."""

    return request.app.state.provider_service
