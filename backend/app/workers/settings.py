"""ARQ worker entry point: `arq app.workers.settings.WorkerSettings`.

Imports, deduplication, ranking, PDF processing and exports run here, never in a request.
"""

import asyncio
from typing import Any, ClassVar

import structlog
from arq.connections import RedisSettings
from arq.typing import WorkerCoroutine
from arq.worker import Function, func

from app.config import get_settings
from app.email.mailer import SEND_EMAIL_JOB, deliver
from app.email.messages import Email
from app.logging_config import configure_logging

log = structlog.get_logger(__name__)


async def ping(ctx: dict[str, Any]) -> str:
    """Round-trip check for the queue: enqueue `ping` and expect "pong"."""
    return "pong"


async def send_email(ctx: dict[str, Any], to: str, subject: str, body: str) -> None:
    """Deliver one email over SMTP, off the event loop."""
    await asyncio.to_thread(deliver, get_settings(), Email(to, subject, body))


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging(get_settings())
    log.info("worker.started")


async def shutdown(ctx: dict[str, Any]) -> None:
    log.info("worker.stopped")


class WorkerSettings:
    functions: ClassVar[list[WorkerCoroutine | Function]] = [
        ping,
        # Job arguments include one-time links: keep no result behind, retry a flaky server.
        func(send_email, name=SEND_EMAIL_JOB, keep_result=0, max_tries=5),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    health_check_interval = 30
