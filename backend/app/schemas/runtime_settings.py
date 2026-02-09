from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import APIModel


class RuntimeSettingsResponse(APIModel):
    """Current runtime settings map."""

    settings: dict[str, Any]


class RuntimeSettingsPatch(APIModel):
    """Partial runtime settings update payload."""

    updates: dict[str, Any] = Field(default_factory=dict)
    persist: bool = Field(default=True)
