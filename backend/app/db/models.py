from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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
