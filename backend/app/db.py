"""Async database engine, session factory and the per-request session dependency.

Row-level security (guide 12.2): every transaction of a request's session runs as
`winnow_app` with the signed-in user's id in `app.user_id`, and the database itself then
keeps records, decisions and notes of other reviews out of reach (see the migration
`row_level_security`). Every other session — workers, operator commands, tests arranging
data — says explicitly that it runs as the owner the app logs in as.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

import structlog
from fastapi import Depends, Request
from sqlalchemy import Connection, event, func, literal, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, SessionTransaction

from app.config import Settings

log = structlog.get_logger(__name__)


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.database_url, pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


APP_ROLE = "winnow_app"
# Session.info keys: this session serves a request, and on whose behalf.
_REQUEST = "row_security"
_USER = "row_security_user"


@event.listens_for(Session, "after_begin")
def _run_as(session: Session, transaction: SessionTransaction, connection: Connection) -> Any:
    """At the start of each transaction, say who it runs as. The settings are local to the
    transaction, so nothing carries over to the next user of a pooled connection."""
    if session.info.get(_REQUEST):
        role, user = APP_ROLE, session.info.get(_USER, "")
    else:
        role, user = "none", ""  # "none": the login role, as SET ROLE NONE
    connection.execute(
        select(func.set_config("role", role, True), func.set_config("app.user_id", user, True))
    )


async def bind_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """From now on the request's transactions act for this user."""
    session.info[_USER] = str(user_id)
    await session.execute(select(func.set_config("app.user_id", str(user_id), True)))


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request, closed when the response is done. Until a user is bound
    (`bind_user`, done when the request is authenticated) its transactions see no rows of
    the tables under row-level security."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        session.info[_REQUEST] = True
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
