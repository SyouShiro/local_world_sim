from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import Field

from app.schemas.common import APIModel

ProviderName = Literal["openai", "ollama", "deepseek", "gemini"]


class ProviderSetRequest(APIModel):
    """Payload for setting a provider configuration."""

    provider: ProviderName
    api_key: Optional[str] = Field(default=None)
    base_url: Optional[str] = Field(default=None)
    model_name: Optional[str] = Field(default=None)


class ProviderSetResponse(APIModel):
    """Response returned after setting provider configuration."""

    provider: ProviderName
    model_name: Optional[str]


class ProviderModelsResponse(APIModel):
    """Response containing available models for a provider."""

    provider: ProviderName
    models: List[str]


class ProviderSelectRequest(APIModel):
    """Payload for selecting a model."""

    model_name: str


class ProviderSelectResponse(APIModel):
    """Response returned after selecting a model."""

    model_name: str
