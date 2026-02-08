from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.repos.message_repo import MessageRepo
from app.repos.session_repo import SessionRepo
from app.schemas.timeline import TimelineMessageOut, TimelineResponse

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


@router.get("/{session_id}", response_model=TimelineResponse)
async def get_timeline(
    session_id: str,
    branch_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
) -> TimelineResponse:
    """Return timeline messages for the requested branch."""

    session_repo = SessionRepo(db)
    message_repo = MessageRepo(db)

    session = await session_repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    target_branch_id = branch_id or session.active_branch_id
    if not target_branch_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Active branch is missing"
        )

    messages = await message_repo.list_messages(target_branch_id, limit)
    payload = [TimelineMessageOut.model_validate(msg) for msg in messages]
    return TimelineResponse(messages=payload)
