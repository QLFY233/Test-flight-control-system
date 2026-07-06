"""Database session factory and utilities."""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend_A.db.models import Base

logger = logging.getLogger(__name__)

DATABASE_URL = "sqlite+aiosqlite:///./data/flight_control.db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def create_all() -> None:
    """Create all tables if they don't exist."""
    import os
    os.makedirs("./data", exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("db/session: all tables created")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def close_engine() -> None:
    """Dispose the engine."""
    await engine.dispose()
    logger.info("db/session: engine disposed")
