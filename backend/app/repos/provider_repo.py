from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProviderConfig
from app.utils.time_utils import utc_now


class ProviderRepo:
    """Repository for provider configuration persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_session(self, session_id: str) -> Optional[ProviderConfig]:
        """Fetch provider configuration for a session."""

        result = await self._db.execute(
            select(ProviderConfig).where(ProviderConfig.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def upsert_config(
        self,
        config_id: str,
        session_id: str,
        provider: str,
        base_url: Optional[str],
        api_key_encrypted: Optional[str],
        model_name: Optional[str],
        extra_json: Optional[str] = None,
    ) -> ProviderConfig:
        """Insert or update provider configuration for a session."""

        existing = await self.get_by_session(session_id)
        if existing:
            existing.provider = provider
            existing.base_url = base_url
            existing.api_key_encrypted = api_key_encrypted
            existing.model_name = model_name
            existing.extra_json = extra_json
            existing.updated_at = utc_now()
            await self._db.flush()
            return existing

        config = ProviderConfig(
            id=config_id,
            session_id=session_id,
            provider=provider,
            base_url=base_url,
            api_key_encrypted=api_key_encrypted,
            model_name=model_name,
            extra_json=extra_json,
            updated_at=utc_now(),
        )
        self._db.add(config)
        await self._db.flush()
        return config

    async def update_model(self, session_id: str, model_name: str) -> Optional[ProviderConfig]:
        """Update the selected model for the session provider."""

        config = await self.get_by_session(session_id)
        if not config:
            return None
        config.model_name = model_name
        config.updated_at = utc_now()
        await self._db.flush()
        return config
