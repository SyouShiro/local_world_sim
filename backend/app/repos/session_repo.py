from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WorldSession
from app.utils.time_utils import utc_now


class SessionRepo:
    """Repository for world session persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_session(
        self,
        session_id: str,
        active_branch_id: str,
        title: Optional[str],
        world_preset: str,
        tick_label: str,
        post_gen_delay_sec: int,
    ) -> WorldSession:
        """Persist a new session and return it."""

        session = WorldSession(
            id=session_id,
            title=title,
            world_preset=world_preset,
            running=False,
            tick_label=tick_label,
            post_gen_delay_sec=post_gen_delay_sec,
            active_branch_id=active_branch_id,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self._db.add(session)
        await self._db.flush()
        return session

    async def get_session(self, session_id: str) -> Optional[WorldSession]:
        """Fetch a session by ID."""

        result = await self._db.execute(
            select(WorldSession).where(WorldSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def update_running(self, session_id: str, running: bool) -> Optional[WorldSession]:
        """Set the running flag for a session and return the updated row."""

        session = await self.get_session(session_id)
        if not session:
            return None
        session.running = running
        session.updated_at = utc_now()
        await self._db.flush()
        return session

    async def update_settings(
        self, session_id: str, tick_label: Optional[str], post_gen_delay_sec: Optional[int]
    ) -> Optional[WorldSession]:
        """Update mutable settings for a session."""

        session = await self.get_session(session_id)
        if not session:
            return None
        if tick_label is not None:
            session.tick_label = tick_label
        if post_gen_delay_sec is not None:
            session.post_gen_delay_sec = post_gen_delay_sec
        session.updated_at = utc_now()
        await self._db.flush()
        return session

    async def update_active_branch(
        self, session_id: str, active_branch_id: str
    ) -> Optional[WorldSession]:
        """Switch the active branch for a session."""

        session = await self.get_session(session_id)
        if not session:
            return None
        session.active_branch_id = active_branch_id
        session.updated_at = utc_now()
        await self._db.flush()
        return session

    async def list_recent_sessions(self, limit: int = 30) -> list[WorldSession]:
        """List recent sessions ordered by update time descending."""

        result = await self._db.execute(
            select(WorldSession)
            .order_by(WorldSession.updated_at.desc(), WorldSession.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
