from __future__ import annotations

import json
import math
import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.types import MemoryItemPayload, MemorySearchResult
from app.repos.memory_repo import MemoryRepo


class VectorStore(ABC):
    """Abstract vector-memory storage backend."""

    @abstractmethod
    async def upsert_item(
        self,
        *,
        db: AsyncSession,
        item: MemoryItemPayload,
        embedding: Sequence[float],
        embed_provider: str,
        embed_model: str,
    ) -> None:
        """Insert or update one memory item and vector."""

    @abstractmethod
    async def search(
        self,
        *,
        db: AsyncSession,
        session_id: str,
        branch_id: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[MemorySearchResult]:
        """Search top-k memory snippets in one branch scope."""

    @abstractmethod
    async def tombstone_by_message(
        self,
        *,
        db: AsyncSession,
        session_id: str,
        branch_id: str,
        source_message_id: str,
    ) -> int:
        """Invalidate memory rows linked to one message."""


class SQLiteVectorStore(VectorStore):
    """SQLite-backed vector store with in-process cosine similarity."""

    _CANDIDATE_MULTIPLIER = 8
    _MIN_CANDIDATES = 64

    async def upsert_item(
        self,
        *,
        db: AsyncSession,
        item: MemoryItemPayload,
        embedding: Sequence[float],
        embed_provider: str,
        embed_model: str,
    ) -> None:
        vector = [float(value) for value in embedding]
        norm = math.sqrt(sum(value * value for value in vector))
        repo = MemoryRepo(db)
        memory_item = await repo.upsert_memory_item(
            item_id=uuid.uuid4().hex,
            session_id=item.session_id,
            branch_id=item.branch_id,
            source_message_id=item.source_message_id,
            source_message_seq=item.source_message_seq,
            source_role=item.source_role,
            content=item.content,
            content_hash=item.content_hash,
        )
        await repo.upsert_embedding(
            embedding_id=uuid.uuid4().hex,
            memory_item_id=memory_item.id,
            provider=embed_provider,
            model_name=embed_model,
            dim=len(vector),
            vector_json=json.dumps(vector, separators=(",", ":")),
            vector_norm=norm if norm > 0 else 1.0,
        )

    async def search(
        self,
        *,
        db: AsyncSession,
        session_id: str,
        branch_id: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[MemorySearchResult]:
        if limit <= 0:
            return []

        query = [float(value) for value in query_embedding]
        query_norm = math.sqrt(sum(value * value for value in query))
        if query_norm <= 0:
            return []

        candidate_limit = max(limit * self._CANDIDATE_MULTIPLIER, self._MIN_CANDIDATES)
        rows = await MemoryRepo(db).list_active_vectors(
            session_id=session_id, branch_id=branch_id, limit=candidate_limit
        )

        scored: list[MemorySearchResult] = []
        for item, embedding in rows:
            try:
                candidate = json.loads(embedding.vector_json)
            except json.JSONDecodeError:
                continue
            if not isinstance(candidate, list) or len(candidate) != len(query):
                continue
            try:
                candidate_vector = [float(value) for value in candidate]
            except (TypeError, ValueError):
                continue
            score = _cosine_similarity(
                query, query_norm, candidate_vector, float(embedding.vector_norm)
            )
            scored.append(
                MemorySearchResult(
                    item_id=item.id,
                    source_message_id=item.source_message_id,
                    source_message_seq=item.source_message_seq,
                    source_role=item.source_role,
                    content=item.content,
                    score=score,
                )
            )

        scored.sort(key=lambda row: (row.score, row.source_message_seq), reverse=True)
        return scored[:limit]

    async def tombstone_by_message(
        self,
        *,
        db: AsyncSession,
        session_id: str,
        branch_id: str,
        source_message_id: str,
    ) -> int:
        return await MemoryRepo(db).tombstone_by_message(
            session_id=session_id,
            branch_id=branch_id,
            source_message_id=source_message_id,
        )


def _cosine_similarity(
    left: list[float], left_norm: float, right: list[float], right_norm: float
) -> float:
    if left_norm <= 0 or right_norm <= 0 or len(left) != len(right):
        return 0.0
    dot = 0.0
    for l_value, r_value in zip(left, right):
        dot += l_value * r_value
    return dot / (left_norm * right_norm)
