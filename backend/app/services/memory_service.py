from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models import TimelineMessage
from app.memory.embedder import (
    DeterministicEmbedder,
    Embedder,
    EmbeddingError,
    OpenAIEmbedder,
)
from app.memory.types import MemoryItemPayload, MemorySearchResult, MemorySnippet
from app.memory.vector_store import SQLiteVectorStore, VectorStore

logger = logging.getLogger(__name__)


class GraphContextProvider(ABC):
    """Extension point for future GraphRAG-style retrieval."""

    @abstractmethod
    async def retrieve(
        self,
        *,
        session_id: str,
        branch_id: str,
        query_text: str,
        limit: int,
    ) -> list[MemorySearchResult]:
        """Retrieve graph-derived memory context."""


class NullGraphContextProvider(GraphContextProvider):
    """No-op graph retriever used by vector-only mode."""

    async def retrieve(
        self,
        *,
        session_id: str,
        branch_id: str,
        query_text: str,
        limit: int,
    ) -> list[MemorySearchResult]:
        return []


class MemoryService(ABC):
    """Abstract memory orchestration service."""

    enabled: bool = False

    @abstractmethod
    async def retrieve_context(
        self,
        *,
        session_id: str,
        branch_id: str,
        query_text: str,
        limit: Optional[int] = None,
        db: Optional[AsyncSession] = None,
    ) -> list[MemorySnippet]:
        """Retrieve memory snippets relevant to the current prompt."""

    @abstractmethod
    async def remember_message(
        self, *, message: TimelineMessage, db: Optional[AsyncSession] = None
    ) -> None:
        """Index one timeline message into long-term memory."""

    @abstractmethod
    async def remember_messages(
        self, *, messages: Iterable[TimelineMessage], db: Optional[AsyncSession] = None
    ) -> None:
        """Index multiple timeline messages."""

    @abstractmethod
    async def invalidate_message(
        self,
        *,
        session_id: str,
        branch_id: str,
        source_message_id: str,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Invalidate memory rows associated with a deleted message."""


class NoopMemoryService(MemoryService):
    """Disabled memory mode implementation."""

    enabled = False

    async def retrieve_context(
        self,
        *,
        session_id: str,
        branch_id: str,
        query_text: str,
        limit: Optional[int] = None,
        db: Optional[AsyncSession] = None,
    ) -> list[MemorySnippet]:
        return []

    async def remember_message(
        self, *, message: TimelineMessage, db: Optional[AsyncSession] = None
    ) -> None:
        return None

    async def remember_messages(
        self, *, messages: Iterable[TimelineMessage], db: Optional[AsyncSession] = None
    ) -> None:
        return None

    async def invalidate_message(
        self,
        *,
        session_id: str,
        branch_id: str,
        source_message_id: str,
        db: Optional[AsyncSession] = None,
    ) -> None:
        return None


class VectorMemoryService(MemoryService):
    """Vector-memory implementation with optional hybrid (graph + vector) mode."""

    enabled = True

    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        embedder: Embedder,
        vector_store: VectorStore,
        mode: str,
        max_snippets: int,
        graph_provider: Optional[GraphContextProvider] = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._embedder = embedder
        self._vector_store = vector_store
        self._mode = mode
        self._max_snippets = max(1, max_snippets)
        self._graph_provider = graph_provider or NullGraphContextProvider()

    async def retrieve_context(
        self,
        *,
        session_id: str,
        branch_id: str,
        query_text: str,
        limit: Optional[int] = None,
        db: Optional[AsyncSession] = None,
    ) -> list[MemorySnippet]:
        cleaned_query = query_text.strip()
        if not cleaned_query:
            return []

        top_k = min(max(1, limit or self._max_snippets), self._max_snippets)
        try:
            query_embedding = (await self._embedder.embed_texts([cleaned_query]))[0]
        except (EmbeddingError, IndexError) as exc:
            logger.warning("Memory retrieval skipped because query embedding failed: %s", exc)
            return []
        except Exception:  # noqa: BLE001
            logger.exception("Memory retrieval failed while embedding query")
            return []

        vector_results: list[MemorySearchResult]
        graph_results: list[MemorySearchResult] = []
        try:
            async with self._db_context(db) as active_db:
                vector_results = await self._vector_store.search(
                    db=active_db,
                    session_id=session_id,
                    branch_id=branch_id,
                    query_embedding=query_embedding,
                    limit=top_k * 3,
                )
        except Exception:  # noqa: BLE001
            logger.exception("Memory retrieval failed while searching vector store")
            return []

        if self._mode == "hybrid":
            try:
                graph_results = await self._graph_provider.retrieve(
                    session_id=session_id,
                    branch_id=branch_id,
                    query_text=cleaned_query,
                    limit=top_k * 2,
                )
            except Exception:  # noqa: BLE001
                logger.exception("Hybrid memory retrieval failed in graph provider")

        merged = self._dedupe_and_rank(vector_results + graph_results, top_k)
        return [
            MemorySnippet(
                content=item.content,
                score=item.score,
                source_message_id=item.source_message_id,
                source_message_seq=item.source_message_seq,
                source_role=item.source_role,
            )
            for item in merged
        ]

    async def remember_message(
        self, *, message: TimelineMessage, db: Optional[AsyncSession] = None
    ) -> None:
        await self.remember_messages(messages=[message], db=db)

    async def remember_messages(
        self, *, messages: Iterable[TimelineMessage], db: Optional[AsyncSession] = None
    ) -> None:
        payloads = self._build_payloads(messages)
        if not payloads:
            return

        texts = [item.content for item in payloads]
        try:
            embeddings = await self._embedder.embed_texts(texts)
        except EmbeddingError as exc:
            logger.warning("Memory indexing skipped because embedding failed: %s", exc)
            return
        except Exception:  # noqa: BLE001
            logger.exception("Memory indexing failed while embedding messages")
            return

        if len(embeddings) != len(payloads):
            logger.warning("Memory indexing skipped due to embedding count mismatch")
            return

        try:
            async with self._db_context(db) as active_db:
                for payload, embedding in zip(payloads, embeddings):
                    await self._vector_store.upsert_item(
                        db=active_db,
                        item=payload,
                        embedding=embedding,
                        embed_provider=self._embedder.provider,
                        embed_model=self._embedder.model_name,
                    )
        except Exception:  # noqa: BLE001
            logger.exception("Memory indexing failed while writing vector store")

    async def invalidate_message(
        self,
        *,
        session_id: str,
        branch_id: str,
        source_message_id: str,
        db: Optional[AsyncSession] = None,
    ) -> None:
        async with self._db_context(db) as active_db:
            await self._vector_store.tombstone_by_message(
                db=active_db,
                session_id=session_id,
                branch_id=branch_id,
                source_message_id=source_message_id,
            )

    @asynccontextmanager
    async def _db_context(
        self, db: Optional[AsyncSession]
    ) -> AsyncIterator[AsyncSession]:
        if db is not None:
            yield db
            return
        async with self._sessionmaker() as local_db:
            async with local_db.begin():
                yield local_db

    @staticmethod
    def _build_payloads(messages: Iterable[TimelineMessage]) -> list[MemoryItemPayload]:
        payloads: list[MemoryItemPayload] = []
        for message in messages:
            content = message.content.strip()
            if not content:
                continue
            payloads.append(
                MemoryItemPayload(
                    session_id=message.session_id,
                    branch_id=message.branch_id,
                    source_message_id=message.id,
                    source_message_seq=message.seq,
                    source_role=message.role,
                    content=content,
                    content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                )
            )
        return payloads

    @staticmethod
    def _dedupe_and_rank(
        candidates: Sequence[MemorySearchResult], limit: int
    ) -> list[MemorySearchResult]:
        best_by_content: dict[str, MemorySearchResult] = {}
        for item in candidates:
            key = _normalize_text(item.content)
            if not key:
                continue
            current = best_by_content.get(key)
            if current is None or item.score > current.score:
                best_by_content[key] = item

        ranked = sorted(
            best_by_content.values(),
            key=lambda row: (row.score, row.source_message_seq),
            reverse=True,
        )
        return ranked[:limit]


def create_memory_service(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> MemoryService:
    """Factory for runtime memory mode selection."""

    mode = settings.memory_mode.strip().lower()
    if mode not in {"off", "vector", "hybrid"}:
        logger.warning("Unknown MEMORY_MODE=%s; fallback to off", mode)
        return NoopMemoryService()
    if mode == "off":
        return NoopMemoryService()

    embedder = _create_embedder(settings)
    return VectorMemoryService(
        sessionmaker=sessionmaker,
        embedder=embedder,
        vector_store=SQLiteVectorStore(),
        mode=mode,
        max_snippets=settings.memory_max_snippets,
    )


def _create_embedder(settings: Settings) -> Embedder:
    provider = settings.embed_provider.strip().lower()
    if provider == "deterministic":
        model_name = settings.embed_model.strip() or "deterministic-v1"
        return DeterministicEmbedder(dimension=settings.embed_dim, model_name=model_name)

    if provider == "openai":
        api_key = settings.embed_openai_api_key.strip()
        if not api_key:
            logger.warning(
                "EMBED_PROVIDER=openai but EMBED_OPENAI_API_KEY is missing; fallback to deterministic"
            )
            return DeterministicEmbedder(dimension=settings.embed_dim)
        model_name = settings.embed_model.strip() or "text-embedding-3-small"
        return OpenAIEmbedder(
            base_url=settings.openai_base_url,
            api_key=api_key,
            model_name=model_name,
            dimension=settings.embed_dim,
        )

    logger.warning("Unknown EMBED_PROVIDER=%s; fallback to deterministic", provider)
    return DeterministicEmbedder(dimension=settings.embed_dim)


def _normalize_text(value: str) -> str:
    collapsed = " ".join(value.split())
    return collapsed.casefold().strip()
