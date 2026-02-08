from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryItemPayload:
    """Payload persisted into the memory index."""

    session_id: str
    branch_id: str
    source_message_id: str
    source_message_seq: int
    source_role: str
    content: str
    content_hash: str


@dataclass(frozen=True)
class MemorySearchResult:
    """Vector-search candidate with similarity score."""

    item_id: str
    source_message_id: str
    source_message_seq: int
    source_role: str
    content: str
    score: float


@dataclass(frozen=True)
class MemorySnippet:
    """Snippet returned to prompt construction."""

    content: str
    score: float
    source_message_id: str
    source_message_seq: int
    source_role: str
