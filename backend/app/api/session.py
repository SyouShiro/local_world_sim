from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import sanitize_text
from app.db.session import get_session
from app.repos.branch_repo import BranchRepo
from app.repos.session_repo import SessionRepo
from app.schemas.session import (
    SessionCreateRequest,
    SessionCreateResponse,
    SessionSettingsPatch,
    SessionStateResponse,
)
from app.providers.base import ProviderError
from app.services.provider_service import ProviderService, get_provider_service
from app.services.runner import RunnerManager, get_runner_manager

router = APIRouter(prefix="/api/session", tags=["session"])

MAX_TITLE_LEN = 200
MAX_PRESET_LEN = 8000
MAX_TICK_LABEL_LEN = 50


@router.post("/create", response_model=SessionCreateResponse)
async def create_session(
    payload: SessionCreateRequest,
    db: AsyncSession = Depends(get_session),
) -> SessionCreateResponse:
    """Create a new simulation session and default branch."""

    settings = get_settings()
    title = sanitize_text(payload.title or "", MAX_TITLE_LEN) or None
    world_preset = sanitize_text(payload.world_preset, MAX_PRESET_LEN)
    tick_label = sanitize_text(
        payload.tick_label or settings.default_tick_label, MAX_TICK_LABEL_LEN
    )
    post_gen_delay_sec = (
        payload.post_gen_delay_sec
        if payload.post_gen_delay_sec is not None
        else settings.default_post_gen_delay_sec
    )

    session_id = uuid.uuid4().hex
    branch_id = uuid.uuid4().hex

    session_repo = SessionRepo(db)
    branch_repo = BranchRepo(db)

    async with db.begin():
        await session_repo.create_session(
            session_id=session_id,
            active_branch_id=branch_id,
            title=title,
            world_preset=world_preset,
            tick_label=tick_label,
            post_gen_delay_sec=post_gen_delay_sec,
        )
        await branch_repo.create_branch(
            branch_id=branch_id,
            session_id=session_id,
            name="main",
        )

    return SessionCreateResponse(
        session_id=session_id,
        active_branch_id=branch_id,
        running=False,
    )


@router.post("/{session_id}/start", response_model=SessionStateResponse)
async def start_session(
    session_id: str,
    runner: RunnerManager = Depends(get_runner_manager),
    provider_service: ProviderService = Depends(get_provider_service),
    db: AsyncSession = Depends(get_session),
) -> SessionStateResponse:
    """Start the session runner."""

    await _ensure_session_exists(session_id, db)
    await _ensure_provider_ready(session_id, provider_service)
    running = await runner.start(session_id)
    if running is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return SessionStateResponse(running=running)


@router.post("/{session_id}/pause", response_model=SessionStateResponse)
async def pause_session(
    session_id: str,
    runner: RunnerManager = Depends(get_runner_manager),
) -> SessionStateResponse:
    """Pause the session runner."""

    running = await runner.pause(session_id)
    if running is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return SessionStateResponse(running=running)


@router.post("/{session_id}/resume", response_model=SessionStateResponse)
async def resume_session(
    session_id: str,
    runner: RunnerManager = Depends(get_runner_manager),
    provider_service: ProviderService = Depends(get_provider_service),
    db: AsyncSession = Depends(get_session),
) -> SessionStateResponse:
    """Resume the session runner."""

    await _ensure_session_exists(session_id, db)
    await _ensure_provider_ready(session_id, provider_service)
    running = await runner.resume(session_id)
    if running is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return SessionStateResponse(running=running)


@router.patch("/{session_id}/settings", response_model=SessionStateResponse)
async def update_settings(
    session_id: str,
    payload: SessionSettingsPatch,
    db: AsyncSession = Depends(get_session),
) -> SessionStateResponse:
    """Update mutable session settings."""

    tick_label = (
        sanitize_text(payload.tick_label, MAX_TICK_LABEL_LEN)
        if payload.tick_label is not None
        else None
    )
    session_repo = SessionRepo(db)
    async with db.begin():
        session = await session_repo.update_settings(
            session_id=session_id,
            tick_label=tick_label,
            post_gen_delay_sec=payload.post_gen_delay_sec,
        )
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
            )

    return SessionStateResponse(running=session.running)


async def _ensure_provider_ready(
    session_id: str, provider_service: ProviderService
) -> None:
    try:
        await provider_service.ensure_ready(session_id)
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        ) from exc


async def _ensure_session_exists(session_id: str, db: AsyncSession) -> None:
    session_repo = SessionRepo(db)
    session = await session_repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
