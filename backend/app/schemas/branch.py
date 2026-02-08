from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import Field

from app.schemas.common import APIModel


class BranchOut(APIModel):
    """Serialized branch metadata."""

    id: str
    session_id: str
    name: str
    parent_branch_id: Optional[str]
    fork_from_message_id: Optional[str]
    created_at: datetime


class BranchListResponse(APIModel):
    """Response with all active branches for a session."""

    active_branch_id: Optional[str]
    branches: List[BranchOut]


class BranchForkRequest(APIModel):
    """Request payload for forking from a source branch."""

    source_branch_id: str
    from_message_id: Optional[str] = Field(default=None)


class BranchForkResponse(APIModel):
    """Response payload after creating a forked branch."""

    branch: BranchOut


class BranchSwitchRequest(APIModel):
    """Request payload for switching active branch."""

    branch_id: str


class BranchSwitchResponse(APIModel):
    """Response payload for branch switching."""

    active_branch_id: str
