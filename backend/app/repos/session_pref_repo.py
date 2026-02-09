from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SessionPreference
from app.utils.time_utils import utc_now


class SessionPreferenceRepo:
    """Repository for session-level preference persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_session(self, session_id: str) -> Optional[SessionPreference]:
        """Fetch preferences by session ID."""

        result = await self._db.execute(
            select(SessionPreference).where(SessionPreference.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def upsert_preferences(
        self,
        session_id: str,
        *,
        output_language: Optional[str] = None,
        timeline_start_iso: Optional[str] = None,
        timeline_step_value: Optional[int] = None,
        timeline_step_unit: Optional[str] = None,
    ) -> SessionPreference:
        """Insert or update session preferences."""

        preference = await self.get_by_session(session_id)
        now = utc_now()
        if preference:
            if output_language is not None:
                preference.output_language = output_language
            if timeline_start_iso is not None:
                preference.timeline_start_iso = timeline_start_iso
            if timeline_step_value is not None:
                preference.timeline_step_value = timeline_step_value
            if timeline_step_unit is not None:
                preference.timeline_step_unit = timeline_step_unit
            preference.updated_at = now
            await self._db.flush()
            return preference

        created = SessionPreference(
            session_id=session_id,
            output_language=output_language or "zh-cn",
            timeline_start_iso=timeline_start_iso,
            timeline_step_value=timeline_step_value or 1,
            timeline_step_unit=timeline_step_unit or "month",
            created_at=now,
            updated_at=now,
        )
        self._db.add(created)
        await self._db.flush()
        return created

    async def upsert_output_language(
        self, session_id: str, output_language: str
    ) -> SessionPreference:
        """Insert or update output language preference."""

        return await self.upsert_preferences(
            session_id,
            output_language=output_language,
        )
