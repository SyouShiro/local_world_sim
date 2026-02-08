from __future__ import annotations

from typing import Any, Optional

import httpx

from app.providers.base import (
    HTTPProviderAdapter,
    LLMAdapter,
    LLMResult,
    ProviderError,
    ProviderRuntimeConfig,
)


class OllamaAdapter(HTTPProviderAdapter, LLMAdapter):
    """Adapter for the Ollama local API."""

    def __init__(
        self, timeout_sec: float = 90, http_client: Optional[httpx.AsyncClient] = None
    ) -> None:
        super().__init__(timeout_sec=timeout_sec, http_client=http_client)

    async def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        url = self._join_url(cfg.base_url, "/api/tags")
        data = await self._request_json("GET", url)
        models = [item.get("name") for item in data.get("models", []) if item.get("name")]
        if not models:
            raise ProviderError("PROVIDER_NO_MODELS", "No models returned by provider.")
        return models

    async def generate(
        self, cfg: ProviderRuntimeConfig, messages: list[dict], stream: bool = False
    ) -> LLMResult:
        url = self._join_url(cfg.base_url, "/api/chat")
        payload = {"model": cfg.model_name, "messages": messages, "stream": False}
        data = await self._request_json("POST", url, json=payload)
        message = data.get("message", {})
        content = message.get("content")
        if not content:
            raise ProviderError("PROVIDER_PARSE_ERROR", "Provider returned empty content.")
        return LLMResult(
            content=content,
            model_provider=cfg.provider,
            model_name=cfg.model_name,
            token_in=self._get_int(data, "prompt_eval_count"),
            token_out=self._get_int(data, "eval_count"),
        )

    @staticmethod
    def _join_url(base_url: Optional[str], path: str) -> str:
        if not base_url:
            raise ProviderError("PROVIDER_BASE_URL_MISSING", "Base URL is required for Ollama.")
        base = base_url.rstrip("/")
        if base.endswith("/api") and path.startswith("/api/"):
            return base + path[4:]
        return base + path

    @staticmethod
    def _get_int(data: dict[str, Any], key: str) -> Optional[int]:
        value = data.get(key)
        return int(value) if isinstance(value, int) else None
