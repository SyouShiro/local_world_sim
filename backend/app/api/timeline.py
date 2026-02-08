from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import sanitize_text
from app.db.session import get_session
from app.repos.message_repo import MessageRepo
from app.repos.session_repo import SessionRepo
from app.schemas.timeline import (
    DeleteLastMessageResponse,
    InterventionCreateRequest,
    InterventionCreateResponse,
    TimelineMessageOut,
    TimelineResponse,
)
from app.services.branch_service import (
    BranchOperationError,
    BranchService,
    get_branch_service,
)
from app.services.runner import RunnerManager, get_runner_manager

MAX_INTERVENTION_LEN = 2000

timeline_router = APIRouter(prefix="/api/timeline", tags=["timeline"])
message_router = APIRouter(prefix="/api/message", tags=["timeline"])
intervention_router = APIRouter(prefix="/api/intervention", tags=["timeline"])


@timeline_router.get("/{session_id}", response_model=TimelineResponse)
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


@message_router.delete("/{session_id}/last", response_model=DeleteLastMessageResponse)
async def delete_last_message(
    session_id: str,
    branch_id: str | None = Query(default=None),
    branch_service: BranchService = Depends(get_branch_service),
    runner_manager: RunnerManager = Depends(get_runner_manager),
) -> DeleteLastMessageResponse:
    """Delete the latest message in a branch (rollback by one step)."""

    if await runner_manager.is_generating(session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Runner is writing to timeline. Pause and retry deletion.",
        )

    try:
        deleted = await branch_service.delete_last_message(session_id, branch_id)
    except BranchOperationError as exc:
        raise HTTPException(status_code=_timeline_status(exc.code), detail=exc.message) from exc

    return DeleteLastMessageResponse(deleted_message_id=deleted.id, branch_id=deleted.branch_id)


@intervention_router.post("/{session_id}", response_model=InterventionCreateResponse)
async def create_intervention(
    session_id: str,
    payload: InterventionCreateRequest,
    branch_service: BranchService = Depends(get_branch_service),
) -> InterventionCreateResponse:
    """Queue a user intervention for consumption in the next generation round."""

    content = sanitize_text(payload.content, MAX_INTERVENTION_LEN)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Intervention content must not be empty",
        )

    try:
        intervention, _ = await branch_service.enqueue_intervention(
            session_id=session_id,
            branch_id=payload.branch_id,
            content=content,
        )
    except BranchOperationError as exc:
        raise HTTPException(status_code=_timeline_status(exc.code), detail=exc.message) from exc

    return InterventionCreateResponse(
        intervention_id=intervention.id,
        branch_id=intervention.branch_id,
    )


def _timeline_status(code: str) -> int:
    if code in {"SESSION_NOT_FOUND", "BRANCH_NOT_FOUND", "MESSAGE_NOT_FOUND"}:
        return status.HTTP_404_NOT_FOUND
    return status.HTTP_400_BAD_REQUEST
