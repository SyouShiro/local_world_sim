from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from app.schemas.common import APIModel


class ProviderSetRequest(APIModel):
    """Payload for setting a provider configuration."""

    provider: str
    api_key: Optional[str] = Field(default=None)
    base_url: Optional[str] = Field(default=None)
    model_name: Optional[str] = Field(default=None)


class ProviderSetResponse(APIModel):
    """Response returned after setting provider configuration."""

    provider: str
    model_name: Optional[str]


class ProviderModelsResponse(APIModel):
    """Response containing available models for a provider."""

    provider: str
    models: List[str]


class ProviderSelectRequest(APIModel):
    """Payload for selecting a model."""

    model_name: str


class ProviderSelectResponse(APIModel):
    """Response returned after selecting a model."""

    model_name: str
