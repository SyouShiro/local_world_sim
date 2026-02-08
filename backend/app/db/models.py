from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.time_utils import utc_now


class WorldSession(Base):
    """A single world simulation session."""

    __tablename__ = "world_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    world_preset: Mapped[str] = mapped_column(Text, nullable=False)
    running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tick_label: Mapped[str] = mapped_column(String, nullable=False, default="1个月")
    post_gen_delay_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    active_branch_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Branch(Base):
    """Branch for a simulation timeline."""

    __tablename__ = "branches"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("world_sessions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    parent_branch_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    fork_from_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TimelineMessage(Base):
    """Messages emitted by the simulation runner or user interventions."""

    __tablename__ = "timeline_messages"
    __table_args__ = (UniqueConstraint("branch_id", "seq", name="uq_message_branch_seq"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("world_sessions.id"), nullable=False)
    branch_id: Mapped[str] = mapped_column(String, ForeignKey("branches.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    time_jump_label: Mapped[str] = mapped_column(String, nullable=False)
    model_provider: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    token_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    token_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserIntervention(Base):
    """User-provided interventions waiting to be consumed by the runner."""

    __tablename__ = "user_interventions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("world_sessions.id"), nullable=False)
    branch_id: Mapped[str] = mapped_column(String, ForeignKey("branches.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderConfig(Base):
    """Persisted provider configuration per session."""

    __tablename__ = "provider_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String, ForeignKey("world_sessions.id"), nullable=False, unique=True
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    extra_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MemoryItem(Base):
    """Persisted memory snippet metadata keyed by session/branch/message."""

    __tablename__ = "memory_items"
    __table_args__ = (
        UniqueConstraint(
            "branch_id",
            "source_message_id",
            "content_hash",
            name="uq_memory_branch_message_hash",
        ),
        Index("ix_memory_scope_active", "session_id", "branch_id", "is_active"),
        Index("ix_memory_source_message", "source_message_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("world_sessions.id"), nullable=False)
    branch_id: Mapped[str] = mapped_column(String, ForeignKey("branches.id"), nullable=False)
    source_message_id: Mapped[str] = mapped_column(
        String, ForeignKey("timeline_messages.id"), nullable=False
    )
    source_message_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    source_role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    invalidated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class MemoryEmbedding(Base):
    """Vector payload associated with a memory item."""

    __tablename__ = "memory_embeddings"
    __table_args__ = (
        UniqueConstraint("memory_item_id", name="uq_memory_embedding_item"),
        Index("ix_memory_embedding_item", "memory_item_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    memory_item_id: Mapped[str] = mapped_column(
        String, ForeignKey("memory_items.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_json: Mapped[str] = mapped_column(Text, nullable=False)
    vector_norm: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
