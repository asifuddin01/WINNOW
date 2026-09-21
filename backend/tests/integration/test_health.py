"""Readiness against the real PostgreSQL and Redis."""

import pytest
from httpx import AsyncClient
from sqlalchemy.engine import make_url

from app.config import Settings
from app.main import create_app
from tests.conftest import make_settings, running_client


async def test_readyz_reports_both_dependencies_ok(db_client: AsyncClient) -> None:
    response = await db_client.get("/api/v1/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


async def _readyz(settings: Settings) -> tuple[int, dict[str, object], str]:
    async with running_client(create_app(settings)) as client:
        response = await client.get("/api/v1/readyz")
    return response.status_code, response.json(), response.headers["content-type"]


@pytest.mark.parametrize("broken", ["database", "redis"])
async def test_readyz_names_the_unavailable_dependency(db_settings: Settings, broken: str) -> None:
    if broken == "database":
        url = make_url(db_settings.database_url).set(port=1)
        settings = make_settings(
            database_url=url.render_as_string(hide_password=False),
            redis_url=db_settings.redis_url,
        )
    else:
        settings = make_settings(
            database_url=db_settings.database_url, redis_url="redis://127.0.0.1:1/0"
        )
    status, body, content_type = await _readyz(settings)
    assert status == 503
    assert content_type == "application/problem+json"
    healthy = "redis" if broken == "database" else "database"
    assert body["checks"] == {broken: "unavailable", healthy: "ok"}
