from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

import httpx


@dataclass
class ProviderRuntimeConfig:
    """Runtime configuration needed by an LLM adapter."""

    provider: str
    model_name: str
    base_url: str | None = None
    api_key: str | None = None


@dataclass
class LLMResult:
    """Result returned from an LLM generation call."""

    content: str
    model_provider: str
    model_name: str
    token_in: int | None = None
    token_out: int | None = None


class LLMAdapter(Protocol):
    """Adapter interface for LLM providers."""

    async def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        """List available models for the provider."""

    async def generate(
        self, cfg: ProviderRuntimeConfig, messages: list[dict], stream: bool = False
    ) -> LLMResult:
        """Generate a response from the provider."""


class ProviderError(RuntimeError):
    """Raised when a provider operation fails."""

    def __init__(
        self,
        code: str,
        message: str,
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code


def build_status_error(response: httpx.Response) -> ProviderError:
    """Build a normalized provider error from an HTTP response."""

    status = response.status_code
    message = _extract_response_message(response)
    formatted = f"Provider returned {status}: {message}"
    if status in {408, 429}:
        code = "PROVIDER_TIMEOUT" if status == 408 else "PROVIDER_RATE_LIMIT"
        return ProviderError(code, formatted, retryable=True, status_code=status)
    if status >= 500:
        return ProviderError(
            "PROVIDER_UPSTREAM",
            formatted,
            retryable=True,
            status_code=status,
        )
    return ProviderError("PROVIDER_BAD_STATUS", formatted, status_code=status)


def require_api_key(api_key: Optional[str], provider_name: str) -> str:
    """Return an API key or raise a normalized configuration error."""

    if api_key:
        return api_key
    raise ProviderError("API_KEY_REQUIRED", f"API key is required for {provider_name}.")


def _extract_response_message(response: httpx.Response) -> str:
    """Extract a concise error message from provider JSON/text payloads."""

    try:
        payload: Any = response.json()
    except ValueError:
        return (response.text or "Unknown error from provider.").strip()

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            detail = error.get("message") or error.get("code")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()
        if isinstance(error, str) and error.strip():
            return error.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return (response.text or "Unknown error from provider.").strip()


class HTTPProviderAdapter:
    """Shared HTTP behavior for provider adapters."""

    def __init__(
        self, timeout_sec: float = 90, http_client: Optional[httpx.AsyncClient] = None
    ) -> None:
        self._timeout = timeout_sec
        self._client = http_client

    async def _request_json(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        response = await self._request(method, url, headers=headers, json=json)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("PROVIDER_PARSE_ERROR", "Invalid JSON from provider.") from exc
        if not isinstance(payload, dict):
            raise ProviderError("PROVIDER_PARSE_ERROR", "Provider returned invalid JSON payload.")
        return payload

    async def _request(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> httpx.Response:
        try:
            if self._client:
                response = await self._client.request(
                    method, url, headers=headers, json=json, timeout=self._timeout
                )
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
            raise build_status_error(response)
        return response


class MockAdapter:
    """Mock adapter used for offline simulation in early milestones."""

    async def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        return [cfg.model_name or "mock-1"]

    async def generate(
        self, cfg: ProviderRuntimeConfig, messages: list[dict], stream: bool = False
    ) -> LLMResult:
        timestamp = datetime.now(timezone.utc).isoformat()
        time_advance = "tick"
        for message in reversed(messages):
            if message.get("role") != "user":
                continue
            for line in message.get("content", "").splitlines():
                if line.startswith("Time advance label:"):
                    time_advance = line.split(":", 1)[1].strip() or time_advance
                    break
        content = (
            "{"
            "\"title\":\"Worldline Report\","
            f"\"time_advance\":\"{time_advance}\","
            f"\"summary\":\"Mock report generated at {timestamp}.\","
            "\"events\":[\"Stability holds\",\"Minor shifts detected\"],"
            "\"risks\":[\"External shock possible\"]"
            "}"
        )
        return LLMResult(
            content=content,
            model_provider=cfg.provider,
            model_name=cfg.model_name,
            token_in=None,
            token_out=None,
        )
