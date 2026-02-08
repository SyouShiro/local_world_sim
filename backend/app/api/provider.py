from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.providers.base import ProviderError
from app.schemas.provider import (
    ProviderModelsResponse,
    ProviderSelectRequest,
    ProviderSelectResponse,
    ProviderSetRequest,
    ProviderSetResponse,
)
from app.services.provider_service import ProviderService, get_provider_service

router = APIRouter(prefix="/api/provider", tags=["provider"])


@router.post("/{session_id}/set", response_model=ProviderSetResponse)
async def set_provider(
    session_id: str,
    payload: ProviderSetRequest,
    provider_service: ProviderService = Depends(get_provider_service),
) -> ProviderSetResponse:
    """Set provider configuration and validate availability."""

    try:
        config = await provider_service.set_provider(
            session_id=session_id,
            provider=payload.provider,
            api_key=payload.api_key,
            base_url=payload.base_url,
            model_name=payload.model_name,
        )
    except ProviderError as exc:
        raise HTTPException(
            status_code=_provider_status(exc.code),
            detail=exc.message,
        ) from exc
    return ProviderSetResponse(provider=config.provider, model_name=config.model_name)


@router.get("/{session_id}/models", response_model=ProviderModelsResponse)
async def list_models(
    session_id: str,
    provider: str,
    provider_service: ProviderService = Depends(get_provider_service),
) -> ProviderModelsResponse:
    """List available models for the provider."""

    try:
        models = await provider_service.list_models(session_id, provider)
    except ProviderError as exc:
        raise HTTPException(
            status_code=_provider_status(exc.code),
            detail=exc.message,
        ) from exc
    return ProviderModelsResponse(provider=provider, models=models)


@router.post("/{session_id}/select-model", response_model=ProviderSelectResponse)
async def select_model(
    session_id: str,
    payload: ProviderSelectRequest,
    provider_service: ProviderService = Depends(get_provider_service),
) -> ProviderSelectResponse:
    """Select a model for the configured provider."""

    try:
        config = await provider_service.select_model(session_id, payload.model_name)
    except ProviderError as exc:
        raise HTTPException(
            status_code=_provider_status(exc.code),
            detail=exc.message,
        ) from exc
    return ProviderSelectResponse(model_name=config.model_name or "")


def _provider_status(code: str) -> int:
    if code in {
        "PROVIDER_NOT_READY",
        "PROVIDER_CONFIG_MISSING",
        "API_KEY_REQUIRED",
        "PROVIDER_MODEL_INVALID",
        "PROVIDER_BASE_URL_MISSING",
    }:
        return status.HTTP_400_BAD_REQUEST
    if code in {"PROVIDER_UNSUPPORTED"}:
        return status.HTTP_400_BAD_REQUEST
    if code in {"APP_SECRET_MISSING"}:
        return status.HTTP_500_INTERNAL_SERVER_ERROR
    if code in {
        "PROVIDER_BAD_STATUS",
        "PROVIDER_RATE_LIMIT",
        "PROVIDER_UPSTREAM",
        "PROVIDER_TIMEOUT",
        "PROVIDER_CONNECTION_ERROR",
        "PROVIDER_PARSE_ERROR",
        "PROVIDER_NO_MODELS",
    }:
        return status.HTTP_502_BAD_GATEWAY
    return status.HTTP_502_BAD_GATEWAY
