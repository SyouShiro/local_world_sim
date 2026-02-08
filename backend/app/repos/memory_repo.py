from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MemoryEmbedding, MemoryItem
from app.utils.time_utils import utc_now


class MemoryRepo:
    """Repository for vector-memory persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def upsert_memory_item(
        self,
        *,
        item_id: str,
        session_id: str,
        branch_id: str,
        source_message_id: str,
        source_message_seq: int,
        source_role: str,
        content: str,
        content_hash: str,
    ) -> MemoryItem:
        """Insert or refresh a memory item for a message payload."""

        existing = await self._get_memory_item(branch_id, source_message_id, content_hash)
        if existing:
            existing.source_message_seq = source_message_seq
            existing.source_role = source_role
            existing.content = content
            existing.is_active = True
            existing.invalidated_at = None
            await self._db.flush()
            return existing

        item = MemoryItem(
            id=item_id,
            session_id=session_id,
            branch_id=branch_id,
            source_message_id=source_message_id,
            source_message_seq=source_message_seq,
            source_role=source_role,
            content=content,
            content_hash=content_hash,
            is_active=True,
            created_at=utc_now(),
            invalidated_at=None,
        )
        self._db.add(item)
        await self._db.flush()
        return item

    async def upsert_embedding(
        self,
        *,
        embedding_id: str,
        memory_item_id: str,
        provider: str,
        model_name: str,
        dim: int,
        vector_json: str,
        vector_norm: float,
    ) -> MemoryEmbedding:
        """Insert or update vector payload for a memory item."""

        existing = await self._get_embedding(memory_item_id)
        if existing:
            existing.provider = provider
            existing.model_name = model_name
            existing.dim = dim
            existing.vector_json = vector_json
            existing.vector_norm = vector_norm
            await self._db.flush()
            return existing

        embedding = MemoryEmbedding(
            id=embedding_id,
            memory_item_id=memory_item_id,
            provider=provider,
            model_name=model_name,
            dim=dim,
            vector_json=vector_json,
            vector_norm=vector_norm,
            created_at=utc_now(),
        )
        self._db.add(embedding)
        await self._db.flush()
        return embedding

    async def list_active_vectors(
        self, *, session_id: str, branch_id: str, limit: int
    ) -> list[tuple[MemoryItem, MemoryEmbedding]]:
        """List active memory item + embedding pairs by recency."""

        stmt = (
            select(MemoryItem, MemoryEmbedding)
            .join(MemoryEmbedding, MemoryEmbedding.memory_item_id == MemoryItem.id)
            .where(
                MemoryItem.session_id == session_id,
                MemoryItem.branch_id == branch_id,
                MemoryItem.is_active.is_(True),
            )
            .order_by(MemoryItem.source_message_seq.desc(), MemoryItem.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.tuples())

    async def tombstone_by_message(
        self, *, session_id: str, branch_id: str, source_message_id: str
    ) -> int:
        """Invalidate all memory items linked to a timeline message."""

        result = await self._db.execute(
            select(MemoryItem).where(
                MemoryItem.session_id == session_id,
                MemoryItem.branch_id == branch_id,
                MemoryItem.source_message_id == source_message_id,
                MemoryItem.is_active.is_(True),
            )
        )
        now = utc_now()
        count = 0
        for item in result.scalars():
            item.is_active = False
            item.invalidated_at = now
            count += 1
        if count:
            await self._db.flush()
        return count

    async def _get_memory_item(
        self, branch_id: str, source_message_id: str, content_hash: str
    ) -> Optional[MemoryItem]:
        result = await self._db.execute(
            select(MemoryItem).where(
                MemoryItem.branch_id == branch_id,
                MemoryItem.source_message_id == source_message_id,
                MemoryItem.content_hash == content_hash,
            )
        )
        return result.scalar_one_or_none()

    async def _get_embedding(self, memory_item_id: str) -> Optional[MemoryEmbedding]:
        result = await self._db.execute(
            select(MemoryEmbedding).where(MemoryEmbedding.memory_item_id == memory_item_id)
        )
        return result.scalar_one_or_none()
