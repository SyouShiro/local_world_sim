from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import sanitize_text
from app.db.session import get_session
from app.repos.branch_repo import BranchRepo
from app.repos.session_pref_repo import SessionPreferenceRepo
from app.repos.session_repo import SessionRepo
from app.schemas.session import (
    SessionCreateRequest,
    SessionCreateResponse,
    SessionDetailResponse,
    SessionHistoryItem,
    SessionHistoryResponse,
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
DEFAULT_OUTPUT_LANGUAGE = "zh-cn"
DEFAULT_TIMELINE_STEP_UNIT = "month"
DEFAULT_TIMELINE_STEP_VALUE = 1


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
    output_language = _normalize_language(payload.output_language)
    timeline_start_iso = _normalize_timeline_start(payload.timeline_start_iso)
    timeline_step_value = payload.timeline_step_value or DEFAULT_TIMELINE_STEP_VALUE
    timeline_step_unit = _normalize_timeline_step_unit(payload.timeline_step_unit)

    session_id = uuid.uuid4().hex
    branch_id = uuid.uuid4().hex

    session_repo = SessionRepo(db)
    branch_repo = BranchRepo(db)
    preference_repo = SessionPreferenceRepo(db)

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
        await preference_repo.upsert_preferences(
            session_id,
            output_language=output_language,
            timeline_start_iso=timeline_start_iso,
            timeline_step_value=timeline_step_value,
            timeline_step_unit=timeline_step_unit,
        )

    return SessionCreateResponse(
        session_id=session_id,
        active_branch_id=branch_id,
        running=False,
        output_language=output_language,
        timeline_start_iso=timeline_start_iso,
        timeline_step_value=timeline_step_value,
        timeline_step_unit=timeline_step_unit,
    )


@router.get("/history", response_model=SessionHistoryResponse)
async def list_session_history(
    limit: int = Query(default=30, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
) -> SessionHistoryResponse:
    """List recent local sessions for resume/replay."""

    session_repo = SessionRepo(db)
    sessions = await session_repo.list_recent_sessions(limit=limit)
    return SessionHistoryResponse(
        sessions=[
            SessionHistoryItem(
                session_id=item.id,
                title=item.title,
                active_branch_id=item.active_branch_id,
                running=item.running,
                updated_at=item.updated_at,
                created_at=item.created_at,
            )
            for item in sessions
        ]
    )


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(
    session_id: str,
    db: AsyncSession = Depends(get_session),
) -> SessionDetailResponse:
    """Return session detail including timeline/language preferences."""

    session_repo = SessionRepo(db)
    pref_repo = SessionPreferenceRepo(db)
    session = await session_repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    preference = await pref_repo.get_by_session(session_id)
    return SessionDetailResponse(
        session_id=session.id,
        title=session.title,
        world_preset=session.world_preset,
        tick_label=session.tick_label,
        post_gen_delay_sec=session.post_gen_delay_sec,
        running=session.running,
        active_branch_id=session.active_branch_id,
        output_language=preference.output_language if preference else None,
        timeline_start_iso=preference.timeline_start_iso if preference else None,
        timeline_step_value=preference.timeline_step_value if preference else None,
        timeline_step_unit=preference.timeline_step_unit if preference else None,
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
    output_language = (
        _normalize_language(payload.output_language)
        if payload.output_language is not None
        else None
    )
    timeline_start_iso = (
        _normalize_timeline_start(payload.timeline_start_iso)
        if payload.timeline_start_iso is not None
        else None
    )
    timeline_step_value = payload.timeline_step_value
    timeline_step_unit = (
        _normalize_timeline_step_unit(payload.timeline_step_unit)
        if payload.timeline_step_unit is not None
        else None
    )
    session_repo = SessionRepo(db)
    preference_repo = SessionPreferenceRepo(db)
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
        if (
            output_language is not None
            or timeline_start_iso is not None
            or timeline_step_value is not None
            or timeline_step_unit is not None
        ):
            await preference_repo.upsert_preferences(
                session_id,
                output_language=output_language,
                timeline_start_iso=timeline_start_iso,
                timeline_step_value=timeline_step_value,
                timeline_step_unit=timeline_step_unit,
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


def _normalize_language(value: str | None) -> str:
    if not value:
        return DEFAULT_OUTPUT_LANGUAGE
    normalized = value.strip().lower().replace("_", "-")
    if not normalized:
        return DEFAULT_OUTPUT_LANGUAGE
    return normalized


def _normalize_timeline_step_unit(value: str | None) -> str:
    normalized = (value or DEFAULT_TIMELINE_STEP_UNIT).strip().lower()
    if normalized not in {"day", "week", "month", "year"}:
        return DEFAULT_TIMELINE_STEP_UNIT
    return normalized


def _normalize_timeline_start(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    candidate = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return datetime.now(timezone.utc).isoformat()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()
