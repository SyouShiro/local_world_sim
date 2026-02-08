from __future__ import annotations

from typing import Any, Optional

import httpx

from app.providers.base import LLMAdapter, LLMResult, ProviderError, ProviderRuntimeConfig


class DeepSeekAdapter(LLMAdapter):
    """Adapter for the DeepSeek OpenAI-compatible API."""

    def __init__(self, timeout_sec: float = 90, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._timeout = timeout_sec
        self._client = http_client

    async def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        url = self._join_url(cfg.base_url, "/models")
        headers = self._auth_headers(cfg.api_key)
        data = await self._request_json("GET", url, headers=headers)
        models = [item.get("id") for item in data.get("data", []) if item.get("id")]
        if not models:
            raise ProviderError("PROVIDER_NO_MODELS", "No models returned by provider.")
        return models

    async def generate(
        self, cfg: ProviderRuntimeConfig, messages: list[dict], stream: bool = False
    ) -> LLMResult:
        url = self._join_url(cfg.base_url, "/chat/completions")
        headers = self._auth_headers(cfg.api_key)
        payload = {"model": cfg.model_name, "messages": messages, "stream": False}
        data = await self._request_json("POST", url, headers=headers, json=payload)
        choices = data.get("choices", [])
        if not choices:
            raise ProviderError("PROVIDER_PARSE_ERROR", "No choices returned by provider.")
        content = choices[0].get("message", {}).get("content")
        if not content:
            raise ProviderError("PROVIDER_PARSE_ERROR", "Provider returned empty content.")
        return LLMResult(
            content=content,
            model_provider=cfg.provider,
            model_name=cfg.model_name,
            token_in=self._get_usage_int(data, "prompt_tokens"),
            token_out=self._get_usage_int(data, "completion_tokens"),
        )

    def _auth_headers(self, api_key: Optional[str]) -> dict[str, str]:
        if not api_key:
            raise ProviderError("API_KEY_REQUIRED", "API key is required for DeepSeek.")
        return {"Authorization": f"Bearer {api_key}"}

    async def _request_json(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        response = await self._request(method, url, headers=headers, json=json)
        try:
            return response.json()
        except ValueError as exc:  # noqa: BLE001
            raise ProviderError("PROVIDER_PARSE_ERROR", "Invalid JSON from provider.") from exc

    async def _request(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> httpx.Response:
        try:
            if self._client:
                response = await self._client.request(method, url, headers=headers, json=json)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.request(method, url, headers=headers, json=json)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "PROVIDER_TIMEOUT", "Provider request timed out.", retryable=True
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                "PROVIDER_CONNECTION_ERROR",
                "Provider connection failed.",
                retryable=True,
            ) from exc
        if response.status_code >= 400:
            raise self._status_error(response)
        return response

    @staticmethod
    def _join_url(base_url: Optional[str], path: str) -> str:
        if not base_url:
            raise ProviderError("PROVIDER_BASE_URL_MISSING", "Base URL is required for DeepSeek.")
        base = base_url.rstrip("/")
        if base.endswith("/v1") and path.startswith("/v1/"):
            return base + path[3:]
        return base + path

    @staticmethod
    def _get_usage_int(data: dict[str, Any], key: str) -> Optional[int]:
        usage = data.get("usage", {})
        value = usage.get(key)
        return int(value) if isinstance(value, int) else None

    @staticmethod
    def _status_error(response: httpx.Response) -> ProviderError:
        status = response.status_code
        message = f"Provider returned {status}: {response.text}"
        if status == 429:
            return ProviderError(
                "PROVIDER_RATE_LIMIT", message, retryable=True, status_code=status
            )
        if status >= 500:
            return ProviderError(
                "PROVIDER_UPSTREAM", message, retryable=True, status_code=status
            )
        return ProviderError("PROVIDER_BAD_STATUS", message, status_code=status)
