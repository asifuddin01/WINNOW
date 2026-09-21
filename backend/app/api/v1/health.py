"""Liveness and readiness probes (guide 16.5), used by Docker healthchecks and monitoring."""

import asyncio

from fastapi import APIRouter, Request, status

from app.db import ping_database
from app.errors import ProblemError
from app.redis_client import ping_redis
from app.schemas.health import CheckState, Liveness, Readiness, ReadinessChecks
from app.schemas.problem import problem_content

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> Liveness:
    """The process is up and serving requests. Touches no dependencies."""
    return Liveness()


@router.get(
    "/readyz",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: problem_content()},
)
async def readyz(request: Request) -> Readiness:
    """The API can reach PostgreSQL and Redis. 503 names the dependency that failed."""
    database_ok, redis_ok = await asyncio.gather(
        ping_database(request.app.state.engine),
        ping_redis(request.app.state.redis),
    )
    database: CheckState = "ok" if database_ok else "unavailable"
    redis: CheckState = "ok" if redis_ok else "unavailable"
    checks = ReadinessChecks(database=database, redis=redis)
    if not (database_ok and redis_ok):
        raise ProblemError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "A required service is unavailable.",
            checks=checks.model_dump(),
        )
    return Readiness(checks=checks)
