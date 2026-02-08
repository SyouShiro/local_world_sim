from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import Field

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
    created_at: datetime


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
