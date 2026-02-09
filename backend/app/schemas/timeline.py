from __future__ import annotations

import json
from datetime import datetime
from typing import Any, List, Optional

from pydantic import Field, field_validator

from app.schemas.common import APIModel


class TimelineMessageOut(APIModel):
    """Serialized timeline message."""

    id: str
    session_id: str
    branch_id: str
    seq: int
    role: str
    content: str
    time_jump_label: str
    model_provider: Optional[str]
    model_name: Optional[str]
    token_in: Optional[int]
    token_out: Optional[int]
    report_snapshot: Optional[dict[str, Any]] = Field(
        default=None,
        validation_alias="report_snapshot_json",
    )
    is_user_edited: bool = False
    edited_at: Optional[datetime] = None
    created_at: datetime

    @field_validator("report_snapshot", mode="before")
    @classmethod
    def _parse_report_snapshot(cls, value: Any) -> Optional[dict[str, Any]]:
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return None
            return payload if isinstance(payload, dict) else None
        return None


class TimelineResponse(APIModel):
    """Response containing timeline messages."""

    messages: List[TimelineMessageOut]


class DeleteLastMessageResponse(APIModel):
    """Response returned after deleting the latest message."""

    deleted_message_id: str
    branch_id: str


class InterventionCreateRequest(APIModel):
    """Payload for creating a pending intervention."""

    branch_id: Optional[str] = Field(default=None)
    content: str


class InterventionCreateResponse(APIModel):
    """Response after enqueuing an intervention."""

    intervention_id: str
    branch_id: str


class MessageEditRequest(APIModel):
    """Payload for editing a historical timeline message."""

    branch_id: Optional[str] = Field(default=None)
    content: Optional[str] = Field(default=None)
    report_snapshot: Optional[dict[str, Any]] = Field(default=None)


class MessageEditResponse(APIModel):
    """Response returned after editing a message."""

    message: TimelineMessageOut
