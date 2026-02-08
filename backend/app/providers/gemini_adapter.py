from __future__ import annotations

from typing import Any, Optional

import httpx

from app.providers.base import LLMAdapter, LLMResult, ProviderError, ProviderRuntimeConfig


class GeminiAdapter(LLMAdapter):
    """Adapter for the Google Gemini API."""

    def __init__(self, timeout_sec: float = 90, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._timeout = timeout_sec
        self._client = http_client

    async def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        url = self._with_key(self._join_url(cfg.base_url, "/v1beta/models"), cfg.api_key)
        data = await self._request_json("GET", url)
        models = [item.get("name") for item in data.get("models", []) if item.get("name")]
        if not models:
            raise ProviderError("PROVIDER_NO_MODELS", "No models returned by provider.")
        return models

    async def generate(
        self, cfg: ProviderRuntimeConfig, messages: list[dict], stream: bool = False
    ) -> LLMResult:
        model_name = self._normalize_model(cfg.model_name)
        url = self._with_key(
            self._join_url(cfg.base_url, f"/v1beta/{model_name}:generateContent"),
            cfg.api_key,
        )
        payload = self._build_payload(messages)
        data = await self._request_json("POST", url, json=payload)
        content = self._parse_content(data)
        usage = data.get("usageMetadata", {})
        return LLMResult(
            content=content,
            model_provider=cfg.provider,
            model_name=cfg.model_name,
            token_in=self._get_int(usage, "promptTokenCount"),
            token_out=self._get_int(usage, "candidatesTokenCount"),
        )

    @staticmethod
    def _normalize_model(model_name: str) -> str:
        if model_name.startswith("models/"):
            return model_name
        return f"models/{model_name}"

    @staticmethod
    def _build_payload(messages: list[dict]) -> dict[str, Any]:
        system_text = None
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            text = message.get("content", "")
            if role == "system" and system_text is None:
                system_text = text
                continue
            gemini_role = "user" if role == "user" else "model"
            contents.append({"role": gemini_role, "parts": [{"text": text}]})
        payload: dict[str, Any] = {"contents": contents or [{"role": "user", "parts": [{"text": ""}]}]}
        if system_text:
            payload["system_instruction"] = {"parts": [{"text": system_text}]}
        return payload

    @staticmethod
    def _parse_content(data: dict[str, Any]) -> str:
        candidates = data.get("candidates", [])
        if not candidates:
            raise ProviderError("PROVIDER_PARSE_ERROR", "No candidates returned by provider.")
        parts = candidates[0].get("content", {}).get("parts", [])
        texts = [part.get("text") for part in parts if part.get("text")]
        if not texts:
            raise ProviderError("PROVIDER_PARSE_ERROR", "Provider returned empty content.")
        return "\n".join(texts)

    async def _request_json(
        self,
        method: str,
        url: str,
        json: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        response = await self._request(method, url, json=json)
        try:
            return response.json()
        except ValueError as exc:  # noqa: BLE001
            raise ProviderError("PROVIDER_PARSE_ERROR", "Invalid JSON from provider.") from exc

    async def _request(
        self, method: str, url: str, json: Optional[dict[str, Any]] = None
    ) -> httpx.Response:
        try:
            if self._client:
                response = await self._client.request(method, url, json=json)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.request(method, url, json=json)
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
            raise ProviderError("PROVIDER_BASE_URL_MISSING", "Base URL is required for Gemini.")
        base = base_url.rstrip("/")
        if base.endswith("/v1beta") and path.startswith("/v1beta/"):
            return base + path[7:]
        return base + path

    @staticmethod
    def _with_key(url: str, api_key: Optional[str]) -> str:
        if not api_key:
            raise ProviderError("API_KEY_REQUIRED", "API key is required for Gemini.")
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}key={api_key}"

    @staticmethod
    def _get_int(data: dict[str, Any], key: str) -> Optional[int]:
        value = data.get(key)
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
