from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


def create_engine(db_url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine for the provided database URL."""

    return create_async_engine(db_url, future=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async sessionmaker bound to the given engine."""

    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Initialize database tables for all ORM models."""

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if engine.dialect.name == "sqlite":
            await _migrate_sqlite_schema(conn)


async def _migrate_sqlite_schema(conn) -> None:
    """Apply lightweight SQLite migrations for additive columns."""

    await _ensure_sqlite_column(
        conn,
        table_name="session_preferences",
        column_name="timeline_start_iso",
        column_definition="timeline_start_iso TEXT",
    )
    await _ensure_sqlite_column(
        conn,
        table_name="session_preferences",
        column_name="timeline_step_value",
        column_definition="timeline_step_value INTEGER NOT NULL DEFAULT 1",
    )
    await _ensure_sqlite_column(
        conn,
        table_name="session_preferences",
        column_name="timeline_step_unit",
        column_definition="timeline_step_unit TEXT NOT NULL DEFAULT 'month'",
    )


async def _ensure_sqlite_column(
    conn,
    *,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
    existing_columns = {row[1] for row in result.fetchall()}
    if column_name in existing_columns:
        return
    await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}"))
