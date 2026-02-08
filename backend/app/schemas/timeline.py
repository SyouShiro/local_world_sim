from __future__ import annotations

from datetime import datetime
from typing import List, Optional

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
