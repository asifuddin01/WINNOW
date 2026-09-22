"""Shared fixtures.

Unit tests build the app without touching a database. Integration tests run against a
separate `<DATABASE_URL name>_test` database (or TEST_DATABASE_URL), migrated to head once
per session, inside a transaction per test that is rolled back afterwards, and against
Redis database 15 (or TEST_REDIS_URL), flushed around each test.
"""

import asyncio
import base64
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.email.messages import Email
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parent.parent

# The suite must run without a .env; CI and the containers provide real values.
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-that-is-long-enough-0123456789")
os.environ.setdefault("ENCRYPTION_KEY", base64.b64encode(bytes(range(32))).decode())

TEST_SECRETS: dict[str, Any] = {
    "secret_key": "unit-test-secret-key-with-plenty-of-bytes-0123456789",
    "encryption_key": base64.b64encode(bytes(32)).decode(),
}
TEST_ORIGIN = "https://testserver"
# Fast Argon2 (production parameters have their own test), no network, HTTPS origin.
FAST_AUTH: dict[str, Any] = {
    "argon2_memory_kib": 1024,
    "argon2_time_cost": 1,
    "password_breach_check": False,
    "public_url": TEST_ORIGIN,
    "smtp_host": None,  # the dev containers point SMTP at Mailpit
}


# Production refuses weak Argon2 parameters, so production-mode tests pass the real ones.
PRODUCTION_ARGON2: dict[str, Any] = {"argon2_memory_kib": 65_536, "argon2_time_cost": 3}


def make_settings(**overrides: Any) -> Settings:
    """Settings for a test, independent of whatever the environment holds."""
    return Settings(**{**TEST_SECRETS, **FAST_AUTH, **overrides})


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = database_url
    return config


def _test_database_url() -> str:
    if explicit := os.environ.get("TEST_DATABASE_URL"):
        return explicit
    url = make_url(Settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


def _test_redis_url() -> str:
    """Tests use their own Redis database and flush it, so development data is safe."""
    if explicit := os.environ.get("TEST_REDIS_URL"):
        return explicit
    base = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    return base.rsplit("/", 1)[0] + "/15"


async def _ensure_database(database_url: str) -> None:
    url = make_url(database_url)
    name = url.database or ""
    # CREATE DATABASE cannot take a bound parameter, so allow only a plain identifier.
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
        raise ValueError(f"refusing to create test database with name {name!r}")
    connection = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port or 5432,
        database="postgres",
    )
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if not exists:
            await connection.execute(f'CREATE DATABASE "{name}"')
    finally:
        await connection.close()


@pytest.fixture(scope="session")
def database_url() -> str:
    """URL of the migrated test database."""
    url = _test_database_url()
    asyncio.run(_ensure_database(url))
    command.upgrade(alembic_config(url), "head")
    return url


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def db_settings(database_url: str) -> Settings:
    return make_settings(database_url=database_url, redis_url=_test_redis_url())


def make_client(app: FastAPI, ip: str = "127.0.0.1") -> AsyncClient:
    """HTTPS so Secure cookies round-trip, and our Origin so the CSRF origin check passes."""
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False, client=(ip, 50000)),
        base_url=TEST_ORIGIN,
        headers={"Origin": TEST_ORIGIN},
    )


@asynccontextmanager
async def running_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Run the app's lifespan and yield a client; resources close on exit, not at GC."""
    async with app.router.lifespan_context(app), make_client(app) as client:
        yield client


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Client for an app whose database and Redis are never contacted."""
    async with running_client(app) as client:
        yield client


class MemoryMailer:
    """Collects outgoing email so tests can follow the links in it."""

    def __init__(self) -> None:
        self.outbox: list[Email] = []

    async def send(self, email: Email) -> None:
        self.outbox.append(email)

    def sent_to(self, to: str) -> list[Email]:
        return [email for email in self.outbox if email.to == to]

    def token(self, to: str, page: str) -> str:
        """The token from the newest `/{page}/{token}` link emailed to `to`."""
        for email in reversed(self.outbox):
            if email.to == to and (found := re.search(rf"/{page}/([A-Za-z0-9_-]+)", email.body)):
                return found.group(1)
        raise AssertionError(f"no {page} link was emailed to {to}")


@pytest.fixture
def mailer() -> MemoryMailer:
    return MemoryMailer()


@pytest.fixture
async def db_connection(database_url: str) -> AsyncIterator[AsyncConnection]:
    """One connection per test inside a transaction that is rolled back afterwards.
    Rolling back, rather than deleting, also respects the append-only audit trigger."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
async def db_app(
    db_settings: Settings, db_connection: AsyncConnection, mailer: MemoryMailer
) -> AsyncIterator[FastAPI]:
    """The app on the test database and Redis, with its lifespan running."""
    app = create_app(db_settings)
    async with app.router.lifespan_context(app):
        app.state.sessionmaker = async_sessionmaker(
            bind=db_connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        app.state.mailer = mailer
        redis: Redis = app.state.redis
        await redis.flushdb()
        try:
            yield app
        finally:
            await redis.flushdb()


@pytest.fixture
async def db_client(db_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Client for an app wired to the test database and Redis."""
    async with make_client(db_app) as client:
        yield client


@pytest.fixture
async def db(db_app: FastAPI) -> AsyncIterator[AsyncSession]:
    """A session on the test transaction, for arranging and inspecting rows."""
    session: AsyncSession = db_app.state.sessionmaker()
    try:
        yield session
    finally:
        await session.close()
