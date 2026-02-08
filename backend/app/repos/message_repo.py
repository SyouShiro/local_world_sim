from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TimelineMessage
from app.utils.time_utils import utc_now


class MessageRepo:
    """Repository for timeline message persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _next_seq(self, branch_id: str) -> int:
        result = await self._db.execute(
            select(func.max(TimelineMessage.seq)).where(TimelineMessage.branch_id == branch_id)
        )
        max_seq = result.scalar_one() or 0
        return int(max_seq) + 1

    async def add_message(
        self,
        message_id: str,
        session_id: str,
        branch_id: str,
        role: str,
        content: str,
        time_jump_label: str,
        model_provider: Optional[str],
        model_name: Optional[str],
        token_in: Optional[int],
        token_out: Optional[int],
    ) -> TimelineMessage:
        """Insert a new timeline message with an incremented sequence number."""

        for attempt in range(3):
            try:
                seq = await self._next_seq(branch_id)
                message = TimelineMessage(
                    id=message_id,
                    session_id=session_id,
                    branch_id=branch_id,
                    seq=seq,
                    role=role,
                    content=content,
                    time_jump_label=time_jump_label,
                    model_provider=model_provider,
                    model_name=model_name,
                    token_in=token_in,
                    token_out=token_out,
                    created_at=utc_now(),
                )
                self._db.add(message)
                await self._db.flush()
                return message
            except IntegrityError:
                await self._db.rollback()
                if attempt == 2:
                    raise
        raise RuntimeError("Failed to insert timeline message after retries")

    async def list_messages(self, branch_id: str, limit: int) -> List[TimelineMessage]:
        """Return the most recent messages for a branch in ascending order."""

        stmt = (
            select(TimelineMessage)
            .where(TimelineMessage.branch_id == branch_id)
            .order_by(TimelineMessage.seq.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        rows = list(result.scalars())
        rows.reverse()
        return rows
