"""ARQ worker entry point: `arq app.workers.settings.WorkerSettings`.

Imports, deduplication, ranking, PDF processing and exports run here, never in a request.
"""

from typing import Any, ClassVar

import structlog
from arq.connections import RedisSettings
from arq.typing import WorkerCoroutine

from app.config import get_settings
from app.logging_config import configure_logging

log = structlog.get_logger(__name__)


async def ping(ctx: dict[str, Any]) -> str:
    """Round-trip check for the queue: enqueue `ping` and expect "pong"."""
    return "pong"


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging(get_settings())
    log.info("worker.started")


async def shutdown(ctx: dict[str, Any]) -> None:
    log.info("worker.stopped")


class WorkerSettings:
    functions: ClassVar[list[WorkerCoroutine]] = [ping]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    health_check_interval = 30
