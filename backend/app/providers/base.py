from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


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
