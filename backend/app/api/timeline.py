from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import sanitize_text
from app.db.session import get_session
from app.db.models import TimelineMessage
from app.repos.message_repo import MessageRepo
from app.repos.branch_repo import BranchRepo
from app.repos.session_repo import SessionRepo
from app.schemas.timeline import (
    DeleteLastMessageResponse,
    InterventionCreateRequest,
    InterventionCreateResponse,
    MessageEditRequest,
    MessageEditResponse,
    TimelineMessageOut,
    TimelineResponse,
)
from app.services.memory_service import MemoryService
from app.services.report_snapshot import (
    normalize_report_snapshot,
    parse_report_snapshot,
    parse_storage_snapshot,
    snapshot_to_content,
    snapshot_to_storage_json,
)
from app.services.branch_service import (
    BranchOperationError,
    BranchService,
    get_branch_service,
)
from app.services.runner import RunnerManager, get_runner_manager
from app.utils.time_utils import utc_now

MAX_INTERVENTION_LEN = 2000
MAX_EDIT_CONTENT_LEN = 12000

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

    async with db.begin():
        session = await session_repo.get_session(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        target_branch_id = branch_id or session.active_branch_id
        if not target_branch_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Active branch is missing"
            )

        messages = await message_repo.list_messages(target_branch_id, limit)
        await _backfill_report_snapshots(messages)

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


@message_router.patch("/{session_id}/{message_id}", response_model=MessageEditResponse)
async def edit_message(
    session_id: str,
    message_id: str,
    payload: MessageEditRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> MessageEditResponse:
    """Edit one historical message and persist a fixed snapshot."""

    session_repo = SessionRepo(db)
    branch_repo = BranchRepo(db)
    message_repo = MessageRepo(db)
    memory_service: MemoryService = request.app.state.memory_service

    async with db.begin():
        session = await session_repo.get_session(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        target_branch_id = payload.branch_id or session.active_branch_id
        if not target_branch_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Active branch is missing"
            )

        branch = await branch_repo.get_branch_in_session(session_id, target_branch_id)
        if not branch:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")

        message = await message_repo.get_message(target_branch_id, message_id)
        if not message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        if message.role == "system_report":
            _apply_system_report_edit(
                message=message,
                payload=payload,
            )
        else:
            _apply_plain_message_edit(
                message=message,
                payload=payload,
            )

        message.is_user_edited = True
        message.edited_at = utc_now()
        await db.flush()

        await memory_service.invalidate_message(
            session_id=session_id,
            branch_id=message.branch_id,
            source_message_id=message.id,
            db=db,
        )
        await memory_service.remember_message(message=message, db=db)

    ws_payload = TimelineMessageOut.model_validate(message).model_dump(mode="json")
    await request.app.state.ws_manager.broadcast(
        session_id,
        {
            "event": "message_updated",
            "branch_id": message.branch_id,
            "message": ws_payload,
        },
    )
    return MessageEditResponse(message=TimelineMessageOut.model_validate(message))


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


async def _backfill_report_snapshots(messages: list[TimelineMessage]) -> None:
    for message in messages:
        if message.role != "system_report":
            continue
        if parse_storage_snapshot(message.report_snapshot_json):
            continue
        parsed = parse_report_snapshot(
            message.content,
            fallback_time_advance=message.time_jump_label,
        )
        if not parsed:
            continue
        message.report_snapshot_json = snapshot_to_storage_json(parsed)


def _apply_system_report_edit(
    *,
    message: TimelineMessage,
    payload: MessageEditRequest,
) -> dict[str, object]:
    if payload.report_snapshot is not None:
        snapshot = normalize_report_snapshot(
            payload.report_snapshot,
            fallback_time_advance=message.time_jump_label,
        )
    elif payload.content is not None:
        parsed = parse_report_snapshot(
            payload.content,
            fallback_time_advance=message.time_jump_label,
        )
        if not parsed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="System report edit requires valid report JSON content or report_snapshot",
            )
        snapshot = parsed
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No editable field provided",
        )

    message.content = sanitize_text(snapshot_to_content(snapshot), MAX_EDIT_CONTENT_LEN)
    message.report_snapshot_json = snapshot_to_storage_json(snapshot)
    return snapshot


def _apply_plain_message_edit(
    *,
    message: TimelineMessage,
    payload: MessageEditRequest,
) -> dict[str, object] | None:
    if payload.content is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="content is required for this message role",
        )
    sanitized = sanitize_text(payload.content, MAX_EDIT_CONTENT_LEN)
    if not sanitized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="content must not be empty",
        )
    message.content = sanitized
    message.report_snapshot_json = None
    return None
