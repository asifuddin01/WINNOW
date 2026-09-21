"""Migrations apply, roll back and match the models."""

import asyncio

import asyncpg
from alembic import command
from sqlalchemy.engine import make_url

from tests.conftest import alembic_config

REQUIRED_EXTENSIONS = {"citext", "pg_trgm", "pgcrypto"}


def _installed_extensions(database_url: str) -> set[str]:
    async def query() -> set[str]:
        url = make_url(database_url)
        connection = await asyncpg.connect(
            user=url.username,
            password=url.password,
            host=url.host,
            port=url.port or 5432,
            database=url.database,
        )
        try:
            rows = await connection.fetch("SELECT extname FROM pg_extension")
        finally:
            await connection.close()
        return {row["extname"] for row in rows}

    return asyncio.run(query())


def test_head_enables_required_extensions(database_url: str) -> None:
    assert _installed_extensions(database_url) >= REQUIRED_EXTENSIONS


def test_migrations_round_trip(database_url: str) -> None:
    config = alembic_config(database_url)
    command.downgrade(config, "base")
    assert not (_installed_extensions(database_url) & REQUIRED_EXTENSIONS)
    command.upgrade(config, "head")
    assert _installed_extensions(database_url) >= REQUIRED_EXTENSIONS


def test_models_have_no_unmigrated_changes(database_url: str) -> None:
    command.check(alembic_config(database_url))
