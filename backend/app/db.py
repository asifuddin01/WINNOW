"""Async database engine, session factory and the per-request session dependency."""

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

import structlog
from fastapi import Depends, Request
from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings

log = structlog.get_logger(__name__)


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.database_url, pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request, closed when the response is done."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def ping_database(engine: AsyncEngine, limit_seconds: float = 2.0) -> bool:
    """True when the database answers a trivial query within `limit_seconds`."""
    try:
        async with asyncio.timeout(limit_seconds), engine.connect() as connection:
            await connection.scalar(select(literal(1)))
    except Exception as exc:  # readiness must report any failure, not raise it
        log.warning("readiness.check_failed", check="database", error=type(exc).__name__)
        return False
    return True
