from __future__ import annotations

from typing import List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TimelineMessage, UserIntervention
from app.utils.time_utils import utc_now


class MessageRepo:
    """Repository for timeline message and intervention persistence."""

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

    async def list_messages_up_to_seq(
        self, branch_id: str, max_seq: int
    ) -> List[TimelineMessage]:
        """Return branch messages from seq=1 to max_seq."""

        result = await self._db.execute(
            select(TimelineMessage)
            .where(TimelineMessage.branch_id == branch_id, TimelineMessage.seq <= max_seq)
            .order_by(TimelineMessage.seq.asc())
        )
        return list(result.scalars())

    async def get_message(
        self, branch_id: str, message_id: str
    ) -> Optional[TimelineMessage]:
        """Fetch a message by ID constrained to a branch."""

        result = await self._db.execute(
            select(TimelineMessage).where(
                TimelineMessage.id == message_id,
                TimelineMessage.branch_id == branch_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_last_message(self, branch_id: str) -> Optional[TimelineMessage]:
        """Fetch the latest message in a branch."""

        result = await self._db.execute(
            select(TimelineMessage)
            .where(TimelineMessage.branch_id == branch_id)
            .order_by(TimelineMessage.seq.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def delete_last_message(self, branch_id: str) -> Optional[TimelineMessage]:
        """Delete and return the latest message in a branch."""

        message = await self.get_last_message(branch_id)
        if not message:
            return None
        await self._db.execute(delete(TimelineMessage).where(TimelineMessage.id == message.id))
        await self._db.flush()
        return message

    async def add_intervention(
        self, intervention_id: str, session_id: str, branch_id: str, content: str
    ) -> UserIntervention:
        """Insert a pending intervention."""

        intervention = UserIntervention(
            id=intervention_id,
            session_id=session_id,
            branch_id=branch_id,
            content=content,
            status="pending",
            created_at=utc_now(),
            consumed_at=None,
        )
        self._db.add(intervention)
        await self._db.flush()
        return intervention

    async def list_pending_interventions(
        self, session_id: str, branch_id: str, limit: int = 20
    ) -> List[UserIntervention]:
        """List pending interventions in FIFO order."""

        result = await self._db.execute(
            select(UserIntervention)
            .where(
                UserIntervention.session_id == session_id,
                UserIntervention.branch_id == branch_id,
                UserIntervention.status == "pending",
            )
            .order_by(UserIntervention.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars())

    async def mark_interventions_consumed(self, intervention_ids: list[str]) -> None:
        """Mark interventions as consumed after generation succeeds."""

        if not intervention_ids:
            return
        result = await self._db.execute(
            select(UserIntervention).where(UserIntervention.id.in_(intervention_ids))
        )
        now = utc_now()
        for intervention in result.scalars():
            intervention.status = "consumed"
            intervention.consumed_at = now
        await self._db.flush()

    async def clone_messages_to_branch(
        self,
        source_messages: list[TimelineMessage],
        session_id: str,
        target_branch_id: str,
    ) -> list[TimelineMessage]:
        """Copy source messages to a target branch preserving sequence numbers."""

        copied_messages: list[TimelineMessage] = []
        for source in source_messages:
            copied = TimelineMessage(
                id=self._new_id(),
                session_id=session_id,
                branch_id=target_branch_id,
                seq=source.seq,
                role=source.role,
                content=source.content,
                time_jump_label=source.time_jump_label,
                model_provider=source.model_provider,
                model_name=source.model_name,
                token_in=source.token_in,
                token_out=source.token_out,
                created_at=utc_now(),
            )
            self._db.add(copied)
            copied_messages.append(copied)
        await self._db.flush()
        return copied_messages

    @staticmethod
    def _new_id() -> str:
        import uuid

        return uuid.uuid4().hex
