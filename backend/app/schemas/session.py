from __future__ import annotations

from typing import Optional

from pydantic import Field

from app.schemas.common import APIModel


class SessionCreateRequest(APIModel):
    """Payload for creating a new world session."""

    title: Optional[str] = Field(default=None)
    world_preset: str
    tick_label: Optional[str] = Field(default=None)
    post_gen_delay_sec: Optional[int] = Field(default=None, ge=1, le=3600)
    output_language: Optional[str] = Field(default=None, min_length=2, max_length=20)


class SessionCreateResponse(APIModel):
    """Response returned after creating a session."""

    session_id: str
    active_branch_id: str
    running: bool


class SessionSettingsPatch(APIModel):
    """Payload for updating session settings."""

    tick_label: Optional[str] = Field(default=None)
    post_gen_delay_sec: Optional[int] = Field(default=None, ge=1, le=3600)
    output_language: Optional[str] = Field(default=None, min_length=2, max_length=20)


class SessionStateResponse(APIModel):
    """Response for session running state."""

    running: bool
