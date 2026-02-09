from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.runtime_settings import RuntimeSettingsPatch, RuntimeSettingsResponse
from app.services.runtime_settings_service import RuntimeSettingsService

router = APIRouter(prefix="/api/debug/settings", tags=["debug"])


def get_runtime_settings_service(request: Request) -> RuntimeSettingsService:
    """Dependency to access runtime settings service from app state."""

    return request.app.state.runtime_settings_service


@router.get("", response_model=RuntimeSettingsResponse)
async def get_runtime_settings(
    runtime_service: RuntimeSettingsService = Depends(get_runtime_settings_service),
) -> RuntimeSettingsResponse:
    """Return runtime settings currently active in process memory."""

    return RuntimeSettingsResponse(settings=runtime_service.get_settings())


@router.patch("", response_model=RuntimeSettingsResponse)
async def patch_runtime_settings(
    payload: RuntimeSettingsPatch,
    runtime_service: RuntimeSettingsService = Depends(get_runtime_settings_service),
) -> RuntimeSettingsResponse:
    """Apply runtime settings updates without process restart."""

    try:
        settings_map = runtime_service.update_settings(
            payload.updates,
            persist=payload.persist,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RuntimeSettingsResponse(settings=settings_map)
