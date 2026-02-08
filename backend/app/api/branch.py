from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.branch import (
    BranchForkRequest,
    BranchForkResponse,
    BranchListResponse,
    BranchOut,
    BranchSwitchRequest,
    BranchSwitchResponse,
)
from app.services.branch_service import (
    BranchOperationError,
    BranchService,
    get_branch_service,
)

router = APIRouter(prefix="/api/branch", tags=["branch"])


@router.get("/{session_id}", response_model=BranchListResponse)
async def list_branches(
    session_id: str,
    branch_service: BranchService = Depends(get_branch_service),
) -> BranchListResponse:
    """Return branches and current active branch for a session."""

    try:
        active_branch_id, branches = await branch_service.list_branches(session_id)
    except BranchOperationError as exc:
        raise HTTPException(status_code=_branch_status(exc.code), detail=exc.message) from exc

    payload = [BranchOut.model_validate(branch) for branch in branches]
    return BranchListResponse(active_branch_id=active_branch_id, branches=payload)


@router.post("/{session_id}/fork", response_model=BranchForkResponse)
async def fork_branch(
    session_id: str,
    payload: BranchForkRequest,
    branch_service: BranchService = Depends(get_branch_service),
) -> BranchForkResponse:
    """Create a new branch forked from a source branch."""

    try:
        branch = await branch_service.fork_branch(
            session_id=session_id,
            source_branch_id=payload.source_branch_id,
            from_message_id=payload.from_message_id,
        )
    except BranchOperationError as exc:
        raise HTTPException(status_code=_branch_status(exc.code), detail=exc.message) from exc

    return BranchForkResponse(branch=BranchOut.model_validate(branch))


@router.post("/{session_id}/switch", response_model=BranchSwitchResponse)
async def switch_branch(
    session_id: str,
    payload: BranchSwitchRequest,
    branch_service: BranchService = Depends(get_branch_service),
) -> BranchSwitchResponse:
    """Switch active branch for a session."""

    try:
        active_branch_id = await branch_service.switch_branch(session_id, payload.branch_id)
    except BranchOperationError as exc:
        raise HTTPException(status_code=_branch_status(exc.code), detail=exc.message) from exc

    return BranchSwitchResponse(active_branch_id=active_branch_id)


def _branch_status(code: str) -> int:
    if code in {"SESSION_NOT_FOUND", "BRANCH_NOT_FOUND", "MESSAGE_NOT_FOUND"}:
        return status.HTTP_404_NOT_FOUND
    return status.HTTP_400_BAD_REQUEST
