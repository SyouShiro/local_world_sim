from __future__ import annotations

from typing import Tuple

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
