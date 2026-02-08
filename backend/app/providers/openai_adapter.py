from __future__ import annotations

from typing import Any, Optional

import httpx

from app.providers.base import (
    HTTPProviderAdapter,
    LLMAdapter,
    LLMResult,
    ProviderError,
    ProviderRuntimeConfig,
    require_api_key,
)


class OpenAIAdapter(HTTPProviderAdapter, LLMAdapter):
    """Adapter for OpenAI-compatible APIs."""

    def __init__(
        self, timeout_sec: float = 90, http_client: Optional[httpx.AsyncClient] = None
    ) -> None:
        super().__init__(timeout_sec=timeout_sec, http_client=http_client)

    async def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        url = self._join_url(cfg.base_url, "/v1/models")
        headers = self._auth_headers(cfg.api_key)
        data = await self._request_json("GET", url, headers=headers)
        models = [item.get("id") for item in data.get("data", []) if item.get("id")]
        if not models:
            raise ProviderError("PROVIDER_NO_MODELS", "No models returned by provider.")
        return models

    async def generate(
        self, cfg: ProviderRuntimeConfig, messages: list[dict], stream: bool = False
    ) -> LLMResult:
        url = self._join_url(cfg.base_url, "/v1/responses")
        headers = self._auth_headers(cfg.api_key)
        payload = {"model": cfg.model_name, "input": messages}
        try:
            data = await self._request_json("POST", url, headers=headers, json=payload)
            content = self._parse_responses_output(data)
            token_in = self._get_usage_int(data, "input_tokens")
            token_out = self._get_usage_int(data, "output_tokens")
            return LLMResult(
                content=content,
                model_provider=cfg.provider,
                model_name=cfg.model_name,
                token_in=token_in,
                token_out=token_out,
            )
        except ProviderError as exc:
            if exc.retryable:
                raise
            if exc.code == "PROVIDER_PARSE_ERROR":
                pass
            elif exc.code == "PROVIDER_BAD_STATUS" and exc.status_code in {400, 404, 405}:
                pass
            else:
                raise

        fallback_url = self._join_url(cfg.base_url, "/v1/chat/completions")
        fallback_payload = {"model": cfg.model_name, "messages": messages}
        data = await self._request_json("POST", fallback_url, headers=headers, json=fallback_payload)
        choices = data.get("choices", [])
        if not choices:
            raise ProviderError("PROVIDER_PARSE_ERROR", "No choices returned by provider.")
        content = choices[0].get("message", {}).get("content")
        if not content:
            raise ProviderError("PROVIDER_PARSE_ERROR", "Provider returned empty content.")
        token_in = self._get_usage_int(data, "prompt_tokens")
        token_out = self._get_usage_int(data, "completion_tokens")
        return LLMResult(
            content=content,
            model_provider=cfg.provider,
            model_name=cfg.model_name,
            token_in=token_in,
            token_out=token_out,
        )

    def _auth_headers(self, api_key: Optional[str]) -> dict[str, str]:
        key = require_api_key(api_key, "OpenAI")
        return {"Authorization": f"Bearer {key}"}

    @staticmethod
    def _join_url(base_url: Optional[str], path: str) -> str:
        if not base_url:
            raise ProviderError("PROVIDER_BASE_URL_MISSING", "Base URL is required for OpenAI.")
        base = base_url.rstrip("/")
        if base.endswith("/v1") and path.startswith("/v1/"):
            return base + path[3:]
        return base + path

    @staticmethod
    def _parse_responses_output(data: dict[str, Any]) -> str:
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        output = data.get("output", [])
        for entry in output:
            for item in entry.get("content", []):
                if item.get("type") == "output_text" and item.get("text"):
                    return item["text"]
        raise ProviderError("PROVIDER_PARSE_ERROR", "No output_text returned by provider.")

    @staticmethod
    def _get_usage_int(data: dict[str, Any], key: str) -> Optional[int]:
        usage = data.get("usage", {})
        value = usage.get(key)
        return int(value) if isinstance(value, int) else None
