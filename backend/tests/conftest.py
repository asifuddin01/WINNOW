"""Shared fixtures.

Unit tests build the app without touching a database. Integration tests run against a
separate `<DATABASE_URL name>_test` database (or TEST_DATABASE_URL), migrated to head once
per session, and the Redis from REDIS_URL.
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
from sqlalchemy.engine import make_url

from app.config import Settings
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parent.parent

# The suite must run without a .env; CI and the containers provide real values.
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-that-is-long-enough-0123456789")
os.environ.setdefault("ENCRYPTION_KEY", base64.b64encode(bytes(range(32))).decode())

TEST_SECRETS: dict[str, Any] = {
    "secret_key": "unit-test-secret-key-with-plenty-of-bytes-0123456789",
    "encryption_key": base64.b64encode(bytes(32)).decode(),
}


def make_settings(**overrides: Any) -> Settings:
    """Settings for a test, independent of whatever the environment holds."""
    return Settings(**{**TEST_SECRETS, **overrides})


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = database_url
    return config


def _test_database_url() -> str:
    if explicit := os.environ.get("TEST_DATABASE_URL"):
        return explicit
    url = make_url(Settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


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
    return make_settings(
        database_url=database_url,
        redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
    )


@asynccontextmanager
async def running_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Run the app's lifespan and yield a client; resources close on exit, not at GC."""
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client,
    ):
        yield client


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Client for an app whose database and Redis are never contacted."""
    async with running_client(app) as client:
        yield client


@pytest.fixture
async def db_client(db_settings: Settings) -> AsyncIterator[AsyncClient]:
    """Client for an app wired to the test database and Redis."""
    async with running_client(create_app(db_settings)) as client:
        yield client
